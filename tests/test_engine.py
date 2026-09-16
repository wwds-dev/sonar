"""The paper-trading engine: what goes in the book, and what the curve says.

`sonar/engine.py` was 38% covered with no test touching `tick`, `_maybe_enter`,
`finalize`, `stats`, `save` or `_load`. Those decide when a position is opened,
what it settles at, and every number the Book tab reports — so a bug here does
not crash, it quietly writes a wrong equity curve and keeps going.

Everything below drives the real `Engine` against a real state file in
`tmp_path`. Nothing is mocked except the clock, because `_tau` reads it.
"""

import json
import time
from dataclasses import dataclass

import pytest

from sonar import engine as eng
from sonar import risk as risk_mod

HOUR = 3_600_000          # candle open_time is in milliseconds


@dataclass
class Candle:
    open_time: int
    open: float
    price: float


@dataclass
class Market:
    title: str = "Bitcoin Up or Down"
    implied_up: float = 0.50
    end_time: int = 0
    best_ask: float | None = None
    best_bid: float | None = None


@pytest.fixture
def clock(monkeypatch):
    """A stopped clock, so `_tau` is something a test can choose."""
    now = [1_700_000_000.0]
    monkeypatch.setattr(eng.time, "time", lambda: now[0])
    return now


@pytest.fixture
def engine(tmp_path, clock):
    return eng.Engine(tmp_path / "state.json", starting_bankroll=10_000.0)


def market_at(clock, tau: float, **kw) -> Market:
    """A market with `tau` of the hour left, per `Engine._tau`."""
    return Market(end_time=clock[0] + tau * 3600.0, **kw)


def eager() -> risk_mod.RiskProfile:
    """A profile that will take almost any bet, so entry tests are about the
    thing under test rather than about the threshold."""
    return risk_mod.RiskProfile(
        name="test", edge_threshold=0.01, kelly_fraction=0.25,
        max_stake_fraction=0.05, enter_tau_min=0.05, enter_tau_max=0.95)


# --------------------------------------------------------------------------- #
# A fresh engine
# --------------------------------------------------------------------------- #
def test_a_new_engine_starts_flat(engine):
    assert engine.bankroll == 10_000.0
    assert engine.open_position is None
    assert engine.trades == []


def test_stats_on_an_empty_book_do_not_divide_by_zero(engine):
    s = engine.stats()
    assert s["n_trades"] == 0
    assert s["win_rate"] == 0.0
    assert s["avg_pnl"] == 0.0
    assert s["profit_factor"] is None
    assert s["total_pnl"] == 0.0


def test_llm_calibration_on_an_empty_book_is_not_an_error(engine):
    rows = engine.llm_calibration()["buckets"]
    assert all(r["n"] == 0 and r["hit_rate"] is None for r in rows)


# --------------------------------------------------------------------------- #
# tick
# --------------------------------------------------------------------------- #
def test_a_tick_with_no_candle_changes_nothing(engine):
    assert engine.tick(None, Market(), 0.0045) is None
    assert engine.current_hour is None


def test_the_first_candle_sets_the_hour(engine, clock):
    engine.tick(Candle(HOUR, 100.0, 100.0), market_at(clock, 0.5), 0.0045)
    assert engine.current_hour == HOUR


def test_a_tick_with_no_market_still_tracks_the_hour(engine):
    """No market to price against is not a reason to lose the rollover."""
    engine.tick(Candle(HOUR, 100.0, 100.0), None, 0.0045)
    assert engine.current_hour == HOUR


def test_ticking_twice_in_the_same_hour_does_not_settle_anything(engine, clock):
    candle = Candle(HOUR, 100.0, 100.5)
    engine.risk = eager()
    engine.tick(candle, market_at(clock, 0.5, implied_up=0.30), 0.0045)
    assert engine.open_position is not None
    engine.tick(candle, market_at(clock, 0.4, implied_up=0.30), 0.0045)
    assert engine.trades == [], "the hour has not rolled over yet"


def test_a_new_hour_settles_the_one_before_it(engine, clock):
    engine.risk = eager()
    engine.tick(Candle(HOUR, 100.0, 100.5),
                market_at(clock, 0.5, implied_up=0.30), 0.0045)
    assert engine.open_position is not None

    # Next hour opens at 101 — above the old open, so UP won.
    engine.tick(Candle(HOUR * 2, 101.0, 101.0),
                market_at(clock, 0.9, implied_up=0.50), 0.0045)
    assert engine.open_position is None
    assert len(engine.trades) == 1
    assert engine.trades[0].result == "UP"
    assert engine.trades[0].won is True


# --------------------------------------------------------------------------- #
# Entry
# --------------------------------------------------------------------------- #
def test_only_one_position_per_hour(engine, clock):
    engine.risk = eager()
    candle = Candle(HOUR, 100.0, 100.5)
    engine.tick(candle, market_at(clock, 0.5, implied_up=0.30), 0.0045)
    first = engine.open_position
    engine.tick(candle, market_at(clock, 0.4, implied_up=0.10), 0.0045)
    assert engine.open_position is first


def test_no_entry_without_enough_edge(engine, clock):
    """The market agreeing with the model is the common case and not a bet."""
    engine.risk = eager()
    engine.tick(Candle(HOUR, 100.0, 100.0),
                market_at(clock, 0.5, implied_up=0.50), 0.0045)
    assert engine.open_position is None


def test_no_entry_outside_the_risk_profile_s_time_window(engine, clock):
    engine.risk = risk_mod.RiskProfile(
        name="narrow", edge_threshold=0.01, kelly_fraction=0.25,
        max_stake_fraction=0.05, enter_tau_min=0.40, enter_tau_max=0.60)
    candle = Candle(HOUR, 100.0, 100.5)
    engine.tick(candle, market_at(clock, 0.95, implied_up=0.30), 0.0045)
    assert engine.open_position is None, "too early in the hour"
    engine.tick(candle, market_at(clock, 0.02, implied_up=0.30), 0.0045)
    assert engine.open_position is None, "too late in the hour"
    engine.tick(candle, market_at(clock, 0.50, implied_up=0.30), 0.0045)
    assert engine.open_position is not None, "inside the window"


def test_the_stake_is_capped_by_the_risk_profile(engine, clock):
    engine.risk = eager()
    engine.tick(Candle(HOUR, 100.0, 101.0),
                market_at(clock, 0.5, implied_up=0.05), 0.0045)
    pos = engine.open_position
    assert pos is not None
    assert pos.stake <= 10_000.0 * engine.risk.max_stake_fraction + 1e-9


def test_entry_crosses_the_spread(engine, clock):
    """We pay the ask plus slippage, not the midpoint. Pricing entries at the
    mid is the classic way a paper book invents an edge it never had."""
    engine.risk = eager()
    engine.tick(Candle(HOUR, 100.0, 100.5),
                market_at(clock, 0.5, implied_up=0.30, best_ask=0.34), 0.0045)
    assert engine.open_position.entry_price == pytest.approx(0.34 + eng.SLIPPAGE)


def test_a_down_bet_is_priced_off_the_up_bid(engine, clock):
    engine.risk = eager()
    engine.tick(Candle(HOUR, 100.0, 99.5),
                market_at(clock, 0.5, implied_up=0.70, best_bid=0.68), 0.0045)
    pos = engine.open_position
    assert pos.side == "DOWN"
    assert pos.entry_price == pytest.approx((1.0 - 0.68) + eng.SLIPPAGE)


def test_an_llm_read_for_this_hour_rides_along(engine, clock):
    engine.risk = eager()
    engine.attach_llm_read(HOUR, {"conviction": 70, "direction": "UP",
                                  "model": "test-model"})
    engine.tick(Candle(HOUR, 100.0, 100.5),
                market_at(clock, 0.5, implied_up=0.30), 0.0045)
    assert engine.open_position.llm_conviction == 70


def test_an_llm_read_for_a_different_hour_is_not_carried_over(engine, clock):
    """Stale conviction stamped on the wrong hour would poison the calibration
    table that exists to grade it."""
    engine.risk = eager()
    engine.attach_llm_read(HOUR * 5, {"conviction": 70, "direction": "UP"})
    engine.tick(Candle(HOUR, 100.0, 100.5),
                market_at(clock, 0.5, implied_up=0.30), 0.0045)
    assert engine.open_position.llm_conviction is None


def test_a_failed_llm_read_is_not_recorded(engine):
    engine.attach_llm_read(HOUR, {"error": "no key"})
    assert engine.pending_llm is None


# --------------------------------------------------------------------------- #
# Settlement
# --------------------------------------------------------------------------- #
def _open_one(engine, clock, price=100.5, implied=0.30):
    engine.risk = eager()
    engine.tick(Candle(HOUR, 100.0, price),
                market_at(clock, 0.5, implied_up=implied), 0.0045)
    return engine.open_position


def test_a_winning_position_pays_out_and_lifts_the_bankroll(engine, clock):
    pos = _open_one(engine, clock)
    before = engine.bankroll
    settled = engine.finalize(HOUR, close_price=101.0)
    assert settled.won is True
    assert settled.pnl == pytest.approx(pos.shares * (1.0 - pos.entry_price), abs=0.01)
    assert engine.bankroll > before


def test_a_losing_position_costs_exactly_the_stake(engine, clock):
    pos = _open_one(engine, clock)
    before = engine.bankroll
    settled = engine.finalize(HOUR, close_price=99.0)
    assert settled.won is False
    assert settled.pnl == pytest.approx(-pos.stake, abs=0.01)
    assert engine.bankroll == pytest.approx(before - pos.stake, abs=0.01)


def test_closing_exactly_at_the_open_counts_as_up(engine, clock):
    """The market's own convention — 'closes at or above its open'."""
    _open_one(engine, clock)
    assert engine.finalize(HOUR, close_price=100.0).result == "UP"


def test_settling_an_hour_we_hold_nothing_for_returns_nothing(engine, clock):
    _open_one(engine, clock)
    assert engine.finalize(HOUR * 99, close_price=101.0) is None
    assert engine.open_position is None, "a mismatched hour clears the position"


def test_a_position_cannot_be_settled_twice(engine, clock):
    _open_one(engine, clock)
    engine.finalize(HOUR, close_price=101.0)
    assert engine.finalize(HOUR, close_price=101.0) is None
    assert len(engine.trades) == 1, "double settlement would double-count the P&L"


def test_settlement_appends_to_the_equity_curve(engine, clock):
    before = len(engine.equity)
    _open_one(engine, clock)
    engine.finalize(HOUR, close_price=101.0)
    assert len(engine.equity) == before + 1
    assert engine.equity[-1]["v"] == engine.bankroll


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def test_stats_count_what_actually_settled(engine, clock):
    _open_one(engine, clock)
    engine.finalize(HOUR, close_price=101.0)
    s = engine.stats()
    assert s["n_trades"] == 1 and s["n_wins"] == 1
    assert s["win_rate"] == 100.0
    assert s["total_pnl"] == pytest.approx(engine.bankroll - 10_000.0, abs=0.01)


def test_profit_factor_needs_a_loss_to_divide_by(engine, clock):
    _open_one(engine, clock)
    engine.finalize(HOUR, close_price=101.0)
    assert engine.stats()["profit_factor"] is None


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def test_a_book_survives_a_restart(engine, tmp_path, clock):
    _open_one(engine, clock)
    engine.finalize(HOUR, close_price=101.0)
    expected = engine.bankroll

    reopened = eng.Engine(tmp_path / "state.json")
    assert reopened.bankroll == expected
    assert len(reopened.trades) == 1
    assert reopened.trades[0].won is True


def test_an_open_position_survives_a_restart(engine, tmp_path, clock):
    pos = _open_one(engine, clock)
    reopened = eng.Engine(tmp_path / "state.json")
    assert reopened.open_position is not None
    assert reopened.open_position.hour_key == pos.hour_key
    assert reopened.open_position.shares == pos.shares


def test_the_risk_profile_survives_a_restart(engine, tmp_path):
    engine.set_risk(risk_mod.get("aggressive"))
    assert eng.Engine(tmp_path / "state.json").risk.name == "aggressive"


def test_a_state_file_written_before_a_field_existed_still_loads(tmp_path):
    """Trades are dataclasses; adding a field must not strand an old book."""
    old = {
        "starting_bankroll": 10_000.0, "bankroll": 10_150.0,
        "current_hour": HOUR, "equity": [],
        "open_position": None,
        "trades": [{"hour_key": HOUR, "title": "t", "side": "UP",
                    "entry_price": 0.4, "shares": 10.0, "stake": 4.0,
                    "model_up": 0.6, "market_up": 0.4, "edge": 0.2,
                    "entered_at": 1.0, "won": True, "pnl": 6.0}],
    }
    (tmp_path / "state.json").write_text(json.dumps(old))
    e = eng.Engine(tmp_path / "state.json")
    assert e.bankroll == 10_150.0
    assert len(e.trades) == 1
    assert e.trades[0].llm_conviction is None, "the new field defaults"


def test_an_unknown_field_in_a_state_file_does_not_crash_the_load(tmp_path):
    """A book written by a *newer* version, opened by an older one."""
    (tmp_path / "state.json").write_text(json.dumps({
        "bankroll": 9_000.0, "trades": [], "equity": [],
        "something_from_the_future": 42}))
    assert eng.Engine(tmp_path / "state.json").bankroll == 9_000.0


def test_a_corrupt_state_file_starts_fresh_rather_than_raising(tmp_path):
    """Losing a book is bad. Refusing to launch is worse."""
    (tmp_path / "state.json").write_text("{not json at all")
    assert eng.Engine(tmp_path / "state.json").bankroll == eng.STARTING_BANKROLL


def test_saving_is_atomic(engine, tmp_path, clock):
    """Written to a temp file and moved, so a crash mid-write cannot leave a
    half-written book behind."""
    _open_one(engine, clock)
    assert (tmp_path / "state.json").exists()
    assert not (tmp_path / "state.tmp").exists()


# --------------------------------------------------------------------------- #
# The historical warm-up
# --------------------------------------------------------------------------- #
def _rows(n: int, up: bool = True) -> list[dict]:
    return [{"open_time": HOUR * i, "open": 100.0,
             "price": 100.5 if up else 99.5, "close": 101.0 if up else 99.0,
             "sigma": 0.0045, "tau": 0.5} for i in range(1, n + 1)]


def test_the_warm_up_fills_the_curve_from_real_hours(engine):
    engine.seed_backtest(_rows(20))
    assert len(engine.trades) == 20
    assert len(engine.equity) == 21
    assert all(e["kind"] == "backtest" for e in engine.equity[1:])


def test_the_warm_up_pays_fair_odds_so_it_cannot_invent_profit(engine):
    """The whole point: it shows variance, not edge. Backing the favoured side
    at the model's own price is expected-value zero by construction, so a run of
    correct calls must not compound into a fortune."""
    engine.seed_backtest(_rows(40))
    won = [t for t in engine.trades if t.won]
    assert len(won) == 40, "the fixture makes every call correct"
    # Every entry was priced at the model's own probability, so the payout on a
    # win is exactly the complement — no counterparty generosity anywhere.
    for t in won:
        assert t.pnl == pytest.approx(t.shares * (1.0 - t.entry_price), abs=0.01)


def test_the_warm_up_runs_only_once(engine):
    engine.seed_backtest(_rows(10))
    after = engine.bankroll
    engine.seed_backtest(_rows(10))
    assert len(engine.trades) == 10
    assert engine.bankroll == after


def test_the_warm_up_refuses_to_touch_a_book_that_has_traded(engine, clock):
    _open_one(engine, clock)
    engine.finalize(HOUR, close_price=101.0)
    engine.seed_backtest(_rows(10))
    assert len(engine.trades) == 1, "real history must not be padded with a backtest"


def test_the_warm_up_settles_against_the_real_candle(engine):
    engine.seed_backtest(_rows(5, up=False))
    assert all(t.result == "DOWN" for t in engine.trades)


def test_warm_up_prices_are_clamped_away_from_certainty(engine):
    """A model reading of 1.0 would mean free shares and infinite size."""
    rows = [{"open_time": HOUR, "open": 100.0, "price": 200.0, "close": 201.0,
             "sigma": 0.0045, "tau": 0.5}]
    engine.seed_backtest(rows)
    assert 0.02 <= engine.trades[0].entry_price <= 0.98


def test_a_stake_too_small_to_matter_is_not_taken(engine, clock):
    """kelly_stake shrinks with the edge; below a pound it is noise, and a
    position that size would still occupy the hour's only slot."""
    engine.risk = risk_mod.RiskProfile(
        name="tiny", edge_threshold=0.0001, kelly_fraction=1e-9,
        max_stake_fraction=0.05, enter_tau_min=0.05, enter_tau_max=0.95)
    engine.tick(Candle(HOUR, 100.0, 100.5),
                market_at(clock, 0.5, implied_up=0.30), 0.0045)
    assert engine.open_position is None
