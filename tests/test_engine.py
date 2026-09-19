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

# Candle open_time is in unix *seconds* (feeds.py converts Binance's
# milliseconds on parse), and since the gap-settlement fix the engine is
# unit-aware: consecutive hours differ by exactly 3600. This used to be an
# opaque key and was 3_600_000, which would now read as a thousand-hour gap.
HOUR = 3_600


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


def test_a_contiguous_rollover_never_consults_the_lookup(engine, clock):
    """The next candle's open *is* the previous close on a contiguous feed —
    settling from it must stay free, or every quiet rollover costs a fetch."""
    engine.risk = eager()
    engine.tick(Candle(HOUR, 100.0, 100.5),
                market_at(clock, 0.5, implied_up=0.30), 0.0045)

    def boom(_hour):
        raise AssertionError("close_lookup consulted on a contiguous feed")

    engine.tick(Candle(HOUR * 2, 101.0, 101.0),
                market_at(clock, 0.9), 0.0045, close_lookup=boom)
    assert engine.trades[0].result == "UP"


def test_a_gap_settles_against_the_hours_own_close(engine, clock):
    """The bug this guards: after a sleep or restart the next live candle's
    open is a price from hours after the position's market resolved. Here BTC
    stands at 105 when the app wakes — but the position's hour actually closed
    at 99, so UP lost. Settling against the wake-up price would book it a win."""
    engine.risk = eager()
    engine.tick(Candle(HOUR, 100.0, 100.5),
                market_at(clock, 0.5, implied_up=0.30), 0.0045)
    assert engine.open_position.side == "UP"

    engine.tick(Candle(HOUR * 4, 105.0, 105.0), market_at(clock, 0.9), 0.0045,
                close_lookup={HOUR: 99.0}.get)
    assert len(engine.trades) == 1
    assert engine.trades[0].close_price == 99.0
    assert engine.trades[0].result == "DOWN"
    assert engine.trades[0].won is False


def test_a_gap_with_no_recoverable_close_voids_rather_than_guesses(engine, clock):
    """No lookup, or a lookup that fails, must not settle against a wrong
    price. Nothing is deducted at entry, so a void leaves the bankroll exactly
    as if the bet had never been taken — a shorter record beats a corrupt one."""
    engine.risk = eager()
    engine.tick(Candle(HOUR, 100.0, 100.5),
                market_at(clock, 0.5, implied_up=0.30), 0.0045)
    before = engine.bankroll

    engine.tick(Candle(HOUR * 4, 105.0, 105.0), market_at(clock, 0.9), 0.0045)
    assert engine.open_position is None
    assert engine.trades == []
    assert engine.bankroll == before


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


def test_the_edge_gate_is_on_the_executable_price_not_the_midpoint(engine, clock):
    """A fat midpoint edge across a fat spread is not an edge. The model reads
    ~0.96 against a 0.90 midpoint — six cents, clearing the moderate profile's
    four — but the ask is 0.94, so a share costs 0.945 with slippage and the
    edge that can actually be bought is ~1.5 cents. The old midpoint gate let
    exactly this entry through, sized small but under-compensated, every time
    the book was wide late in the hour."""
    engine.tick(Candle(HOUR, 100.0, 100.56),
                market_at(clock, 0.5, implied_up=0.90, best_ask=0.94), 0.0045)
    assert engine.open_position is None


def test_an_executable_edge_past_the_threshold_still_enters(engine, clock):
    """The control for the gate above: same model reading, tighter book."""
    engine.tick(Candle(HOUR, 100.0, 100.56),
                market_at(clock, 0.5, implied_up=0.90, best_ask=0.90), 0.0045)
    assert engine.open_position is not None


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


# --------------------------------------------------------------------------- #
# Live stats stay live
# --------------------------------------------------------------------------- #
def test_seeded_warm_up_rows_stay_out_of_the_live_stats(engine):
    """The warm-up seeds the *chart* with real variance; letting its synthetic
    fair-odds rows into the win rate meant a fresh install opened claiming a
    record built from trades nobody took."""
    engine.seed_backtest(_rows(20))
    s = engine.stats()
    assert s["n_trades"] == 0
    assert s["win_rate"] == 0.0
    assert s["n_seeded"] == 20


def test_live_trades_count_alongside_seeded_ones(engine, clock):
    engine.seed_backtest(_rows(10))
    engine.risk = eager()
    engine.tick(Candle(HOUR * 99, 100.0, 100.5),
                market_at(clock, 0.5, implied_up=0.30), 0.0045)
    engine.finalize(HOUR * 99, close_price=101.0)
    s = engine.stats()
    assert s["n_trades"] == 1 and s["n_wins"] == 1
    assert s["n_seeded"] == 10


def test_a_pre_kind_state_file_still_knows_its_seeded_rows(tmp_path):
    """State written before the `kind` field existed carries seeded rows
    identifiable only by the title seed_backtest stamped on them."""
    row = {"hour_key": HOUR, "side": "UP", "entry_price": 0.4, "shares": 10.0,
           "stake": 4.0, "model_up": 0.6, "market_up": 0.4, "edge": 0.2,
           "entered_at": 1.0, "won": True, "pnl": 6.0}
    (tmp_path / "state.json").write_text(json.dumps({
        "bankroll": 10_006.0, "equity": [], "open_position": None,
        "trades": [dict(row, title="backtest"),
                   dict(row, title="Bitcoin Up or Down")]}))
    s = eng.Engine(tmp_path / "state.json").stats()
    assert s["n_trades"] == 1
    assert s["n_seeded"] == 1


# --------------------------------------------------------------------------- #
# Scoring every hour, traded or not
# --------------------------------------------------------------------------- #
def test_the_hour_is_scored_even_when_no_trade_is_taken(engine, clock):
    """The paper P&L only grades hours the engine traded — the model's boldest
    claims. The score log records every hour, which is the sample the
    model-vs-market comparison actually needs."""
    engine.tick(Candle(HOUR, 100.0, 100.0),
                market_at(clock, 0.5, implied_up=0.50), 0.0045)
    assert engine.open_position is None, "no edge, no trade"
    assert engine.pending_score["hour_key"] == HOUR

    engine.tick(Candle(HOUR * 2, 101.0, 101.0), market_at(clock, 0.9), 0.0045)
    assert len(engine.scorelog) == 1
    row = engine.scorelog[0]
    assert row["outcome"] == 1.0
    assert row["market_up"] == 0.5


def test_no_snapshot_before_the_scoring_point(engine, clock):
    """At the top of the hour the model is pinned near 0.5 by construction —
    scoring there would compare nothing to nothing."""
    engine.tick(Candle(HOUR, 100.0, 100.0), market_at(clock, 0.9), 0.0045)
    assert engine.pending_score is None


def test_the_first_reading_past_the_point_is_the_one_kept(engine, clock):
    """One snapshot per hour, taken mid-hour. Re-snapshotting later would let
    the log drift toward the end of the hour, where model and market both
    collapse to the sign of the move and the comparison degenerates."""
    engine.tick(Candle(HOUR, 100.0, 100.4),
                market_at(clock, 0.45, implied_up=0.50), 0.0045)
    first = engine.pending_score["model_up"]
    engine.tick(Candle(HOUR, 100.0, 100.9),
                market_at(clock, 0.20, implied_up=0.50), 0.0045)
    assert engine.pending_score["model_up"] == first


def test_a_scored_hour_survives_a_restart(engine, tmp_path, clock):
    engine.tick(Candle(HOUR, 100.0, 100.0), market_at(clock, 0.5), 0.0045)
    engine.tick(Candle(HOUR * 2, 101.0, 101.0), market_at(clock, 0.9), 0.0045)
    reopened = eng.Engine(tmp_path / "state.json")
    assert len(reopened.scorelog) == 1


def test_a_voided_hour_is_not_scored(engine, clock):
    """An hour whose real close could not be recovered has no outcome to score
    against — inventing one would poison the very comparison the log exists for."""
    engine.tick(Candle(HOUR, 100.0, 100.0), market_at(clock, 0.5), 0.0045)
    engine.tick(Candle(HOUR * 4, 105.0, 105.0), market_at(clock, 0.9), 0.0045)
    assert engine.scorelog == []
    assert engine.pending_score is None


def test_the_score_log_is_capped(engine, clock):
    engine.scorelog = [{"hour_key": i, "open": 1.0, "model_up": 0.5,
                        "market_up": 0.5, "tau": 0.5, "outcome": 1.0,
                        "close": 1.0} for i in range(eng.SCORELOG_MAX)]
    engine.tick(Candle(HOUR, 100.0, 100.0), market_at(clock, 0.5), 0.0045)
    engine.tick(Candle(HOUR * 2, 101.0, 101.0), market_at(clock, 0.9), 0.0045)
    assert len(engine.scorelog) == eng.SCORELOG_MAX
    assert engine.scorelog[-1]["hour_key"] == HOUR


def test_model_vs_market_refuses_a_small_sample(engine):
    engine.scorelog = [{"model_up": 0.7, "market_up": 0.5, "outcome": 1.0}
                       for _ in range(10)]
    r = engine.model_vs_market()
    assert r["model_brier"] < r["market_brier"]
    assert "too few" in r["verdict"]


def test_model_vs_market_calls_a_clear_win(engine):
    win = {"model_up": 0.9, "market_up": 0.5, "outcome": 1.0}
    lose = {"model_up": 0.1, "market_up": 0.5, "outcome": 0.0}
    engine.scorelog = [win, lose] * 60
    r = engine.model_vs_market()
    assert r["brier_diff"] < 0
    assert "beats the market" in r["verdict"]


def test_model_vs_market_reads_a_tie_as_noise(engine):
    engine.scorelog = [{"model_up": 0.5, "market_up": 0.5,
                        "outcome": float(i % 2)} for i in range(200)]
    r = engine.model_vs_market()
    assert "noise" in r["verdict"]


def test_model_vs_market_on_an_empty_log_is_not_an_error(engine):
    r = engine.model_vs_market()
    assert r["n"] == 0
