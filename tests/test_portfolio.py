"""Tests for the paper book.

Bookkeeping bugs here are the quiet kind: a short that credits cash twice, or a
stop that fills on the wrong side, produces a portfolio that looks profitable
for reasons that have nothing to do with the model. Since the whole point of
this book is to *judge* the model, its arithmetic has to be beyond doubt.
"""

import pytest

from sonar.portfolio import Portfolio

ASSET = {"symbol": "TEST", "name": "Test Co", "price": 100.0,
         "volatility": 0.02, "confidence": 70.0, "cls": "Equity"}


def book(tmp_path, **kw):
    return Portfolio(tmp_path / "portfolio.json", **kw)


def test_long_then_target_makes_money(tmp_path):
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "LONG", 4, "week")
    assert pos is not None and pos.direction == "LONG"
    assert pos.stop < pos.entry < pos.target
    closed = p.mark({"TEST": pos.target})
    assert len(closed) == 1 and closed[0].outcome == "TARGET"
    assert closed[0].pnl > 0
    assert p.stats()["n_open"] == 0


def test_long_then_stop_loses_the_risk_budget(tmp_path):
    """A stopped-out long must lose almost exactly the cash it put at risk."""
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "LONG", 4, "week", risk_fraction=0.01)
    closed = p.mark({"TEST": pos.stop})[0]
    assert closed.outcome == "STOP"
    assert closed.pnl == pytest.approx(-pos.cash_at_risk, rel=1e-6)
    assert closed.pnl == pytest.approx(-100.0, rel=1e-6)   # 1% of 10k


def test_short_profits_when_price_falls(tmp_path):
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "SHORT", 4, "week")
    assert pos.target < pos.entry < pos.stop
    closed = p.mark({"TEST": pos.target})[0]
    assert closed.outcome == "TARGET" and closed.pnl > 0


def test_short_loses_when_price_rises(tmp_path):
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "SHORT", 4, "week")
    closed = p.mark({"TEST": pos.stop})[0]
    assert closed.outcome == "STOP" and closed.pnl < 0


def test_reward_is_rr_times_the_risk(tmp_path):
    """Winning must pay the advertised multiple of what losing costs."""
    win = book(tmp_path / "a")
    wpos, _ = win.enter(ASSET, "LONG", 4, "week")
    wclosed = win.mark({"TEST": wpos.target})[0]
    lose = book(tmp_path / "b")
    lpos, _ = lose.enter(ASSET, "LONG", 4, "week")
    lclosed = lose.mark({"TEST": lpos.stop})[0]
    assert wclosed.pnl / abs(lclosed.pnl) == pytest.approx(wpos.rr, rel=1e-6)


def test_one_position_per_symbol(tmp_path):
    p = book(tmp_path)
    first, _ = p.enter(ASSET, "LONG", 4, "week")
    second, msg = p.enter(ASSET, "LONG", 4, "week")
    assert first is not None
    assert second is None and "already holding" in msg


def test_round_trip_returns_cash_to_the_book(tmp_path):
    """Open and close at the same price: cash must come back where it started."""
    p = book(tmp_path)
    start = p.cash
    pos, _ = p.enter(ASSET, "LONG", 4, "week")
    assert p.cash < start                     # a long spends cash
    p.close(pos.id, pos.entry, "MANUAL")
    assert p.cash == pytest.approx(start)
    assert p.stats()["total_pnl"] == pytest.approx(0.0)


def test_equity_tracks_an_open_position(tmp_path):
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "LONG", 4, "week")
    flat = p.equity({"TEST": pos.entry})
    up = p.equity({"TEST": pos.entry * 1.01})
    assert flat == pytest.approx(p.starting_cash)
    assert up > flat


def test_entry_records_the_belief_for_calibration(tmp_path):
    """Without the score at entry there is nothing to calibrate against."""
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "LONG", 4, "week")
    assert pos.confidence == 70.0
    assert 0.0 < pos.p_profit < 1.0
    assert pos.rr > 0 and pos.horizon == "week"


def test_state_survives_a_restart(tmp_path):
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "LONG", 4, "week")
    p.mark({"TEST": pos.target})
    again = book(tmp_path)
    assert again.stats()["n_closed"] == 1
    assert again.cash == pytest.approx(p.cash)


def test_refuses_an_instrument_with_no_volatility(tmp_path):
    """No volatility means no honest stop, so there is no position to take."""
    p = book(tmp_path)
    pos, msg = p.enter({**ASSET, "volatility": 0.0}, "LONG", 4, "week")
    assert pos is None and "volatility" in msg


def test_untouched_barriers_leave_the_position_open(tmp_path):
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "LONG", 4, "week")
    assert p.mark({"TEST": pos.entry}) == []
    assert p.stats()["n_open"] == 1


def test_the_broker_is_paper(tmp_path):
    p = book(tmp_path)
    assert p.stats()["live"] is False
    assert p.stats()["broker"] == "paper"
