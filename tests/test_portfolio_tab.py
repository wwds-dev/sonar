"""The landing page is the reader's own money.

Until Oct 2026 the app opened on the hourly bitcoin model — an experiment the
engine runs, not something the reader holds. Now it opens on the paper book:
the figures as a hierarchy, the account's value over time, every position as a
tile and as a card. These tests build the real window over a book with
positions in it, because the page is only as good as the data it reads.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from sonar.core import Live
from sonar.portfolio import Portfolio
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
    monkeypatch.setattr("ui.app.llm.available", lambda: (False, "no key"))
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


def test_the_grade_never_reads_as_a_forecast(window):
    """Measurement, in words that describe the past. The one rule."""
    text = " ".join(lb.text().lower() for lb in
                    (window.grade_verdict, window.grade_rows, window.grade_next))
    for forecast in ("will", "should", "buy", "sell", "expect", "likely",
                     "going to", "bullish", "bearish"):
        assert forecast not in text, f"{forecast!r} in the grade panel"


def test_the_grade_names_protocol_mode_either_way(window):
    on = window.live.protocol_on
    try:
        window.live.protocol_on = True
        window._refresh_grade(window.live.calibration, window.live.positions["closed"])
        assert "protocol mode is on" in window.grade_next.text()
        window.live.protocol_on = False
        window._refresh_grade(window.live.calibration, window.live.positions["closed"])
        assert "protocol mode is off" in window.grade_next.text()
    finally:
        window.live.protocol_on = on
