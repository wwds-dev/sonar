"""Tests for the historical replay.

The result that matters from this module is a *negative* one — momentum shows no
edge — and a negative result is only worth anything if the instrument that
produced it can detect a positive one. So the load-bearing test here feeds the
backtester a series that is rigged to drift and checks that it says so. Without
that, "no edge detected" is indistinguishable from a broken detector.
"""

import math

import pytest

from sonar import backtest, scoring


def synthetic(drift_per_bar: float, n: int = 900, vol: float = 0.01,
              seed: int = 7) -> backtest.Bars:
    """A deterministic pseudo-random walk with a known drift baked in."""
    bars = backtest.Bars(symbol="SYN")
    price = 100.0
    state = seed
    for i in range(n):
        state = (1103515245 * state + 12345) % (2 ** 31)
        shock = ((state / (2 ** 31)) - 0.5) * 2 * vol
        price *= math.exp(drift_per_bar + shock)
        bars.time.append(i * 86400)
        bars.open.append(price)
        bars.high.append(price * (1 + vol))
        bars.low.append(price * (1 - vol))
        bars.close.append(price)
    return bars


def test_detects_a_strong_upward_drift():
    """The control: rig the series upward and the LONGs must beat the baseline."""
    trials = backtest.run_symbol(synthetic(0.004), horizon_days=5, step=2)
    longs = [t for t in trials if t["direction"] == "LONG"]
    assert len(longs) > 50
    hit = sum(1 for t in longs if t["outcome"] == "TARGET") / len(longs)
    baseline = scoring.barrier_probability(scoring.K_TARGET, scoring.K_STOP)
    assert hit > baseline + 0.05, (
        f"detector missed a real drift: {hit:.3f} vs baseline {baseline:.3f}")


def test_detects_a_strong_downward_drift():
    trials = backtest.run_symbol(synthetic(-0.004), horizon_days=5, step=2)
    shorts = [t for t in trials if t["direction"] == "SHORT"]
    assert len(shorts) > 50
    hit = sum(1 for t in shorts if t["outcome"] == "TARGET") / len(shorts)
    baseline = scoring.barrier_probability(scoring.K_TARGET, scoring.K_STOP)
    assert hit > baseline + 0.05


def test_summary_calls_a_real_edge_significant():
    trials = [{"outcome": "TARGET", "predicted": 0.4, "bars_held": 3,
               "momentum": 0.03, "rr": 1.5} for _ in range(700)]
    trials += [{"outcome": "STOP", "predicted": 0.4, "bars_held": 3,
                "momentum": 0.03, "rr": 1.5} for _ in range(300)]
    s = backtest.summarise(trials)
    assert s["hit_rate"] == pytest.approx(0.70)
    assert s["significant"] is True
    assert s["implied_edge_sigma"] > 0
    assert "doing something" in s["verdict"]


def test_summary_calls_a_matching_rate_no_edge():
    trials = [{"outcome": "TARGET" if i < 400 else "STOP", "predicted": 0.4,
               "bars_held": 3, "momentum": 0.03, "rr": 1.5} for i in range(1000)]
    s = backtest.summarise(trials)
    assert s["significant"] is False
    assert "no edge" in s["verdict"].lower()


def test_summary_flags_a_harmful_signal():
    trials = [{"outcome": "TARGET" if i < 100 else "STOP", "predicted": 0.4,
               "bars_held": 3, "momentum": 0.03, "rr": 1.5} for i in range(1000)]
    s = backtest.summarise(trials)
    assert s["significant"] is True
    assert "lost money" in s["verdict"]


def test_ambiguous_bar_is_scored_as_a_loss():
    """A bar spanning both barriers must resolve against you.

    Daily data cannot say which came first, so the pessimistic reading is the
    only honest one — anything else quietly inflates every result.
    """
    bars = backtest.Bars(symbol="X", time=[0, 1], open=[100.0, 100.0],
                         high=[100.0, 200.0], low=[100.0, 1.0],
                         close=[100.0, 100.0])
    outcome, _ = backtest._resolve(bars, 0, "LONG", target=110.0, stop=90.0,
                                   max_bars=5)
    assert outcome == "STOP"


def test_unresolved_trials_are_dropped_not_counted():
    flat = backtest.Bars(symbol="F", time=list(range(400)),
                         open=[100.0] * 400, high=[100.0] * 400,
                         low=[100.0] * 400, close=[100.0] * 400)
    assert backtest.run_symbol(flat, horizon_days=5) == []


def test_decisions_never_see_the_future():
    """Momentum at a decision point must match a hand computation from the
    bars available *then* — the property that makes this a backtest at all."""
    bars = synthetic(0.001)
    trials = backtest.run_symbol(bars, horizon_days=5, step=37)
    assert trials
    for t in trials[:5]:
        i = bars.time.index(t["t"])
        expected = bars.close[i] / bars.close[i - 5] - 1
        assert t["momentum"] == pytest.approx(expected, rel=1e-9)


def test_summary_of_nothing_claims_nothing():
    assert backtest.summarise([])["n"] == 0
