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


# --------------------------------------------------------------------------- #
# The landing page's figures and the account-value log
# --------------------------------------------------------------------------- #
def test_stats_split_invested_into_cash_spent_and_stock_borrowed(tmp_path):
    """A long spends cash; a short borrows. Summed blindly on a $10k book the
    two come to $40k+, which is why the landing page says which is which."""
    p = book(tmp_path)
    lp, _ = p.enter(ASSET, "LONG", 4, "week")
    sp, _ = p.enter({**ASSET, "symbol": "OTHER"}, "SHORT", 4, "week")
    st = p.stats({"TEST": 100.0, "OTHER": 100.0})
    assert st["long_cash"] == pytest.approx(lp.units * lp.entry, rel=1e-6)
    assert st["short_notional"] == pytest.approx(sp.units * sp.entry, rel=1e-6)
    assert (st["n_long"], st["n_short"]) == (1, 1)
    assert st["at_risk"] == pytest.approx(lp.cash_at_risk + sp.cash_at_risk, rel=1e-6)
    assert st["realised"] == 0.0


def test_realised_is_the_sum_of_what_closed(tmp_path):
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "LONG", 4, "week")
    closed = p.mark({"TEST": pos.target})[0]
    st = p.stats()
    assert st["realised"] == pytest.approx(closed.pnl, abs=0.01)
    assert st["at_risk"] == 0.0 and st["n_long"] == 0


def test_open_rows_carry_the_stake_and_the_move_since_entry(tmp_path):
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "SHORT", 4, "week")
    row = p.open_rows({"TEST": 95.0})[0]
    assert row["stake"] == pytest.approx(pos.units * 100.0, rel=1e-6)
    assert row["pct"] == pytest.approx(5.0)          # a short gains as price falls
    assert row["age_s"] >= 0


def test_the_account_value_is_logged_hourly_not_every_scan(tmp_path):
    p = book(tmp_path)
    p.enter(ASSET, "LONG", 4, "week")
    assert p.log_equity({"TEST": 100.0}, now=1_000_000.0)
    assert not p.log_equity({"TEST": 101.0}, now=1_000_000.0 + 600)
    assert p.log_equity({"TEST": 101.0}, now=1_000_000.0 + 3600)
    assert [q["t"] for q in p.equity_log] == [1_000_000, 1_003_600]


def test_an_entry_or_an_exit_forces_a_point(tmp_path):
    p = book(tmp_path)
    p.enter(ASSET, "LONG", 4, "week")
    p.log_equity({"TEST": 100.0}, now=1_000_000.0)
    assert p.log_equity({"TEST": 100.0}, now=1_000_000.0 + 5, force=True)
    assert len(p.equity_log) == 2


def test_no_point_is_written_while_a_held_position_has_no_price(tmp_path):
    """Marking the missing one at entry would draw a dip or a jump that never
    happened; refusing is the honest shape of the curve."""
    p = book(tmp_path)
    p.enter(ASSET, "LONG", 4, "week")
    assert not p.log_equity({}, now=1_000_000.0)
    assert p.equity_log == []


def test_the_log_survives_a_restart(tmp_path):
    p = book(tmp_path)
    p.enter(ASSET, "LONG", 4, "week")
    p.log_equity({"TEST": 100.0}, now=1_000_000.0)
    again = book(tmp_path)
    assert again.equity_log == [{"t": 1_000_000, "v": pytest.approx(10_000.0, abs=0.01)}]


def _local_day(year: int, month: int, day: int, hour: int = 0) -> float:
    from datetime import datetime
    return datetime(year, month, day, hour).timestamp()


def test_the_seed_rebuilds_one_point_per_day_from_the_books_own_records(tmp_path):
    """Ten units at 100, bought in the morning of day 0, sold at 115 on day 2.
    Closes 100 / 110 / 120: the account is worth 10,000, 10,100 and — once
    the sale has gone through — 10,150 at the end of those three days."""
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "LONG", 4, "week")
    pos.units, pos.entry = 10.0, 100.0
    p.cash = 10_000.0 - 1_000.0
    pos.opened_at = _local_day(2026, 9, 1, 10)
    p.close(pos.id, 115.0, "MANUAL")
    p.closed[-1].closed_at = _local_day(2026, 9, 3, 12)
    bars = {"TEST": [(_local_day(2026, 9, 1, 9), 100.0),
                     (_local_day(2026, 9, 2, 9), 110.0),
                     (_local_day(2026, 9, 3, 9), 120.0)]}
    n = p.seed_equity_log(bars, now=_local_day(2026, 9, 4, 12))
    assert n == 3
    assert [q["v"] for q in p.equity_log] == [10_000.0, 10_100.0, 10_150.0]
    assert [q["t"] for q in p.equity_log] == [
        _local_day(2026, 9, 2) - 1, _local_day(2026, 9, 3) - 1, _local_day(2026, 9, 4) - 1]
    assert book(tmp_path).equity_log == p.equity_log      # saved


def test_the_seed_values_a_short_by_its_profit_not_its_notional(tmp_path):
    """A short borrows, so cash never moved: the account is the cash plus the
    short's running profit, not the cash plus a holding."""
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "SHORT", 4, "week")
    pos.units, pos.entry = 10.0, 100.0
    pos.opened_at = _local_day(2026, 9, 1, 10)
    bars = {"TEST": [(_local_day(2026, 9, 1, 9), 100.0),
                     (_local_day(2026, 9, 2, 9), 90.0)]}
    p.seed_equity_log(bars, now=_local_day(2026, 9, 3, 12))
    assert [q["v"] for q in p.equity_log] == [10_000.0, 10_100.0]


def test_the_seed_refuses_to_overwrite_a_log_or_invent_one(tmp_path):
    p = book(tmp_path)
    assert not p.history_wanted()
    assert p.seed_equity_log({"TEST": [(1, 1.0)]}) == 0          # never traded
    pos, _ = p.enter(ASSET, "LONG", 4, "week")
    assert p.history_wanted()
    assert p.seed_equity_log({}) == 0                             # no bars
    p.log_equity({"TEST": 100.0}, now=pos.opened_at + 1)
    assert not p.history_wanted()                                 # logged from day one
    assert p.seed_equity_log({"TEST": [(1, 1.0)]}) == 0
    assert len(p.equity_log) == 1


def test_the_seed_fills_in_before_a_live_point_and_never_over_it(tmp_path):
    """The engine logs its first live point the moment every position has a
    price — which is before the seed gets its turn. The seed prepends the
    days before that point and leaves the measured one alone."""
    p = book(tmp_path)
    pos, _ = p.enter(ASSET, "LONG", 4, "week")
    pos.units, pos.entry = 10.0, 100.0
    p.cash = 9_000.0
    pos.opened_at = _local_day(2026, 9, 1, 10)
    live_at = _local_day(2026, 9, 3, 11)
    p.log_equity({"TEST": 125.0}, now=live_at)             # 9,000 + 1,250
    assert p.history_wanted()
    bars = {"TEST": [(_local_day(2026, 9, 1, 9), 100.0),
                     (_local_day(2026, 9, 2, 9), 110.0),
                     (_local_day(2026, 9, 3, 9), 120.0)]}
    assert p.seed_equity_log(bars, now=_local_day(2026, 9, 3, 12)) == 2
    assert [(q["t"], q["v"]) for q in p.equity_log] == [
        (_local_day(2026, 9, 2) - 1, 10_000.0), (_local_day(2026, 9, 3) - 1, 10_100.0),
        (int(live_at), 10_250.0)]
    assert not p.history_wanted()
    assert p.seed_equity_log(bars) == 0                      # idempotent
