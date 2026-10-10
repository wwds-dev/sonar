"""A position whose instrument the risk filter hides is still priced.

The filter is a visibility rule for the board. It used to reach the book: a
held DOGE that fell 30%, closed after switching to Conservative (which hides
DOGE), closed at its entry price for a P&L of zero; its barriers stopped being
watched and its equity was marked flat.
"""

from __future__ import annotations

import pytest

from sonar import assets, horizon, risk
from sonar.core import Live
from sonar.portfolio import Portfolio

DOGE = {"symbol": "DOGE-USD", "name": "Dogecoin", "price": 1.0, "volatility": 0.05,
        "confidence": 50.0, "cls": "crypto"}
CALM = {"symbol": "AAA", "name": "Aaa", "price": 100.0, "volatility": 0.01,
        "confidence": 50.0, "cls": "equity"}


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    lv = Live()
    lv.book = Portfolio(tmp_path / "portfolio.json")
    pos, msg = lv.book.enter(DOGE, "LONG", 5, "week")
    assert pos is not None, msg
    lv.assets = {"assets": [dict(CALM)]}          # DOGE hidden from the board
    return lv, pos


def test_closing_a_hidden_position_uses_its_last_price(live):
    lv, pos = live
    lv.asset_scanner.last_prices["DOGE-USD"] = 0.70
    result = lv.close_position(pos.id)
    assert result["ok"]
    closed = lv.book.closed[-1]
    assert closed.exit == 0.70
    assert closed.pnl == pytest.approx(pos.units * (0.70 - 1.0), abs=0.01)
    assert closed.pnl < 0, "a 30% loss was booked as zero"


def test_with_no_price_at_all_the_close_is_refused_not_booked_at_entry(live):
    lv, pos = live
    result = lv.close_position(pos.id)
    assert result["ok"] is False and "no price for DOGE-USD" in result["message"]
    assert lv.book.open and not lv.book.closed


def test_a_hidden_positions_stop_is_still_watched(live):
    lv, pos = live
    lv.asset_scanner.last_prices["DOGE-USD"] = pos.stop * 0.9
    lv._mark_book({"assets": [dict(CALM)]})
    assert not lv.book.open
    assert lv.book.closed[-1].outcome == "STOP"


def test_the_scanner_remembers_prices_of_the_rows_it_hides(monkeypatch):
    def fetch(symbol, rng):
        if symbol == "DOGE-USD":                     # 10% swings: hidden by Conservative
            closes = [1.0 if i % 2 else 1.1 for i in range(300)]
        else:
            closes = [100.0 + i * 0.01 for i in range(300)]
        return (closes[-1], "USD", closes)

    monkeypatch.setattr(assets, "_fetch", fetch)
    sc = assets.AssetScanner()
    board = sc.payload([], horizon.HORIZONS["week"], risk.get("conservative"))
    shown = {a["symbol"] for a in board["assets"]}
    assert "DOGE-USD" not in shown
    assert sc.last_prices["DOGE-USD"] == 1.0


def test_stops_are_watched_even_when_the_filter_empties_the_board(live):
    """A crash where every instrument is too volatile for the profile: the
    board is empty, and the mark pass used to return before looking."""
    lv, pos = live
    lv.asset_scanner.last_prices["DOGE-USD"] = pos.stop * 0.9
    lv._mark_book({"assets": []})
    assert not lv.book.open and lv.book.closed[-1].outcome == "STOP"


def test_a_hidden_positions_card_keeps_its_price_history(live):
    lv, pos = live
    lv.asset_scanner.last_prices["DOGE-USD"] = 0.95
    lv.asset_scanner.last_sparks["DOGE-USD"] = [1.0, 0.98, 0.95]
    lv._mark_book({"assets": [dict(CALM)]})
    row = next(r for r in lv.positions["open"] if r["symbol"] == "DOGE-USD")
    assert row["price"] == 0.95 and row["spark"] == [1.0, 0.98, 0.95]


def test_taking_the_book_over_prices_hidden_positions_too(live, tmp_path):
    lv, pos = live
    lv.asset_scanner.last_prices["DOGE-USD"] = 0.70
    lv._take_the_book()                          # re-reads portfolio.json from disk
    row = next(r for r in lv.positions["open"] if r["symbol"] == "DOGE-USD")
    assert row["price"] == 0.70, "shown at its entry price after a takeover"
