"""The second grade on screen: every protocol entry, graded at a fixed date.

`ShadowGrade` sits under the existing grade on the landing page and on My
trades (docs/specs/shadow-time-stop.md, Design D2–D7). These tests drive one
real window through every state of D3 by setting `Live.shadow` by hand — the
same dict the engine computes, or the holder sends — and read what the labels
say. Synthetic readouts only.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from sonar import core
from sonar.core import Live
from sonar.portfolio import Portfolio
from test_landing_figures import FORECAST_WORDS
from ui import words
from ui.app import SHADOW_WORDS, MainWindow, _sh_z

DAY = 86_400.0
NOW = time.time()
ROWS = [{"symbol": "AAA", "name": "Alpha", "price": 100.0, "volatility": 0.02,
         "confidence": 60.0, "cls": "Equity", "spark": [96, 97, 99, 98, 100]}]
# What the Screener needs on top to draw a row: refresh() draws the board in
# every engine state (closing UX C-1), as in test_portfolio_tab.
SCREEN = {"day_change": 0.01, "momentum": 0.05, "momentum_days": 5, "lean": "Normal",
          "comp": {"momentum": .5, "volatility": .3, "news": .8, "catalyst": .2},
          "data_age_s": 60.0, "plan": {"rr": 1.5, "p_profit": 0.4, "calibrated": False}}
BANNED = ("promised", "advertised", "profit", "certain", "guarantee")
#: Exactly the phrases SHADOW_WORDS may use "edge" in (domain review r2 N-4).
EDGE_ALLOWED = ("with no edge, exact fills and randomly wandering prices",
                "what no edge would give", "no edge @σ̂", "not a trading edge",
                "not a tradeable edge")


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    data = tmp_path_factory.mktemp("sonar-data")
    mp.setattr("sonar.paths.user_data_base", lambda: data)
    book = Portfolio(data / "portfolio.json")
    book.enter(ROWS[0], "LONG", 4, "week")
    gone, _ = book.enter({**ROWS[0], "symbol": "CCC", "name": "Gamma"}, "SHORT", 4, "week")
    book.close(gone.id, gone.target, "TARGET")
    QApplication.instance() or QApplication([])
    live = Live()
    win = MainWindow(live)
    win.poll.live.stop()
    win.poll.quit()
    win.poll.wait(3000)
    with live.lock:
        live.assets = {"status": "live", "assets": [{**r, **SCREEN} for r in ROWS]}
    live._mark_book({"assets": [dict(r) for r in ROWS]})
    win.refresh()
    yield win
    win.shutdown()
    mp.undo()


def look(k, n, entered=None, due=None, used=0, excluded=0, waiting=0, wait_price=0,
         evaluated=False, z=None, crossed=False, closed=False):
    entered = n if entered is None else entered
    return {"k": k, "n": n, "entered": entered, "n_missing": n - entered, "due": due,
            "used": used, "n_excluded": excluded, "n_waiting": waiting,
            "n_wait_price": wait_price, "evaluated": evaluated, "z": z,
            "crossed": crossed, "design_closed": closed}


def readout(**kw) -> dict:
    """A readout shaped as `calibration.shadow_time_stop` returns it."""
    d = {"n_entered": 51, "n_reached": 12, "n_target": 4, "n_stop": 6, "n_time": 2,
         "n_waiting": 39, "next_t": NOW + 2 * DAY, "n_wait_price": 0, "n_nonprotocol": 1,
         "n_left": 0, "n_no_price": 0, "n_gap": 0, "z": 0.84, "ic": 0.11,
         "ic_closed": -0.32, "n_closed_same": 10, "mean_r": 0.12, "mean_r_lo": -0.31,
         "mean_r_hi": 0.55, "ref": {"target": 0.374, "stop": 0.574, "neither": 0.052},
         "t_days": 28.0, "rr": 1.5, "boundary": 2.315,
         "looks": [look(1, 45, due=NOW + 25 * DAY, used=12), look(2, 101, entered=51),
                   look(3, 201, entered=51)],
         "bands": [{"lo": 0, "hi": 20, "n": 5, "target": 1, "stop": 3, "time": 1,
                    "ref": {"target": 0.374, "stop": 0.574, "neither": 0.052}},
                   {"lo": 80, "hi": 101, "n": 7, "target": 3, "stop": 3, "time": 1,
                    "ref": {"target": 0.374, "stop": 0.574, "neither": 0.052}}],
         "entries": [], "computed_at": NOW - 600, "error": None}
    d.update(kw)
    return d


def _evaluated(z1=0.84, crossed=False):
    closed = crossed
    return [look(1, 45, due=NOW - 30 * DAY, used=45, evaluated=True, z=z1, crossed=crossed),
            look(2, 101, due=NOW + 10 * DAY, used=60, closed=closed),
            look(3, 201, entered=120, used=60, closed=closed)]


STATES = {
    "not available": core.SHADOW_UNAVAILABLE,
    "loading": None,
    "error, nothing yet": {"error": "RuntimeError"},
    "error, last good": readout(error="RuntimeError"),
    "a1 empty": readout(n_entered=0, n_reached=0, n_target=0, n_stop=0, n_time=0,
                        n_waiting=0, next_t=None, n_nonprotocol=0, t_days=None, ref=None,
                        mean_r=None, mean_r_lo=None, mean_r_hi=None, z=None, ic=None,
                        bands=[], looks=[look(1, 45, entered=0), look(2, 101, entered=0),
                                         look(3, 201, entered=0)]),
    "a2 none at T": readout(n_reached=0, n_target=0, n_stop=0, n_time=0, n_waiting=51,
                            ref=None, mean_r=None, z=None, ic=None, bands=[],
                            looks=[look(1, 45, due=NOW + 25 * DAY), look(2, 101, entered=51),
                                   look(3, 201, entered=51)]),
    "a3 before look 1": readout(),
    "a3 before look 1, undated": readout(
        n_entered=30, n_waiting=18,
        looks=[look(1, 45, entered=30, used=12), look(2, 101, entered=30),
               look(3, 201, entered=30)]),
    "f look due, prices missing": readout(
        n_reached=42, n_wait_price=3, n_waiting=6,
        looks=[look(1, 45, due=NOW - DAY, used=42, wait_price=3), look(2, 101, entered=51),
               look(3, 201, entered=51)]),
    "c not crossed": readout(n_entered=130, n_reached=105, n_waiting=25, looks=_evaluated()),
    "c not crossed, next undated": readout(
        n_entered=80, n_reached=60, n_waiting=20,
        looks=[look(1, 45, due=NOW - 30 * DAY, used=45, evaluated=True, z=-1.2),
               look(2, 101, entered=80, used=40), look(3, 201, entered=80, used=40)]),
    "c crossed up": readout(n_entered=60, n_reached=45, looks=_evaluated(2.61, True)),
    "c crossed down": readout(n_entered=60, n_reached=45, looks=_evaluated(-2.61, True)),
    "d closed, no crossing": readout(
        n_entered=210, n_reached=201, n_waiting=9,
        looks=[look(1, 45, due=NOW - 90 * DAY, used=45, evaluated=True, z=0.4),
               look(2, 101, due=NOW - 60 * DAY, used=101, evaluated=True, z=1.1),
               look(3, 201, due=NOW - DAY, used=201, evaluated=True, z=-0.3)]),
}


def show(win, shadow) -> dict:
    with win.live.lock:
        win.live.shadow = shadow
    win._refresh_portfolio()
    win._refresh_book()
    out = {}
    for page, w in (("landing", win.shadow_grade), ("book", win.book_shadow)):
        out[page] = {"count": w.shadow_count.text(), "status": w.shadow_status.text(),
                     "rows": w.shadow_rows.text(), "warn": w.shadow_warn.text(),
                     "warn_shown": not w.shadow_warn.isHidden(),
                     "note": w.shadow_note.text()}
    return out


def grade_texts(win) -> tuple:
    return (win.grade_verdict.text(), win.grade_rows.text(), win.grade_next.text(),
            win.grade_count.text(), win.cal_verdict.text(), win.cal_table.text())


def _all_text(t: dict) -> str:
    return "\n".join(v for page in t.values() for k, v in page.items() if k != "warn_shown")


def _check_words(text: str, where: str) -> None:
    low = text.lower()
    for w in FORECAST_WORDS + BANNED:
        assert w not in low, f"{w!r} in {where}: {text!r}"
    rest = low
    for ok in EDGE_ALLOWED:
        rest = rest.replace(ok, "")
    assert "edge" not in rest, f"'edge' outside its allowed phrases in {where}: {text!r}"


@pytest.mark.parametrize("mode", [words.PLAIN, words.EXPERT])
def test_u1_no_forecast_edge_or_profit_words_anywhere(window, monkeypatch, mode):
    """U-1. Every string, both modes, and every state's rendered text."""
    monkeypatch.setattr(words, "_mode", mode)
    for key, pair in SHADOW_WORDS.items():
        _check_words(words.pick(pair), key)
    for name, shadow in STATES.items():
        _check_words(_all_text(show(window, shadow)), name)


def test_u2_the_existing_grade_reads_the_same_with_the_shadow_present(window):
    """U-2 (and V-11 on screen): TESTPLAN 11.9 still holds. Kills: a shadow
    that writes into, reorders or rewords the existing grade."""
    show(window, None)
    before = grade_texts(window)
    for name, shadow in STATES.items():
        show(window, shadow)
        assert grade_texts(window) == before, name


def test_u2_the_block_comes_after_every_existing_widget(window):
    for panel_child, last_existing in ((window.shadow_grade, window.grade_next),
                                       (window.book_shadow, window.bt_result)):
        lay = panel_child.parentWidget().layout()
        idx = [lay.itemAt(i).widget() for i in range(lay.count())]
        assert idx.index(panel_child) == idx.index(last_existing) + 1 == len(idx) - 1


def test_u3_landing_and_my_trades_say_the_same_sentence(window):
    """U-3 (TESTPLAN 11.14; the spec calls it 11.9b)."""
    for name, shadow in STATES.items():
        t = show(window, shadow)
        assert t["landing"]["status"] == t["book"]["status"], name


def _status(win, name):
    return show(win, STATES[name])["landing"]["status"]


def test_u4_each_state_says_its_own_sentence(window):
    """U-4: one assertion per row of D3."""
    s = {name: _status(window, name) for name in STATES}
    assert s["not available"].startswith("Not available from the running agent")
    assert s["loading"].startswith("Working it out")
    assert s["error, nothing yet"].startswith("Could not work it out this time (RuntimeError)")
    assert s["error, last good"].startswith("Could not work it out this time")
    assert "Not a test yet. 12 of the first 45" in s["error, last good"]
    assert s["a1 empty"].startswith("Not a test yet: there are no protocol entries")
    assert s["a2 none at T"].startswith("Not a test yet. None of the 51 entries has had 4 weeks")
    assert "the first look is on or after" in s["a3 before look 1"]
    assert "15 of them are not entered yet" in s["a3 before look 1, undated"]
    assert "The first look is due; 3 of its 45 entries are still waiting" in \
        s["f look due, prices missing"]
    assert s["c not crossed"].startswith("Look 1 of 3, first 45 entries (45 with a result): "
                                         "no link strong enough to cross the line yet")
    assert "Next look: the first 101 entries, on or after" in s["c not crossed"]
    assert "after 21 more are entered" in s["c not crossed, next undated"]
    assert "On these paper entries, higher scores went with higher R on average." in s["c crossed up"]
    assert "On these paper entries, higher scores went with lower R on average." in s["c crossed down"]
    for name in ("c crossed up", "c crossed down"):
        assert "It is not a trading edge." in s[name] and "crossed the line" in s[name]
    assert "no evidence that the score ranks 4-week results, at the planned size" in \
        s["d closed, no crossing"]


def test_u4_not_a_test_yet_until_a_look_is_evaluated(window):
    for name in ("a1 empty", "a2 none at T", "a3 before look 1", "a3 before look 1, undated",
                 "f look due, prices missing"):
        assert "Not a test yet" in _status(window, name), name
    for name in ("c not crossed", "c crossed up", "d closed, no crossing"):
        assert "Not a test yet" not in _status(window, name), name


def test_u4_the_running_row_always_says_not_a_test(window):
    shown = 0
    for name, shadow in STATES.items():
        rows = show(window, shadow)["book"]["rows"]
        for line in rows.splitlines():
            if "95% range" in line or "mean R " in line:
                shown += 1
                assert line.startswith("running, not a test"), (name, line)
    assert shown >= 4


def test_u4_running_figures_wait_for_twenty_results(window):
    rows = show(window, readout())["landing"]["rows"]
    assert "running figures start at 20 results; 8 to go" in rows
    assert "rank correlation" not in rows
    rows = show(window, STATES["c not crossed"])["landing"]["rows"]
    assert ("running, not a test: paper average +0.12R (95% range for the average -0.31 to "
            "+0.55R)") in rows
    assert ("link z = +0.84 · before costs; an average above 0 here is not a trading edge"
            in rows)
    assert "rank correlation +0.11 on these entries at 4 weeks, -0.32 on the closed ones" in rows


def test_u4_past_looks_are_listed_under_the_sentence(window):
    rows = show(window, STATES["d closed, no crossing"])["landing"]["rows"]
    assert [ln for ln in rows.splitlines() if ln.startswith("look ")] == [
        "look 1, first 45: z = +0.40, did not cross the line",
        "look 2, first 101: z = +1.10, did not cross the line",
        "look 3, first 201: z = -0.30, did not cross the line"]


@pytest.mark.parametrize("field,text", [
    ("n_nonprotocol", "3 chosen by hand"), ("n_left", "3 closed by hand before 4 weeks"),
    ("n_no_price", "3 with no closing price"),
    ("n_gap", "3 counted at the target or stop price because a daily close went past it "
              "between checks (a real fill could have been different, often worse at a stop)"),
])
def test_u5_every_exclusion_is_shown(window, field, text):
    """U-5. Kills: hiding a non-zero exclusion or gap count."""
    base = {"n_nonprotocol": 0, "n_left": 0, "n_no_price": 0, "n_gap": 0}
    rows = show(window, readout(**{**base, field: 3}))["landing"]["rows"]
    assert text in rows
    clean = show(window, readout(**base))["landing"]["rows"]
    assert "left out" not in clean and "graded at the target or stop" not in clean


@pytest.mark.parametrize("excluded,shown", [(5, True), (4, False)])
def test_u5_a_look_with_over_a_tenth_left_out_says_so(window, excluded, shown):
    looks = [look(1, 45, due=NOW - 30 * DAY, used=45 - excluded, excluded=excluded,
                  evaluated=True, z=0.5),
             look(2, 101, entered=60), look(3, 201, entered=60)]
    t = show(window, readout(n_reached=40, looks=looks))
    assert t["landing"]["warn_shown"] is shown and t["book"]["warn_shown"] is shown
    if shown:
        assert t["landing"]["warn"] == ("Note: 5 of the first 45 entries were left out "
                                        "(11%). This look rests on the other 40.")


def test_u6_no_reference_means_no_reference_line_and_no_dash(window):
    """U-6. Kills: a dashed placeholder where the reference would be."""
    bands = [{"lo": 0, "hi": 20, "n": 5, "target": 1, "stop": 3, "time": 1, "ref": None}]
    t = show(window, readout(ref=None, bands=bands))
    for page in t.values():
        assert "what no edge would give" not in page["rows"]
        assert "—" not in page["rows"] and "n/a" not in page["rows"]
    assert "scores 0-20: 5 with a result · 1 target · 3 stop · 1 neither" in t["book"]["rows"]


def test_u6_the_reference_and_the_bands_when_present(window):
    t = show(window, readout())
    assert ("what no edge would give after 4 weeks, if the volatility estimate was right: "
            "about 37% at the target · 57% at the stop · 5% at neither. A different split "
            "can mean the volatility estimate was off. With no edge, exact fills and "
            "randomly wandering prices, the average result would be about 0R.") \
        in t["landing"]["rows"]
    assert ("· what no edge would give if the volatility estimate was right: 37% / 57% / 5%"
            in t["book"]["rows"])
    assert "scores 80-100:" in t["book"]["rows"] and "scores" not in t["landing"]["rows"]


@pytest.mark.parametrize("z,crossed,text", [(2.3149, False, "+2.314"), (2.3151, True, "+2.315"),
                                            (-2.3151, True, "-2.315"), (2.3, False, "+2.30"),
                                            (2.315, True, "+2.315"), (0.8449, False, "+0.84")])
def test_u7_z_near_the_line_never_contradicts_the_verdict(z, crossed, text):
    """U-7. Kills: rounding 2.3149 up to a "2.315" that did not cross."""
    assert _sh_z(z, crossed) == text


def test_u7_the_sentence_follows_the_unrounded_decision(window):
    near = [look(1, 45, due=NOW - 30 * DAY, used=45, evaluated=True, z=2.3149),
            look(2, 101, entered=60), look(3, 201, entered=60)]
    s = show(window, readout(n_reached=45, looks=near))["landing"]["status"]
    assert "no link strong enough" in s and "z = +2.314" in s
    near[0].update(z=2.3151, crossed=True)
    near[1]["design_closed"] = near[2]["design_closed"] = True
    s = show(window, readout(n_reached=45, looks=near))["landing"]["status"]
    assert "crossed the line" in s and "z = +2.315" in s


def test_u8_the_block_does_not_widen_either_page(window):
    """U-8: every label in the block wraps, so its longest state is no wider
    than its shortest. A page's minimum is the widest of its children's, and
    an unwrapped sentence here would set it — on My trades directly, since
    its grade panel does not scroll. The pages themselves are held to
    1280 pt by test_layout."""
    blocks = (window.shadow_grade, window.book_shadow)
    show(window, None)
    base = [b.minimumSizeHint().width() for b in blocks]
    for name, shadow in STATES.items():
        show(window, shadow)
        for block, was in zip(blocks, base, strict=True):
            assert block.minimumSizeHint().width() <= was, name
            for lb in block.findChildren(QLabel):
                assert lb.wordWrap() or lb is block.shadow_count or lb is block.heading, \
                    lb.text()[:60]
    assert max(base) <= 1280


def test_the_note_says_when_and_goes_stale(window):
    t = show(window, readout())["landing"]["note"]
    assert t.startswith("R is the result in units of the amount risked: -1R lost the "
                        "amount risked, +1.5R reached the target.")
    assert "Worked out" in t
    t = show(window, readout(computed_at=NOW - 30 * 3600))["landing"]["note"]
    assert "Not updated for 30 hours: the agent may be stopped." in t


def test_payload_text_is_never_markup(window):
    """The dict can come from another process: its one string is cleaned as
    the untrusted-text sweep cleans every such string (no angle brackets, no
    control characters, 80 at most — code review r2 P3-5), and labels never
    interpret markup."""
    t = show(window, readout(error="<b>bold</b><img src=x>\n" + "y" * 200))
    status = t["landing"]["status"]
    assert "bold" in status and "<" not in status and "\n" not in status
    assert "y" * 81 not in status
    for w in (window.shadow_grade, window.book_shadow):
        for lb in (w.shadow_count, w.shadow_status, w.shadow_rows, w.shadow_warn,
                   w.shadow_note):
            assert lb.textFormat() == Qt.PlainText


@pytest.mark.parametrize("junk", [
    {"n_entered": "51", "n_reached": "x"},
    {"n_entered": 5, "n_reached": 2, "looks": "nope", "bands": [None, 3]},
    {"n_entered": 5, "n_reached": 25, "mean_r": float("nan"), "z": "1e9", "ref": []},
    {"n_entered": 5, "n_reached": 2, "looks": [{"k": "1", "due": "soon", "n": None}]},
    {"n_entered": 50, "n_reached": 30, "looks": [], "computed_at": 1e17},
    {"n_entered": 3, "n_reached": 0, "n_waiting": 3, "next_t": 1e17, "looks": []},
    {"n_entered": 50, "n_reached": 30, "computed_at": 1e18,
     "looks": [{"k": 1, "n": 45, "entered": 45, "due": 1e18, "used": 30}]},
    {"n_entered": 50, "n_reached": 30, "computed_at": -1e12, "looks": []},
])
def test_a_damaged_readout_is_never_a_crash(window, junk):
    t = show(window, junk)
    assert t["landing"]["status"]
    assert "nan" not in _all_text(t).lower()


@pytest.mark.parametrize("name", list(STATES))
def test_both_wordings_keep_the_same_rows(window, monkeypatch, name):
    """D5: the expert wording changes words, not the rows or their order."""
    plain = show(window, STATES[name])["book"]
    monkeypatch.setattr(words, "_mode", words.EXPERT)
    expert = show(window, STATES[name])["book"]
    assert len(plain["rows"].splitlines()) == len(expert["rows"].splitlines())
    assert bool(plain["warn"]) == bool(expert["warn"])
    assert "before costs, fees and slippage" in plain["note"]
    assert "before costs, fees and slippage; exact fills" in expert["note"]


def test_the_block_is_announced_and_its_heading_links_to_the_manual(window):
    assert window.shadow_grade.accessibleName() == "Second grade, every entry at a fixed date"
    assert window.shadow_grade.heading._anchor == "grading"
    assert window.shadow_grade.heading.text() in SHADOW_WORDS["SH_HEAD"]


@pytest.mark.parametrize("t,words_", [
    (28.0, ("4 weeks", "4-week")), (112.0, ("16 weeks", "16-week")),
    (5.6, ("5.6 days", "5.6-day")), (336.0, ("336 days", "336-day")),
    (None, ("4 holding periods", "fixed-time"))])
def test_t_in_words(t, words_):
    """D4: {T} and {T_adj} per preset; one readout mixing T says so."""
    from ui.app import _sh_t_words
    assert _sh_t_words(t) == words_


def test_a_date_in_another_year_carries_its_year():
    from ui.app import _sh_date
    later = NOW + 400 * DAY
    assert _sh_date(later, NOW).endswith(time.strftime("%Y", time.localtime(later)))
    assert len(_sh_date(NOW, NOW).split()) == 2
    assert _sh_date(None, NOW) == "n/a"


@pytest.mark.parametrize("z,crossed,text", [(2.3149999, True, "+2.315"), (2.3151, False, "+2.314"),
                                            (None, None, "n/a")])
def test_u7_the_shown_z_is_clamped_to_the_verdicts_side(z, crossed, text):
    """The decision is the engine's, on the unrounded value; the figure never
    contradicts it, even where cutting to three places would."""
    assert _sh_z(z, crossed) == text


def test_a_readout_this_build_cannot_read_is_said_not_half_shown(window, monkeypatch):
    import ui.app as app_mod
    real = app_mod.shadow_texts
    calls = []

    def flaky(shadow, *a):
        calls.append(shadow)
        if len(calls) == 1:
            raise KeyError("looks")
        return real(shadow, *a)

    monkeypatch.setattr(app_mod, "shadow_texts", flaky)
    window.shadow_grade.render(readout(), 28.0, NOW)
    assert window.shadow_grade.shadow_status.text().startswith(
        "Could not work it out this time (unreadable)")


@pytest.mark.parametrize("caveat", ["paper entries", "before costs, fees and slippage",
                                    "with exact fills", "can cross by chance",
                                    "It is not a trading edge."])
def test_domain_p1_the_crossing_says_what_it_does_not_show(window, caveat):
    """Domain review P1-1: beside a crossing, the copy says the figures are
    past paper entries, before costs and fills, from one test that can cross
    by chance — and never states a false-alarm rate."""
    for name in ("c crossed up", "c crossed down"):
        status = show(window, STATES[name])["landing"]["status"]
        assert caveat in status, name
        assert "%" not in status, name
    note = show(window, STATES["c crossed up"])["landing"]["note"]
    assert "the direction was random" not in note
    assert "says nothing about how future entries end" in note


def test_the_existing_grade_is_refreshed_before_the_shadow(window, monkeypatch):
    """Code review P2-2: whatever the shadow block does, the existing grade
    has already been brought up to date on both pages."""
    show(window, None)

    def boom(*a, **k):
        raise RuntimeError("shadow")

    with window.live.lock:
        window.live.calibration = {**window.live.calibration, "verdict": "fresh verdict"}
    for w in (window.shadow_grade, window.book_shadow):
        monkeypatch.setattr(w, "render", boom)
    with pytest.raises(RuntimeError):
        window._refresh_portfolio()
    with pytest.raises(RuntimeError):
        window._refresh_book()
    assert window.grade_verdict.text() == "fresh verdict"
    assert window.cal_verdict.text() == "fresh verdict"


def test_an_impossible_date_reads_as_n_a_not_as_a_failure(window):
    """Security P2-1 / code review P2-2: a timestamp past ~1e17 makes
    `time.localtime` raise. It is shown as n/a and the rest of the readout
    renders as usual. Kills: dropping the bound on payload timestamps."""
    t = show(window, readout(n_reached=0, n_target=0, n_stop=0, n_time=0, ref=None,
                             mean_r=None, z=None, ic=None, bands=[], next_t=1e17,
                             computed_at=1e17,
                             looks=[look(1, 45, due=NOW + 25 * DAY), look(2, 101, entered=51),
                                    look(3, 201, entered=51)]))["landing"]
    assert t["status"].startswith("Not a test yet. None of the 51 entries")
    assert "first gets there on n/a" in t["status"]
    assert "Worked out" not in t["note"] and "Could not" not in t["status"]


def test_qa_u01_a_due_look_waiting_for_prices_comes_before_the_last_result(window):
    """QA U01, D3 order: (f) "look due, prices missing" outranks (c)."""
    looks = [look(1, 45, due=NOW - 40 * DAY, used=45, evaluated=True, z=0.6),
             look(2, 101, due=NOW - DAY, used=98, wait_price=3), look(3, 201, entered=130)]
    s = show(window, readout(n_entered=130, n_reached=110, n_wait_price=3,
                             looks=looks))["landing"]
    assert s["status"].startswith("Not a test yet. The second look is due; 3 of its 101")
    assert "look 1, first 45: z = +0.60, did not cross the line" in s["rows"]


def test_qa_u04_the_tenth_left_out_warning_shows_on_a_due_look_too(window):
    """QA U04, D3 (h): "for an evaluated or due look"."""
    looks = [look(1, 45, due=NOW - DAY, used=38, excluded=5, wait_price=2),
             look(2, 101, entered=60), look(3, 201, entered=60)]
    t = show(window, readout(n_reached=38, n_wait_price=2, looks=looks))["landing"]
    assert t["warn_shown"] and t["warn"].startswith("Note: 5 of the first 45 entries")
    looks[0]["due"] = NOW + DAY                              # not due yet: no warning
    assert not show(window, readout(n_reached=38, looks=looks))["landing"]["warn_shown"]


def test_qa_u05_none_at_t_is_not_said_while_entries_wait_for_a_price(window):
    """QA U05: entries past T, waiting for a close, have had their T."""
    s = show(window, readout(n_reached=0, n_target=0, n_stop=0, n_time=0, n_wait_price=2,
                             n_waiting=49, ref=None, mean_r=None, z=None, ic=None,
                             bands=[]))["landing"]["status"]
    assert "None of the" not in s and "of the first 45 entries have a result" in s


def test_qa_u08_two_looks_are_not_three(window):
    """QA U08: "The test is finished" only once all three looks are evaluated."""
    looks = [look(1, 45, due=NOW - 90 * DAY, used=45, evaluated=True, z=0.4),
             look(2, 101, due=NOW - 60 * DAY, used=101, evaluated=True, z=1.1),
             look(3, 201, entered=150, used=120)]
    s = show(window, readout(n_entered=150, n_reached=130, looks=looks))["landing"]["status"]
    assert "The test is finished" not in s and s.startswith("Look 2 of 3")


def test_qa_u09_the_past_look_row_never_repeats_the_named_look(window):
    t = show(window, STATES["c not crossed"])["landing"]
    assert t["status"].startswith("Look 1 of 3")
    assert "look 1, first 45" not in t["rows"]


def test_u2_a_grade_with_a_verdict_reads_the_same_with_the_shadow_present(window):
    """QA on U-2: the existing grade with enough closes for a verdict (25
    graded), compared in every shadow state."""
    from sonar import calibration
    from sonar.portfolio import Position
    closed = [Position(id=f"g{i}", symbol="AAA", name="A", direction="LONG", units=1.0,
                       entry=100.0, target=103.0, stop=98.0, opened_at=0.0,
                       cash_at_risk=2.0, confidence=float(4 * i), rr=1.5, p_profit=0.4,
                       horizon="week", protocol=True, closed_at=1.0,
                       exit=103.0 if i % 3 == 0 else 98.0,
                       pnl=3.0 if i % 3 == 0 else -2.0,
                       outcome="TARGET" if i % 3 == 0 else "STOP") for i in range(25)]
    report = calibration.report(closed)
    assert report["enough"] is True and report["n_settled"] == 25
    with window.live.lock:
        saved = window.live.calibration
        window.live.calibration = report
    try:
        show(window, None)
        before = grade_texts(window)
        assert before[0] == report["verdict"] and before[4] == report["verdict"]
        for name, shadow in STATES.items():
            show(window, shadow)
            assert grade_texts(window) == before, name
    finally:
        with window.live.lock:
            window.live.calibration = saved


def test_qa_n20_a_negative_timestamp_reads_n_a():
    """QA r2 N20: the clamp's lower bound. Without it, -1 is 31 Dec 1969."""
    from ui.app import _sh_date
    assert _sh_date(-1.0, NOW) == "n/a" and _sh_date(0.0, NOW) != "n/a"


def test_domain_n2_the_caveat_covers_a_downward_crossing_too(window):
    """Domain r2 N-2: one caveat for both directions, so it negates trading
    by score, not only trading high scores."""
    for name in ("c crossed up", "c crossed down"):
        status = show(window, STATES[name])["landing"]["status"]
        assert "trading by score would make money" in status
        assert "high scores would make money" not in status


# --------------------------------------------------------------------------- #
# The entry-date window (domain r2 P2-2; owner decision 2026-10-12)
# --------------------------------------------------------------------------- #
def _noon(y, m, d):
    from datetime import datetime
    return datetime(y, m, d, 12).timestamp()            # local noon: no date shift


def _entries(*spec):
    return [{"id": f"w{i}", "opened_at": t, "state": state} for i, (t, state) in enumerate(spec)]


def test_window_names_the_period_of_the_graded_entries(window, monkeypatch):
    """Graded entries set the period when there are any; the not-yet-graded
    later ones do not stretch it."""
    from ui.app import shadow_texts
    now = _noon(2026, 12, 1)
    entries = _entries((_noon(2026, 9, 22), "time"), (_noon(2026, 10, 3), "stop"),
                       (_noon(2026, 11, 20), "waiting"))
    rows = shadow_texts(readout(entries=entries), False, now, 28.0)["rows"].splitlines()
    assert rows[0] == "the 2 with a result opened 22 Sep to 3 Oct"
    monkeypatch.setattr(words, "_mode", words.EXPERT)
    rows = shadow_texts(readout(entries=entries), False, now, 28.0)["rows"].splitlines()
    assert rows[0] == "2 graded: opened 22 Sep to 3 Oct"


def test_window_with_nothing_graded_spans_every_entry():
    from ui.app import shadow_texts
    now = _noon(2026, 10, 12)
    entries = _entries((_noon(2026, 9, 22), "waiting"), (_noon(2026, 10, 11), "left"))
    t = shadow_texts(readout(n_reached=0, entries=entries), False, now, 28.0)
    assert t["rows"].splitlines()[0] == ("entries opened 22 Sep to 11 Oct "
                                         "(none has a result yet)")
    words._mode, keep = words.EXPERT, words._mode
    try:
        t = shadow_texts(readout(n_reached=0, entries=entries), False, now, 28.0)
    finally:
        words._mode = keep
    assert t["rows"].splitlines()[0] == "opened 22 Sep to 11 Oct (none graded yet)"


def test_window_across_the_new_year_carries_the_year():
    from ui.app import shadow_texts
    now = _noon(2027, 2, 1)
    entries = _entries((_noon(2026, 12, 20), "time"), (_noon(2027, 1, 5), "target"))
    rows = shadow_texts(readout(entries=entries), True, now, 28.0)["rows"]
    assert rows.splitlines()[0] == "the 2 with a result opened 20 Dec 2026 to 5 Jan"


@pytest.mark.parametrize("bad", ["x", 1e18, -5.0, None, float("nan")])
def test_window_reads_n_a_for_a_bad_date_never_raises(bad):
    from ui.app import shadow_texts
    t = shadow_texts(readout(entries=_entries((bad, "time"))), False, NOW, 28.0)
    assert t["rows"].splitlines()[0] == "the 1 with a result opened n/a to n/a"


def test_window_is_hidden_with_no_entries(window):
    for name, shadow in STATES.items():
        assert "opened" not in show(window, shadow)["book"]["rows"], name


@pytest.mark.parametrize("mode", [words.PLAIN, words.EXPERT])
def test_window_obeys_the_banned_words(window, monkeypatch, mode):
    monkeypatch.setattr(words, "_mode", mode)
    entries = _entries((_noon(2026, 9, 22), "time"), (_noon(2026, 10, 3), "stop"))
    _check_words(_all_text(show(window, readout(entries=entries))), "window")


def test_window_on_a_follower_comes_from_the_holders_payload(window, monkeypatch):
    """The follower computes nothing: the window is read from the mirrored
    readout's entries."""
    entries = _entries((_noon(2026, 9, 22), "time"), (_noon(2026, 10, 3), "stop"))
    payload = {"shadow": readout(entries=entries)}
    monkeypatch.setattr(core.Live, "_fetch", staticmethod(lambda url, path: payload))
    window.live._mirror_book("http://holder")
    window._refresh_portfolio()
    window._refresh_book()
    for w in (window.shadow_grade, window.book_shadow):
        first = w.shadow_rows.text().splitlines()[0]
        assert first.startswith("the 2 with a result opened 22 Sep") and "3 Oct" in first
