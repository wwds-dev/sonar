"""The "why is this notable" card (spec docs/specs/why-notable-card.md).

Pure-function tests on a recorded `/api/assets` board (129 rows, captured from
the loopback agent on 2026-11-18); no window, no model call.
"""
import copy
import json
import random
import re
import sys
import time
import types
from pathlib import Path

import pytest

from sonar import assets as A
from ui import why_card as W

BOARD = json.loads((Path(__file__).parent / "fixtures"
                    / "assets_board_2026-11-18.json").read_text())
ROWS = BOARD["assets"]

# W3: matched by word-start, case-insensitive.
BANNED = """recommend advice advise pick top best worst winner loser favourite attractive
promising hot trending bet invest hold avoid accumulate outperform underperform beat
bottom rally surge soar plunge crash dip trigger driver poised due soon imminent
certain definitely proven reliable obvious confirmed validated probably possible
potential might must conf catalyst buy sell short long bullish bearish upside downside
opportunity signal edge profit gain win likely expect will should could may breakout
rebound recover bounce oversold overbought cheap expensive undervalued overvalued
target chance odds probability confident confidence sure guaranteed safe risky strong
weak positive negative tone sentiment momentum""".split()
ALLOWED = ["worth a look"]


def banned_in(text: str, extra_allowed=()) -> list:
    t = text
    for a in [W.FOOTER, *ALLOWED, *extra_allowed]:
        t = re.sub(re.escape(a), " ", t, flags=re.I)
    return [b for b in BANNED if re.search(r"\b" + b, t, re.I)]


@pytest.fixture(autouse=True)
def _tz(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


@pytest.fixture
def no_llm(monkeypatch):
    class Poison(types.ModuleType):
        def __getattr__(self, name):
            raise AssertionError(f"the card touched sonar.llm.{name}")
    monkeypatch.setitem(sys.modules, "sonar.llm", Poison("sonar.llm"))


def card(row, plain=True, board=BOARD, age=0.0):
    return W.build_card(row, board, plain=plain, age_s=age)


def strings(c: W.Card) -> list:
    out = [c.title, c.as_of, c.rounding_note, c.footer]
    out += [x for x in (c.stale, c.unavailable) if x]
    for ln in c.lines:
        out += [ln.label, ln.text] + ([ln.expert_detail] if ln.expert_detail else [])
    return out


def row_of(sym):
    return next(r for r in ROWS if r["symbol"] == sym)


# --------------------------------------------------------------------------- #
# success measure 1
# --------------------------------------------------------------------------- #
def test_fixture_is_the_whole_board():
    assert len(ROWS) == 129 and {r["cls"] for r in ROWS} >= set(W.PLURAL)


@pytest.mark.parametrize("plain", [True, False])
def test_every_row_has_four_lines_summing_to_the_displayed_score(no_llm, plain):
    for r in ROWS:
        c = card(r, plain)
        assert len(c.lines) == 4, r["symbol"]
        assert all(isinstance(ln.points, int) for ln in c.lines)
        assert sum(ln.points for ln in c.lines) == W.displayed_score(r["confidence"])
        assert all(0 <= ln.points <= ln.max for ln in c.lines)


def test_every_lines_facts_match_the_row(no_llm):
    for r in ROWS:
        by = {ln.key: ln for ln in card(r).lines}
        k = len(r["headlines"])
        if k:
            assert f"{k} matched news " in by["news"].text, r["symbol"]
        else:
            assert by["news"].text == "No matched news."
        assert f"{abs(r['momentum']) * 100:.1f}%" in by["momentum"].text
        assert W._days_phrase(r["momentum_days"], r["cls"]) in by["momentum"].text
        assert f"{r['volatility'] * 100:.1f}%" in by["volatility"].text
        assert W.swing_words(r["volatility"]) in by["volatility"].text
        assert str(W.displayed_score(r["confidence"])) in card(r).title


def test_the_card_never_imports_the_llm_module():
    src = (Path(W.__file__)).read_text()
    assert "sonar.llm" not in src and "import llm" not in src
    assert "PySide6" not in src


def test_the_max_points_are_the_weights_and_whole():
    for k, w in A._W.items():
        assert abs(w * 100 - round(w * 100)) < 1e-9
        assert W.max_points(k) == round(w * 100)
    assert sum(W.max_points(k) for k in A._W) == 100


def test_lines_sort_by_points_then_weight_order_zero_last():
    for r in ROWS:
        lines = card(r).lines
        keys = [(ln.points == 0, -ln.points, W.ORDER.index(ln.key)) for ln in lines]
        assert keys == sorted(keys), r["symbol"]
    assert W.ORDER == ("news", "momentum", "catalyst", "volatility")


def test_points_are_nothing_but_the_largest_remainder():
    # exact 26.4 / 12.6 / 10.5 = 49.5 -> target 50; floors 26+12+10 = 48,
    # two extra points go to the largest remainders: .6 (vol) and .5 (news)
    comp = {"momentum": 0.88, "volatility": 0.84, "news": 0.30}
    exact = {k: 100 * A._W[k] * v for k, v in comp.items()}
    pts = W.allocate_points(comp, 50)
    assert pts == {"news": 11, "momentum": 26, "catalyst": 0, "volatility": 13}
    assert sum(pts.values()) == 50
    for k, v in comp.items():
        assert pts[k] in (int(exact[k]), int(exact[k]) + 1)


def test_the_largest_fractional_part_gets_the_extra_point():
    # news 35 * .5 = 17.5 ; momentum 30 * .45 = 13.5 ; targets differ by rounding
    comp = {"news": 0.5, "momentum": 0.45, "volatility": 0.0}
    # exact: 17.5, 13.5, 0 -> floors 17, 13; target 31 -> one extra
    assert W.allocate_points(comp, 31) == {"news": 18, "momentum": 13,
                                           "catalyst": 0, "volatility": 0}
    comp = {"news": 0.45, "momentum": 0.5, "volatility": 0.0}
    # news 15.75, momentum 15.0 -> floors 15, 15; target 31 -> news (.75)
    assert W.allocate_points(comp, 31)["news"] == 16


def test_ties_in_remainder_go_in_weight_order():
    comp = {"news": 0.5, "momentum": 0.5, "volatility": 0.5, "catalyst": 0.5}
    # exact 17.5, 15, 7.5 (volatility), 10 (catalyst); floors sum to 49;
    # target 50: news and volatility both have .5 left, news wins on weight
    pts = W.allocate_points(comp, 50)
    assert pts["news"] == 18 and pts["volatility"] == 7


def test_allocation_property_on_random_components():
    rnd = random.Random(7)
    for _ in range(2000):
        comp = {k: round(rnd.random(), 3) for k in A._W if rnd.random() < .8 or k == "news"}
        total = round(100 * sum(A._W[k] * comp.get(k, 0.0) for k in A._W), 1)
        target = W.displayed_score(total)
        pts = W.allocate_points(comp, target)
        assert pts is not None
        assert sum(pts.values()) == target
        assert all(0 <= v <= W.max_points(k) for k, v in pts.items())


def test_allocation_refuses_a_target_the_formula_cannot_reach():
    assert W.allocate_points({"news": 0.5}, 90) is None
    assert W.allocate_points({"news": 0.5}, 0) is None


def test_a_broken_sum_falls_back_to_unrounded_points_without_the_note(caplog):
    r = copy.deepcopy(row_of("NVDA"))
    r["confidence"] = 3.0
    c = card(r)
    assert c.rounding_note == W.FALLBACK_NOTE
    assert any(isinstance(ln.points, float) for ln in c.lines)
    assert "do not add up" in caplog.text
    # catalyst is still zero, not "missing", on the fallback path
    cat = next(ln for ln in c.lines if ln.key == "catalyst")
    assert cat.points == 0 and cat.text == "No earnings date in the next 10 days of SONAR's calendar."


def test_displayed_score_is_the_cells_own_format():
    for v in (0.0, 0.49, 0.5, 7.4, 7.5, 77.6, 100.0, 66.45):
        assert W.displayed_score(v) == int(f"{v:.0f}")


# --------------------------------------------------------------------------- #
# ranks
# --------------------------------------------------------------------------- #
def test_ordinals():
    assert [W.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101, 111)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st", "111th"]


def test_competition_rank_shares_ties():
    assert W._rank(5, [9, 5, 5, 1]) == 2
    assert W._rank(1, [9, 5, 5, 1]) == 4
    assert W._rank(9, [9, 5, 5, 1]) == 1


def board_of(rows):
    return {"assets": rows, "generated": 1_700_000_000, "risk": {"name": "x"},
            "horizon": {"momentum_days": 5}}


def mk(sym, cls, mom, vol, conf=50.0, **kw):
    r = {"symbol": sym, "name": sym, "cls": cls, "momentum": mom, "momentum_days": 5,
         "volatility": vol, "confidence": conf, "lean": "Quiet", "headlines": [],
         "comp": {"momentum": 0.5, "volatility": 0.5, "news": 0.0}, "data_age_s": 0.0}
    r.update(kw)
    return r


def test_move_rank_uses_the_absolute_move_within_the_class():
    rows = [mk("A", "Equity", -0.20, .01), mk("B", "Equity", 0.05, .01),
            mk("C", "Equity", 0.10, .01), mk("D", "Crypto", 0.9, .01)]
    b = board_of(rows)
    t = {r["symbol"]: {l.key: l.text for l in card(r, board=b).lines} for r in rows}
    assert "the largest move of 3 shares" in t["A"]["momentum"]       # |-0.20|
    assert "the 2nd-largest move of 3 shares" in t["C"]["momentum"]
    assert "the smallest move of 3 shares" in t["B"]["momentum"]
    assert "the only cryptocurrency on the board" in t["D"]["momentum"]


def test_swing_rank_and_ties():
    rows = [mk("A", "Forex", 0, .004), mk("B", "Forex", 0, .004), mk("C", "Forex", 0, .001)]
    b = board_of(rows)
    a = {l.key: l.text for l in card(rows[0], board=b).lines}["volatility"]
    assert "the largest of 3 currency pairs" in a        # tie shares rank 1
    c = {l.key: l.text for l in card(rows[2], board=b).lines}["volatility"]
    assert "the smallest of 3 currency pairs" in c
    assert "other currency pairs" in a


def test_a_class_of_one_is_the_only_one_and_makes_no_comparison():
    r = mk("X", "Commodity", 0.02, .01)
    t = {l.key: l.text for l in card(r, board=board_of([r])).lines}
    assert "the only commodity on the board" in t["momentum"]
    assert "the only commodity on the board" in t["volatility"]
    assert "partly compares" not in t["momentum"] + t["volatility"]


def test_board_rank_does_not_rely_on_payload_order():
    rows = [mk("A", "Equity", 0, .01, 10.0), mk("B", "Equity", 0, .01, 90.0),
            mk("C", "Equity", 0, .01, 90.0)]
    b = board_of(rows)
    assert "ranked 1st of 3" in card(rows[1], board=b).title
    assert "ranked 1st of 3" in card(rows[2], board=b).title
    assert "ranked 3rd of 3" in card(rows[0], board=b).title


def test_ranks_come_from_the_scores_own_keys(monkeypatch):
    rows = [mk("A", "Equity", 0.01, .05), mk("B", "Equity", 0.50, .01)]
    b = board_of(rows)
    assert "the largest move" in {l.key: l.text for l in card(rows[1], board=b).lines}["momentum"]
    monkeypatch.setitem(A.CROSS_SECTIONAL, "momentum", lambda r: -abs(r.momentum))
    t = {l.key: l.text for l in card(rows[0], board=b).lines}
    assert "the largest move" in t["momentum"]


def test_the_rank_is_among_the_same_class_only():
    r = row_of("NVDA")
    n = sum(1 for x in ROWS if x["cls"] == "Equity")
    assert f"of {n} shares on the board" in {l.key: l.text for l in card(r).lines}["momentum"]


# --------------------------------------------------------------------------- #
# the four lines
# --------------------------------------------------------------------------- #
def test_title_plain_and_expert():
    r = row_of("NVDA")
    assert card(r).title == ("Nvidia — notability score 78 / 100, ranked 1st of 129 "
                             "by this score today (risk filter: aggressive)")
    assert card(r, False).title == ("NVDA — NOTABILITY 78, ranked 1st of 129 "
                                    "(risk filter: aggressive)")


def test_labels_and_expert_detail():
    r = row_of("NVDA")
    plain = {l.key: l for l in card(r).lines}
    exp = {l.key: l for l in card(r, False).lines}
    assert [plain[k].label for k in ("news", "momentum", "volatility", "catalyst")] == \
        ["News", "Recent move", "Swing size", "Earnings date"]
    assert [exp[k].label for k in ("news", "momentum", "volatility", "catalyst")] == \
        ["NEWS", "MOM", "VOL", "EARN"]
    assert exp["news"].expert_detail == "1.000 × 0.35 = 35.0"
    assert all(l.expert_detail is None for l in plain.values())


def test_news_line_counts_sources_and_ages():
    r = mk("A", "Equity", 0, .01, lean="Spike", headlines=[
        {"source": "Reuters", "age_h": 0.2}, {"source": "Reuters", "age_h": 2.4},
        {"source": "AP", "age_h": 3.0}])
    t = card(r, board=board_of([r])).lines
    news = next(l for l in t if l.key == "news").text
    assert news == ("3 matched news stories in the last 3 hours (newest 12 minutes "
                    "before the scan; Reuters ×2, AP). 3 or more stories in the last 6 hours.")


def test_news_singular_and_days():
    r = mk("A", "Equity", 0, .01, lean="Normal",
           headlines=[{"source": "CNBC", "age_h": 168.0}])
    news = next(l for l in card(r, board=board_of([r])).lines if l.key == "news").text
    assert news.startswith("1 matched news story in the last 7 days (newest 7 days before the scan; CNBC).")


def test_undated_headlines_are_counted_but_not_spanned():
    r = mk("A", "Equity", 0, .01, lean="Normal",
           headlines=[{"source": "X", "age_h": None}, {"source": "Y", "age_h": None}])
    news = next(l for l in card(r, board=board_of([r])).lines if l.key == "news").text
    assert news == "2 matched news stories, with no publication time given (X, Y)."
    r["headlines"].append({"source": "Z", "age_h": 5.0})
    news = next(l for l in card(r, board=board_of([r])).lines if l.key == "news").text
    assert news.startswith("3 matched news stories in the last 5 hours")


@pytest.mark.parametrize("lean,expect", [
    ("Spike", "3 or more stories in the last 6 hours."),
    ("Elevated", "At least one story in the last 6 hours, or 3 in the last day."),
    ("Normal", "No story in the last 6 hours and fewer than 3 in the last day."),
])
def test_news_level_sentences(lean, expect):
    assert W._level_sentence(lean) == expect


def test_the_level_sentences_quote_the_constants(monkeypatch):
    monkeypatch.setattr(A, "NEWS_FRESH_H", 4)
    monkeypatch.setattr(A, "NEWS_SPIKE_N", 5)
    monkeypatch.setattr(A, "NEWS_DAY_N", 7)
    monkeypatch.setattr(A, "NEWS_DAY_H", 48)
    assert W._level_sentence("Spike") == "5 or more stories in the last 4 hours."
    assert W._level_sentence("Elevated") == \
        "At least one story in the last 4 hours, or 7 in the last 48 hours."


def test_news_level_thresholds_are_the_constants(monkeypatch):
    from sonar import news as N
    from datetime import datetime, timezone, timedelta
    assert (A.NEWS_FRESH_H, A.NEWS_DAY_H, A.NEWS_SPIKE_N, A.NEWS_DAY_N) == (6, 24, 3, 3)

    class H:
        dated = True
        def __init__(self, age): self.age_hours = age
    assert A.news_level([H(5.9)] * 3) == "Spike"
    assert A.news_level([H(5.9)] * 2) == "Elevated"
    assert A.news_level([H(6.0)] * 2) == "Normal"
    assert A.news_level([H(23.9)] * 3) == "Elevated"
    monkeypatch.setattr(A, "NEWS_SPIKE_N", 2)
    assert A.news_level([H(5.9)] * 2) == "Spike"


def test_a_row_without_news_says_so():
    r = mk("A", "Equity", 0, .01)
    assert next(l for l in card(r, board=board_of([r])).lines
                if l.key == "news").text == "No matched news."


def test_move_line_reads():
    r = row_of("NVDA")
    t = {l.key: l.text for l in card(r).lines}["momentum"]
    assert t.startswith("Fell 13.1% over the last 5 trading days, the 3rd-largest move of 50 shares on the board.")
    assert t.endswith("The size counts, not the direction: a fall scores the same as a rise.")


def test_swing_line_carries_the_dispute_note_only_for_volatility():
    r = row_of("NVDA")
    by = {l.key: l.text for l in card(r).lines}
    assert by["volatility"].endswith(W.UNDER_DISPUTE["volatility"])
    for k in ("news", "momentum", "catalyst"):
        assert W.UNDER_DISPUTE.get(k) is None and "open question" not in by[k]


def test_issue_10_is_in_the_dispute_map():
    assert set(W.UNDER_DISPUTE) == {"volatility"}
    assert "open question" in W.UNDER_DISPUTE["volatility"]
    assert "Learn, section 11" in W.UNDER_DISPUTE["volatility"]


# -- the catalyst-absent branch ------------------------------------------------ #
def test_equity_without_an_earnings_date_is_zero_not_missing():
    r = row_of("NVDA")
    assert "catalyst" not in r["comp"]
    ln = next(l for l in card(r).lines if l.key == "catalyst")
    assert ln.points == 0 and ln.muted
    assert ln.text == "No earnings date in the next 10 days of SONAR's calendar."


def test_equity_with_a_date():
    r = row_of("BABA")
    ln = next(l for l in card(r).lines if l.key == "catalyst")
    assert ln.points == 20
    assert ln.text == ("Earnings tomorrow (pre-market) (2026-11-19): a date on the "
                       "calendar, not a forecast.")


@pytest.mark.parametrize("cls", ["Forex", "Index", "Crypto", "Commodity"])
def test_other_classes_never_score_for_earnings_even_with_a_key(cls):
    r = mk("X", cls, 0.01, .01, comp={"momentum": .5, "volatility": .5, "news": 0,
                                      "catalyst": 1.0},
           catalyst={"label": "x", "date": "2026-01-01"})
    ln = next(l for l in card(r, board=board_of([r])).lines if l.key == "catalyst")
    assert ln.text == (f"SONAR only tracks company earnings dates, so "
                       f"{W.PLURAL[cls]} never score here.")


# -- states -------------------------------------------------------------------- #
@pytest.mark.parametrize("gone", ["momentum", "volatility", "news"])
def test_a_missing_component_is_not_a_zero(gone):
    r = copy.deepcopy(row_of("NVDA"))
    del r["comp"][gone]
    r["confidence"] = round(100 * sum(A._W[k] * r["comp"].get(k, 0) for k in A._W), 1)
    c = card(r)
    ln = next(l for l in c.lines if l.key == gone)
    assert ln.points is None and ln.text == "Not available for this row."
    assert c.lines[-1] is ln
    others = [l for l in c.lines if l.key != gone]
    assert sum(l.points for l in others) == W.displayed_score(r["confidence"])
    assert c.rounding_note == W.ROUNDING_NOTE


def test_empty_comp_shows_title_notice_and_footer():
    r = copy.deepcopy(row_of("NVDA"))
    r["comp"] = {}
    c = card(r)
    assert c.lines == () and c.unavailable == W.UNAVAILABLE_ALL
    assert c.title and c.footer == W.FOOTER


def test_stale_line_is_absolute_and_appears_at_the_warn_age():
    r = copy.deepcopy(row_of("NVDA"))
    r["data_age_s"] = 3600.0
    assert card(r, age=W.AGE_WARN_S - 1).stale is None
    c = card(r, age=W.AGE_WARN_S)
    gen = BOARD["generated"]
    hhmm = time.strftime("%H:%M", time.gmtime(gen - 3600))
    assert c.stale == (f"The price and news for this row were fetched at {hhmm}; "
                       "every figure here is as of then.")
    assert c.stale_level == "warn"
    assert card(r, age=W.AGE_BAD_S).stale_level == "bad"
    assert card(r, age=0).stale_level is None


def test_as_of_line_is_the_scan_time():
    assert card(row_of("NVDA")).as_of == "As of the " + \
        time.strftime("%H:%M", time.gmtime(BOARD["generated"])) + " scan."


def test_the_card_is_the_same_with_or_without_a_key(monkeypatch, no_llm):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    a = card(row_of("NVDA"))
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert a == card(row_of("NVDA"))


# --------------------------------------------------------------------------- #
# success measure 2: no direction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("plain", [True, False])
def test_flipping_the_momentum_sign_changes_exactly_the_verb(plain):
    n = 0
    for r in ROWS:
        if r["momentum"] == 0:
            continue
        flipped = copy.deepcopy(r)
        flipped["momentum"] = -r["momentum"]
        # same board, so ranks are unchanged (rank uses |momentum|)
        b2 = copy.deepcopy(BOARD)
        b2["assets"] = [flipped if x["symbol"] == r["symbol"] else x for x in ROWS]
        a, b = card(r, plain), card(flipped, plain, board=b2)
        diffs = []
        for x, y in zip(strings(a), strings(b)):
            xs, ys = x.split(), y.split()
            assert len(xs) == len(ys)
            diffs += [(p, q) for p, q in zip(xs, ys) if p != q]
        assert len(diffs) == 1 and set(diffs[0]) == {"Rose", "Fell"}, (r["symbol"], diffs)
        n += 1
    assert n > 100


def test_a_row_that_did_not_move_gets_a_neutral_verb():
    r = mk("A", "Equity", 0.0, .01)
    t = next(l for l in card(r, board=board_of([r])).lines if l.key == "momentum").text
    assert t.startswith("Moved 0.0% over")


@pytest.mark.parametrize("plain", [True, False])
def test_no_banned_term_on_any_card(plain):
    for r in ROWS:
        c = card(r, plain, age=W.AGE_BAD_S)
        label = (r.get("catalyst") or {}).get("label", "")
        for s in strings(c):
            assert not banned_in(s, [label] if label else []), (r["symbol"], s)


def test_no_banned_term_in_the_fixed_strings():
    for s in [*W.UNDER_DISPUTE.values(), W.UNAVAILABLE_ALL, W.UNAVAILABLE_PART,
              W.ROUNDING_NOTE, *W.LABELS["news"], *W.LABELS["momentum"],
              *W.LABELS["volatility"], *W.LABELS["catalyst"],
              *W.PLURAL.values(), *W.SINGULAR.values(),
              W._level_sentence("Spike"), W._level_sentence("Elevated"),
              W._level_sentence("Normal")]:
        assert not banned_in(s), s


def test_the_banned_matcher_catches_inflections_and_ignores_the_allowlist():
    assert banned_in("A strong rallying day")
    assert banned_in("You should buy") == ["buy", "should"]
    assert not banned_in("Worth a look")
    assert not banned_in(W.FOOTER)       # the footer is the one allowed place


def test_no_future_tense_in_any_template():
    for r in ROWS:
        for s in strings(card(r)):
            if s is W.FOOTER:
                continue
            assert not re.search(r"\bwill\b|\bgoing to\b", s)


def test_sentences_are_short():
    for r in ROWS:
        for ln in card(r).lines:
            for sentence in re.split(r"(?<=[.])\s+", ln.text):
                assert len(sentence.split()) <= 25, sentence


# --------------------------------------------------------------------------- #
# success measure 3: parity
# --------------------------------------------------------------------------- #
def numbers(s):
    return re.findall(r"\d+(?:[.,]\d+)?", s)


def test_plain_and_expert_carry_the_same_numbers_and_footer():
    for r in ROWS:
        p, e = card(r, True), card(r, False)
        assert [(l.key, l.points, l.max, l.muted) for l in p.lines] == \
               [(l.key, l.points, l.max, l.muted) for l in e.lines]
        assert [numbers(l.text) for l in p.lines] == [numbers(l.text) for l in e.lines]
        assert p.footer == e.footer == W.FOOTER
        assert p.rounding_note == e.rounding_note
        assert p.as_of == e.as_of and p.stale == e.stale
        pt = re.search(r"score (\d+) / 100, ranked (\d+\w\w) of (\d+)", p.title).groups()
        et = re.search(r"NOTABILITY (\d+), ranked (\d+\w\w) of (\d+)", e.title).groups()
        assert pt == et


# --------------------------------------------------------------------------- #
# swing words moved here
# --------------------------------------------------------------------------- #
def test_swing_words_follow_the_number():
    assert W.swing_words(0.045) == "big swings"
    assert W.swing_words(0.030) == "big swings"
    assert W.swing_words(0.020) == "medium"
    assert W.swing_words(0.015) == "medium"
    assert W.swing_words(0.007) == "small swings"


# --------------------------------------------------------------------------- #
# Review fixes (docs/audit/why-notable-card-*review*.md)
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).parent.parent


def test_expert_arithmetic_multiplies_out_as_printed():
    """CR P2-1: 158 of 516 expert lines once showed `0.97 x 0.30 = 29.2`."""
    n = 0
    for r in ROWS:
        for ln in card(r, False).lines:
            if ln.expert_detail is None:
                continue
            m = re.fullmatch(r"(\d\.\d+) × (\d\.\d+) = (\d+\.\d)", ln.expert_detail)
            assert m, ln.expert_detail
            a, b, prod = (float(x) for x in m.groups())
            assert f"{a * b * 100:.1f}" == f"{prod:.1f}" or abs(a * b * 100 - prod) < 0.051, \
                (r["symbol"], ln.expert_detail)
            n += 1
    assert n >= 500


def test_the_earnings_sentence_never_looks_further_than_the_calendar():
    """DF P1-1: the calendar reaches 14 days; the horizon-scaled window did not."""
    r = copy.deepcopy(row_of("NVDA"))
    for days in (1, 5, 20, 60, 250):
        r["momentum_days"] = days
        t = next(l for l in card(r).lines if l.key == "catalyst").text
        reach = min(2 * days, 14)
        assert t == f"No earnings date in the next {reach} days of SONAR's calendar."
    assert W.CALENDAR_DAYS == 14


@pytest.mark.parametrize("cal", [None, {}, {"n": 0, "days": 14}])
def test_an_empty_or_unfetched_calendar_says_so(cal):
    b = copy.deepcopy(BOARD)
    if cal is None:
        b.pop("earnings_calendar")
    else:
        b["earnings_calendar"] = cal
    r = next(x for x in b["assets"] if x["symbol"] == "NVDA")
    t = next(l for l in card(r, board=b).lines if l.key == "catalyst").text
    assert t == "Earnings calendar not available."
    # a dated share and a non-share are unaffected
    baba = next(x for x in b["assets"] if x["symbol"] == "BABA")
    assert "a date on the calendar" in \
        next(l for l in card(baba, board=b).lines if l.key == "catalyst").text


def test_the_payload_carries_the_calendar_coverage(monkeypatch):
    """QA P3: a payload built by the real scanner, with the fetch stubbed, not a
    grep of the source."""
    from sonar import horizon, risk

    def fetch(symbol, rng):
        closes = [100.0 + i * 0.01 for i in range(300)]
        return (closes[-1], "USD", closes)

    class Ev:
        def cached_payload(self):
            return {"n_earnings": 9}

        def earnings_for(self, symbol):
            return None

    monkeypatch.setattr(A, "_fetch", fetch)
    board = A.AssetScanner(events=Ev()).payload(
        [], horizon.HORIZONS["week"], risk.get("aggressive"))
    assert board["status"] == "live" and board["assets"]
    assert board["earnings_calendar"] == {"n": 9, "days": 14}
    # and the card reads it from there
    row = next(r for r in board["assets"] if r["cls"] == "Equity")
    t = next(l for l in card(row, board=board).lines if l.key == "catalyst").text
    assert t == "No earnings date in the next 10 days of SONAR's calendar."


def test_the_calendar_coverage_reads_the_cache_without_fetching():
    class Ev:
        calls = 0
        def cached_payload(self):
            Ev.calls += 1
            return {"n_earnings": 7}
    scanner = A.AssetScanner(events=Ev())
    assert scanner._calendar_coverage() == {"n": 7, "days": 14}
    assert A.AssetScanner(events=None)._calendar_coverage() == {"n": 0, "days": 14}


def test_the_25504_figure_is_the_one_in_confidence_13_and_the_footer_is_the_specs():
    """DF P2-2."""
    conf = (ROOT / "CONFIDENCE.md").read_text()
    sec13 = conf[conf.index("## 13. The completed studies"):conf.index("## Sources")]
    assert "25,504 setups" in sec13
    assert "25,504" in W.FOOTER
    spec = (ROOT / "docs" / "specs" / "why-notable-card.md").read_text()
    quoted = re.search(r"> This score counts.*?large effects\.", spec, re.S).group(0)
    quoted = " ".join(l.lstrip("> ").strip() for l in quoted.splitlines())
    assert W.FOOTER == quoted


def test_a_zero_move_is_not_a_rise_or_a_fall():
    for mom in (0.0, 0.0004, -0.0004):
        r = mk("A", "Equity", mom, .01)
        t = next(l for l in card(r, board=board_of([r])).lines if l.key == "momentum").text
        assert t.startswith("Moved 0.0% over"), t
    r = mk("A", "Equity", 0.0006, .01)
    assert next(l for l in card(r, board=board_of([r])).lines
                if l.key == "momentum").text.startswith("Rose 0.1% over")


def test_days_wording():
    assert W._days_phrase(1, "Equity") == "1 trading day"
    assert W._days_phrase(5, "Equity") == "5 trading days"
    assert W._days_phrase(1, "Crypto") == "1 day"
    assert W._days_phrase(5, "Forex") == "5 days"
    r = mk("A", "Crypto", 0.02, .01, momentum_days=1)
    t = next(l for l in card(r, board=board_of([r])).lines if l.key == "momentum").text
    assert " over the last day, " in t
    r = mk("A", "Equity", 0.02, .01, momentum_days=1)
    t = next(l for l in card(r, board=board_of([r])).lines if l.key == "momentum").text
    assert " over the last trading day, " in t
    assert "1 days" not in " ".join(strings(card(r, board=board_of([r]))))


def test_two_rows_that_show_the_same_score_share_a_rank():
    rows = [mk("A", "Equity", 0, .01, 74.6), mk("B", "Equity", 0, .01, 75.4),
            mk("C", "Equity", 0, .01, 60.0)]
    b = board_of(rows)
    assert "ranked 1st of 3" in card(rows[0], board=b).title    # both show 75
    assert "ranked 1st of 3" in card(rows[1], board=b).title
    assert "ranked 3rd of 3" in card(rows[2], board=b).title


def test_non_shares_carry_no_earnings_points_on_the_recorded_board():
    for r in ROWS:
        if r["cls"] != "Equity":
            assert next(l for l in card(r).lines if l.key == "catalyst").points == 0, r["symbol"]


def test_a_non_share_with_earnings_points_is_logged(caplog):
    r = mk("X", "Forex", 0.01, .01, comp={"momentum": .5, "volatility": .5, "news": 0,
                                         "catalyst": 1.0}, confidence=0.0)
    r["confidence"] = round(100 * sum(A._W[k] * r["comp"].get(k, 0) for k in A._W), 1)
    card(r, board=board_of([r]))
    assert "not a share but carries" in caplog.text


def test_the_fallback_says_the_points_are_not_rounded():
    r = copy.deepcopy(row_of("NVDA"))
    r["confidence"] = 3.0
    assert card(r).rounding_note == W.FALLBACK_NOTE
    assert not banned_in(W.FALLBACK_NOTE) and not banned_in(W.NO_CALENDAR)


def test_a_part_with_no_fraction_never_gets_the_extra_point():
    """QA M2: a component that is already whole must not be rounded up, even when
    the target needs another point (the formula then does not reach it)."""
    comp = {"news": 0.4, "momentum": 0.5, "volatility": 0.0}   # 14.0, 15.0, 0.0
    assert W.allocate_points(comp, 29) == {"news": 14, "momentum": 15,
                                           "catalyst": 0, "volatility": 0}
    assert W.allocate_points(comp, 30) is None       # no part has a fraction to round up
    assert W.allocate_points(comp, 28) is None
