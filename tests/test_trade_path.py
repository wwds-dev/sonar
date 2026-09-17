"""From a click on the Assets board to a row in the Book.

`Live.trade` and `Live.close_position` are the layer between a user action and
the paper book, and `sonar/core.py` was 34% with neither of them touched. The
book underneath has its own suite; what is untested is the orchestration —
finding the row, passing the direction through, and re-marking afterwards so
the Book tab shows the position that was just opened rather than the state
before it.

`Live` is real here. Nothing reaches the network: the poll loop is never
started, and every price is one this test put there.
"""

import pytest

from sonar.core import Live


def row(symbol="BTC-USD", price=100.0, vol=0.03, name=None, conf=70.0, cls="Crypto"):
    return {"symbol": symbol, "price": price, "volatility": vol,
            "name": name or symbol, "confidence": conf, "cls": cls}


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    engine = Live()
    engine.assets = {"assets": [row(), row("ETH-USD", price=50.0)]}
    return engine


# --------------------------------------------------------------------------- #
# Opening
# --------------------------------------------------------------------------- #
def test_a_long_opens_a_position(live):
    result = live.trade("BTC-USD", "LONG")
    assert result["ok"] is True
    assert result["position"]["symbol"] == "BTC-USD"
    assert result["position"]["direction"] == "LONG"


def test_a_short_opens_the_other_way(live):
    assert live.trade("BTC-USD", "SHORT")["position"]["direction"] == "SHORT"


def test_a_stop_and_target_are_set_at_entry(live):
    """A position with no barriers never resolves, so nothing about it is ever
    falsifiable — which is the whole point of the book."""
    pos = live.trade("BTC-USD", "LONG")["position"]
    assert pos["stop"] < pos["entry"] < pos["target"]


def test_a_short_has_its_barriers_the_other_way_round(live):
    pos = live.trade("BTC-USD", "SHORT")["position"]
    assert pos["target"] < pos["entry"] < pos["stop"]


def test_an_unknown_symbol_is_refused_by_name(live):
    result = live.trade("NOPE", "LONG")
    assert result["ok"] is False
    assert "NOPE" in result["message"]
    assert result["position"] is None


def test_a_symbol_with_no_price_cannot_be_traded(live):
    """A dead feed sends a zero, and a position entered at zero is nonsense
    that would sit in the book forever."""
    live.assets = {"assets": [row("DEAD", price=0.0)]}
    assert live.trade("DEAD", "LONG")["ok"] is False


def test_a_symbol_with_no_volatility_cannot_be_traded(live):
    """No volatility means no stop distance, and a stop is not optional."""
    live.assets = {"assets": [row("FLAT", vol=0.0)]}
    result = live.trade("FLAT", "LONG")
    assert result["ok"] is False
    assert "stop" in result["message"]


def test_the_same_symbol_cannot_be_held_twice(live):
    """Doubling up turns a fixed risk budget into an unbounded one."""
    assert live.trade("BTC-USD", "LONG")["ok"] is True
    second = live.trade("BTC-USD", "LONG")
    assert second["ok"] is False
    assert "already holding" in second["message"]


def test_two_different_symbols_can_both_be_held(live):
    assert live.trade("BTC-USD", "LONG")["ok"] is True
    assert live.trade("ETH-USD", "SHORT")["ok"] is True
    assert len(live.book.open) == 2


# --------------------------------------------------------------------------- #
# The Book tab reads `positions`, so opening has to refresh it
# --------------------------------------------------------------------------- #
def test_a_new_position_is_visible_to_the_book_tab_immediately(live):
    """Without the re-mark, a user clicks buy and the Book stays empty until
    the next 90-second tick — indistinguishable from the button not working."""
    live.trade("BTC-USD", "LONG")
    symbols = [p["symbol"] for p in live.positions["open"]]
    assert symbols == ["BTC-USD"]


def test_the_book_carries_stats_after_a_trade(live):
    live.trade("BTC-USD", "LONG")
    assert live.positions["stats"]["n_open"] == 1


# --------------------------------------------------------------------------- #
# Closing
# --------------------------------------------------------------------------- #
def test_closing_moves_a_position_from_open_to_closed(live):
    pos_id = live.trade("BTC-USD", "LONG")["position"]["id"]
    result = live.close_position(pos_id)
    assert result["ok"] is True
    assert live.book.open == []
    assert len(live.book.closed) == 1


def test_closing_is_marked_as_a_manual_exit(live):
    """So the calibration table can tell a hand-closed position from one that
    actually hit a barrier — only the second kind is evidence."""
    pos_id = live.trade("BTC-USD", "LONG")["position"]["id"]
    live.close_position(pos_id)
    assert live.book.closed[0].outcome == "MANUAL"


def test_closing_uses_the_current_price_not_the_entry(live):
    pos_id = live.trade("BTC-USD", "LONG")["position"]["id"]
    live.assets = {"assets": [row(price=120.0), row("ETH-USD", price=50.0)]}
    closed = live.close_position(pos_id)["position"]
    assert closed["exit"] == pytest.approx(120.0)
    assert closed["pnl"] > 0


def test_closing_an_unknown_position_is_refused(live):
    result = live.close_position("not-a-real-id")
    assert result["ok"] is False
    assert "no such open position" in result["message"]


def test_a_position_cannot_be_closed_twice(live):
    pos_id = live.trade("BTC-USD", "LONG")["position"]["id"]
    live.close_position(pos_id)
    assert live.close_position(pos_id)["ok"] is False
    assert len(live.book.closed) == 1, "double close would double-count the P&L"


def test_the_book_tab_sees_the_close_immediately(live):
    pos_id = live.trade("BTC-USD", "LONG")["position"]["id"]
    live.close_position(pos_id)
    assert live.positions["open"] == []
    assert len(live.positions["closed"]) == 1


# --------------------------------------------------------------------------- #
# Marking
# --------------------------------------------------------------------------- #
def test_an_empty_scan_does_not_touch_the_book_at_all(live):
    """The guard is about not doing the work, not about protecting the board.

    Checked, because the first version of this test claimed the guard stopped
    an empty scan wiping the positions — it does not. `open_rows({})` and
    `stats({})` fall back to entry prices and return exactly what they returned
    before, so removing the guard changes nothing visible. What it does stop is
    re-marking, re-settling and re-running calibration against no prices every
    time a scan comes back empty, so that is what this asserts.
    """
    live.trade("BTC-USD", "LONG")
    touched = []
    live.book.poll_fills = lambda: touched.append("poll")
    live.book.mark = lambda prices: touched.append("mark")

    live._mark_book({"assets": []})
    assert touched == [], "an empty scan should be a no-op"

    live._mark_book({"assets": [row(price=101.0)]})
    assert touched == ["poll", "mark"], "a real scan should mark the book"


def test_hitting_the_target_closes_the_position_by_itself(live):
    """The loop that makes the screener falsifiable: positions resolve on their
    own, and calibration then measures whether high scores actually won."""
    pos = live.trade("BTC-USD", "LONG")["position"]
    live._mark_book({"assets": [row(price=pos["target"] * 1.01)]})
    assert live.book.open == []
    assert live.book.closed[0].outcome == "TARGET"


def test_hitting_the_stop_closes_it_too(live):
    pos = live.trade("BTC-USD", "LONG")["position"]
    live._mark_book({"assets": [row(price=pos["stop"] * 0.99)]})
    assert live.book.closed[0].outcome == "STOP"


def test_an_unproven_book_claims_no_edge(live):
    """`P(profit)` stays on its driftless baseline until calibration has enough
    closed positions to say otherwise. One trade is not enough."""
    pos = live.trade("BTC-USD", "LONG")["position"]
    live._mark_book({"assets": [row(price=pos["target"] * 1.01)]})
    assert live.calibration["calibrated"] is False
    assert live.asset_scanner.edge_sigma == 0.0


def test_marking_republishes_the_calibration_report(live):
    live.trade("BTC-USD", "LONG")
    live._mark_book({"assets": [row(price=101.0)]})
    assert "calibrated" in live.calibration


@pytest.mark.parametrize("call", [
    lambda live: live.trade("NOPE", "LONG"),
    lambda live: live.trade("BTC-USD", "LONG"),
    lambda live: live.close_position("not-a-real-id"),
])
def test_every_reply_has_the_same_shape(live, call):
    """A caller reading result["position"] should not have to know which
    failure it hit. The unknown-symbol path used to omit the key entirely."""
    result = call(live)
    assert set(result) == {"ok", "message", "position"}
    assert isinstance(result["ok"], bool)
    assert isinstance(result["message"], str)
