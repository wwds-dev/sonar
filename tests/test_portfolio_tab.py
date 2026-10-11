"""The landing page is the reader's own money.

Until Oct 2026 the app opened on the hourly bitcoin model — an experiment the
engine runs, not something the reader holds. Now it opens on the paper book:
the figures as a hierarchy, the account's value over time, every position as a
tile and as a card. These tests build the real window over a book with
positions in it, because the page is only as good as the data it reads.
"""

from __future__ import annotations

import itertools
import re
import time
from dataclasses import asdict

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from sonar import calibration
from sonar.core import Live
from sonar.portfolio import Portfolio, Position
from ui.app import MainWindow, PositionCard

ROWS = [{"symbol": "AAA", "name": "Alpha", "price": 100.0, "volatility": 0.02,
         "confidence": 60.0, "cls": "Equity", "spark": [96, 97, 99, 98, 100]},
        {"symbol": "BBB", "name": "Beta", "price": 50.0, "volatility": 0.03,
         "confidence": 40.0, "cls": "Equity", "spark": [52, 51, 50, 49, 50]}]


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    data = tmp_path_factory.mktemp("sonar-data")
    mp.setattr("sonar.paths.user_data_base", lambda: data)
    # A book with one open position per row and one that already resolved.
    book = Portfolio(data / "portfolio.json")
    for row in ROWS:
        book.enter(row, "LONG", 4, "week")
    gone, _ = book.enter({**ROWS[0], "symbol": "CCC", "name": "Gamma"}, "SHORT", 4, "week")
    book.close(gone.id, gone.target, "TARGET")
    QApplication.instance() or QApplication([])
    live = Live()
    win = MainWindow(live)
    win.poll.live.stop()
    win.poll.quit(); win.poll.wait(3000)
    # What a scan would have left behind: the board, and the book marked on it.
    with live.lock:
        live.assets = {"status": "live", "assets": [dict(r) for r in ROWS]}
    live._mark_book({"assets": [dict(r) for r in ROWS]})
    win.refresh()
    yield win
    win.shutdown()
    mp.undo()


def test_the_app_opens_on_the_readers_investments(window):
    bar = window.tabs.tabBar()
    assert window.tabs.tabText(0) == "My investments"
    assert bar._subtitles.get(0) == "PORTFOLIO"
    assert window.tabs.currentIndex() == 0


def test_no_tab_is_about_one_asset_any_more(window):
    names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert "Live model" not in names
    assert window.tabs.count() == 8


def test_the_strip_reads_the_book(window):
    assert window.pstats["equity"].val.text().startswith("$")
    assert window.pstats["closed"].val.text() == "1"
    assert "1 won" in window.plines["closed"].text()
    assert "2 longs" in window.plines["invested"].text()
    assert "2 stops set" in window.plines["at risk"].text()
    assert window.pstats["at risk"].val.text().startswith("-$")


def test_every_open_position_has_a_card_and_a_tile(window):
    assert set(window._cards) == {p["id"] for p in window.live.positions["open"]}
    assert all(isinstance(c, PositionCard) for c in window._cards.values())
    assert [r["symbol"] for r in window.tiles.rows] == ["AAA", "BBB"] or \
           [r["symbol"] for r in window.tiles.rows] == ["BBB", "AAA"]
    assert "2 open" in window.tiles_line.text()


def test_the_cards_update_in_place_rather_than_being_rebuilt(window):
    before = dict(window._cards)
    rows = [dict(r, price=r["price"] * 1.05) for r in ROWS]
    window.live._mark_book({"assets": rows})
    window.refresh()
    assert dict(window._cards) == before
    assert all(c.pnl.text().startswith("+") for c in window._cards.values())


def test_a_resolved_position_is_listed_as_recently_closed(window):
    texts = []
    for i in range(window._closed_lay.count()):
        w = window._closed_lay.itemAt(i).widget()
        if w is not None:
            texts.append(" ".join(lb.text() for lb in w.findChildren(type(window.closed_line))))
    assert any("Gamma" in t and "hit target" in t for t in texts)
    assert window.closed_line.text() == "last 1 of 1"


def test_the_curve_gets_the_books_points(window):
    """`_mark_book` logs a point once every held position has a price."""
    assert window.live.positions["equity"], "no account-value point was logged"
    assert window.account_curve.points == window.live.positions["equity"]


def test_closing_from_a_card_goes_through_the_book(window):
    pid = next(iter(window._cards))
    window._close_position(pid)
    window.refresh()
    assert pid not in window._cards
    assert window.pstats["closed"].val.text() == "2"


def test_the_hourly_model_lives_under_practice_now(window):
    assert window._lab_scroll.isAncestorOf(window.read_panel)
    assert window._lab_scroll.isAncestorOf(window.equity)       # its bankroll curve
    assert window.tabs.tabText(window._lab_index) == "Practice"


def test_an_llm_read_brings_the_reader_to_the_model(window, monkeypatch):
    monkeypatch.setattr("sonar.llm.available", lambda: (False, "no key"))
    window.tabs.setCurrentIndex(0)
    window._read("btc", "", "BTC/USD hourly up-or-down")
    assert window.tabs.currentIndex() == window._lab_index
    assert window.read_panel.isVisibleTo(window)


# --------------------------------------------------------------------------- #
# Is the score right? — the question the app exists to answer, on its first page
# --------------------------------------------------------------------------- #
def test_the_first_screen_grades_the_score(window):
    from ui.app import HelpHeading
    heads = [h for h in window.findChildren(HelpHeading) if h._anchor == "grading"]
    assert heads, "no heading links the grading section of the manual"
    assert window.grade_verdict.text().startswith("Not enough resolved positions yet")
    assert "of the 20 closed positions a verdict needs" in window.grade_next.text()
    assert "scores " in window.grade_rows.text() and "the plan promised" in window.grade_rows.text()
    assert "graded" in window.grade_count.text()


FORECAST_WORDS = ("will", "should", "buy", "sell", "expect", "likely",
                  "going to", "bullish", "bearish")


def test_the_grade_never_reads_as_a_forecast(window):
    """Measurement, in words that describe the past. The one rule."""
    text = " ".join(lb.text().lower() for lb in
                    (window.grade_verdict, window.grade_rows, window.grade_next))
    for forecast in FORECAST_WORDS:
        assert forecast not in text, f"{forecast!r} in the grade panel"


def test_the_grade_names_protocol_mode_either_way(window):
    on = window.live.protocol_on
    try:
        window.live.protocol_on = True
        window._refresh_grade(window.live.calibration, window.live.positions["closed"],
                              window.live.positions["open"])
        assert "protocol mode is on" in window.grade_next.text()
        window.live.protocol_on = False
        window._refresh_grade(window.live.calibration, window.live.positions["closed"],
                              window.live.positions["open"])
        assert "protocol mode is off" in window.grade_next.text()
    finally:
        window.live.protocol_on = on


# --------------------------------------------------------------------------- #
# The grade is made of the positions that closed — say how many have not
# --------------------------------------------------------------------------- #
# `calibration.report` grades closed positions only, and the book has no time
# stop, so how long a position takes to close depends on its score. On the live
# book 54% / 40% / 14% of the entries had closed across the 0–20 / 40–60 /
# 60–80 bands (docs/audit/calibration-censoring-by-score.md): the hit rates and
# the rank correlation were read off the quick ones. The panel shows it.
_ids = itertools.count()


def _closed(score, outcome="TARGET", p_profit=0.33):
    """A position that reached a barrier, as the calibration report grades it."""
    return Position(id=f"c{next(_ids)}", symbol="X", name="X", direction="LONG",
                    units=1.0, entry=100.0, target=104.0, stop=98.0,
                    opened_at=1.0, cash_at_risk=2.0, confidence=score, rr=2.0,
                    p_profit=p_profit, horizon="week", closed_at=2.0,
                    exit=104.0 if outcome == "TARGET" else 98.0,
                    pnl=4.0 if outcome == "TARGET" else -2.0, outcome=outcome)


def _open(score, days):
    """An open row as `Portfolio.open_rows` serves it: score, entry time, age."""
    age = days * 86400
    return {"confidence": score, "opened_at": time.time() - age, "age_s": age}


@pytest.fixture
def grade(window):
    """Draw the grade panel from a book the test builds, then put the real one
    back: the window is shared by the whole module."""
    def draw(closed, open_rows):
        cal = calibration.report(closed)
        latest = [asdict(p) for p in closed[-40:]][::-1]     # what the engine hands over
        window._refresh_grade(cal, latest, open_rows)
        return window.grade_rows.text().splitlines(), window.grade_next.text()
    yield draw
    window._refresh_portfolio()


def test_each_band_says_how_many_were_entered_closed_and_are_still_open(grade):
    closed = [_closed(10), _closed(10), _closed(10, "STOP"), _closed(70)]
    opened = [_open(10, 2), _open(10, 4), _open(30, 0.125),
              _open(70, 10), _open(70, 12), _open(70, 80)]
    rows, _ = grade(closed, opened)
    assert rows == [
        "scores 0–20:  5 entered, 2 still open (median age 3.0 days) · 3 closed · "
        "2 won (67%) · the plan promised 33%   (a band needs 20 to count)",
        "scores 20–40:  1 entered, 1 still open (median age 3 hours) · 0 closed",
        "scores 60–80:  4 entered, 3 still open (median age 12.0 days) · 1 closed · "
        "1 won (100%) · the plan promised 33%   (a band needs 20 to count)",
    ]


def test_a_band_with_nothing_closed_yet_is_still_shown(grade):
    """The most censored a band can be is the one the grade never mentions."""
    rows, _ = grade([], [_open(70, 19.9)])
    assert rows == ["scores 60–80:  1 entered, 1 still open "
                    "(median age 19.9 days) · 0 closed"]


def test_no_entries_at_all_keeps_the_empty_state(grade):
    rows, nxt = grade([], [])
    assert rows == ["no closed positions yet — nothing to grade"]
    assert "provisional" not in nxt


def test_a_closed_count_is_the_whole_book_not_the_latest_forty(grade):
    """`positions["closed"]` holds the latest forty rows; the report grades all."""
    rows, _ = grade([_closed(10) for _ in range(60)], [_open(10, 4)])
    assert rows[0].startswith("scores 0–20:  61 entered, 1 still open "
                              "(median age 4.0 days) · 60 closed · ")


def test_open_positions_are_banded_as_the_report_bands_the_closed_ones(grade):
    """lo <= score < hi on both sides, so a score of exactly 20 is in 20–40
    whether it has closed or not, and the top band prints as 80–100."""
    rows, _ = grade([_closed(20), _closed(100)],
                    [_open(19.99, 2), _open(20, 2), _open(100, 2)])
    assert [r.split(" · ")[0] for r in rows] == [
        "scores 0–20:  1 entered, 1 still open (median age 2.0 days)",
        "scores 20–40:  2 entered, 1 still open (median age 2.0 days)",
        "scores 80–100:  2 entered, 1 still open (median age 2.0 days)",
    ]


@pytest.mark.parametrize("seconds, said", [
    (0, "under an hour"), (3599, "under an hour"),
    (3600, "1 hour"), (7200, "2 hours"), (86399, "24 hours"),
    (86400, "1 day"), (1.5 * 86400, "1.5 days"), (4.94 * 86400, "4.9 days"),
])
def test_an_age_is_said_in_the_unit_it_is_read_in(seconds, said):
    from ui.app import _open_span
    assert _open_span(seconds) == said


def test_a_position_closed_by_hand_is_in_neither_count_and_the_panel_says_so(grade):
    """The report grades barriers only, so a by-hand close is outside the
    band counts; the line that reports it says it is."""
    rows, _ = grade([_closed(10), _closed(10, "MANUAL")], [_open(10, 3)])
    assert rows[0].startswith("scores 0–20:  2 entered, 1 still open "
                              "(median age 3.0 days) · 1 closed · 1 won (100%)")
    assert rows[-1] == ("1 closed by hand — not graded, and not in the counts above: "
                        "the odds are about reaching the target or the stop")


def test_an_open_row_without_an_age_is_aged_from_when_it_opened(grade):
    rows, _ = grade([], [{"confidence": 10, "opened_at": time.time() - 2 * 86400}])
    assert "median age 2.0 days" in rows[0]


@pytest.mark.parametrize("entered, still_open, flagged", [
    (5, 1, False),      # 20%
    (10, 3, False),     # 30%
    (5, 2, True),       # 40%, exactly: "at least"
    (10, 4, True),
    (5, 3, True),
])
def test_the_caveat_starts_at_forty_percent_of_a_bands_entries_open(
        grade, entered, still_open, flagged):
    closed = [_closed(10) for _ in range(entered - still_open)]
    _, nxt = grade(closed, [_open(10, 3) for _ in range(still_open)])
    assert ("provisional" in nxt) is flagged


def test_the_caveat_names_the_mostly_open_bands_and_only_those(grade):
    closed = [_closed(10)] * 6 + [_closed(50)] * 2 + [_closed(70)]
    opened = [_open(10, 3)] + [_open(50, 3)] * 3 + [_open(70, 3)]     # 14% · 60% · 50%
    _, nxt = grade(closed, opened)
    assert nxt.startswith(
        "any verdict is provisional: slow positions are missing from the grade — "
        "40% or more of the positions entered at scores 40–60 and 60–80 are "
        "still open · ")
    assert "0–20" not in nxt


def test_the_caveat_calls_it_the_verdict_once_there_is_one(grade):
    closed = [_closed(10, "TARGET" if i % 2 else "STOP") for i in range(20)]
    _, nxt = grade(closed, [_open(10, 6) for _ in range(20)])           # 50% open
    assert nxt.startswith("the verdict is provisional: slow positions are "
                          "missing from the grade — ")


def test_the_caveat_goes_when_the_open_ones_close(grade):
    _, before = grade([_closed(10), _closed(10)], [_open(10, 5) for _ in range(3)])
    assert "provisional" in before
    _, after = grade([_closed(10) for _ in range(5)], [])               # all five closed
    assert "provisional" not in after


def test_the_censoring_readout_never_reads_as_a_forecast(window, grade):
    closed = [_closed(10) for _ in range(20)] + [_closed(70)]
    grade(closed, [_open(10, 9), _open(40, 2), _open(70, 30)])
    text = " ".join(lb.text().lower() for lb in
                    (window.grade_verdict, window.grade_rows, window.grade_next))
    assert "provisional" in text and "still open" in text   # the state under test
    for forecast in FORECAST_WORDS:
        assert forecast not in text, f"{forecast!r} in the grade panel"


def test_the_band_lines_wrap_so_they_cannot_set_a_floor_under_the_window(window):
    assert window.grade_rows.wordWrap()


def test_the_first_screen_counts_every_open_position(window):
    """Through `refresh`, not `_refresh_grade`: the call site has to hand the
    book's open rows over."""
    window.refresh()
    opened = window.live.positions["open"]
    assert opened, "the fixture book has no open position to count"
    shown = sum(int(n) for n in re.findall(r"(\d+) still open", window.grade_rows.text()))
    assert shown == len(opened)


def test_my_trades_table_shows_the_open_share_too(window):
    window.live.positions["open"].append(_open(10, 3))
    try:
        window._refresh_book()
        text = window.cal_table.text()
        assert "still open" in text and "median age 3.0 days" in text
        assert "provisional" in text
        assert window.cal_table.wordWrap()
        for forecast in FORECAST_WORDS:
            assert forecast not in text.lower()
    finally:
        window.live.positions["open"].pop()
        window._refresh_book()
