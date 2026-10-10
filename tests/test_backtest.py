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


def _trial(outcome, held=6):
    return {"outcome": outcome, "predicted": 0.4, "bars_held": held,
            "momentum": 0.03, "rr": 1.5}


def test_overlapping_trials_widen_the_error_bar():
    """At a step smaller than the holding time, neighbouring trials share the
    bars that decide them — runs of identical outcomes are one reading wearing
    several hats. The binomial bar assumes they are independent; the corrected
    bar must come out wider."""
    trials = []
    for block in range(100):                     # runs of six, alternating
        trials += [_trial("TARGET" if block % 2 == 0 else "STOP")] * 6
    s = backtest.summarise(trials, step=3)
    naive = (0.5 * 0.5 / len(trials)) ** 0.5
    assert s["hit_rate"] == pytest.approx(0.5)
    assert s["std_error"] > naive * 1.2


def test_the_correction_never_narrows_the_bar():
    """Overlap can only reduce the information in a sample. A series whose
    autocorrelation happens to be negative would hand Newey-West a *smaller*
    variance; the wider of the two estimates is the honest one."""
    trials = [_trial("TARGET" if i % 2 == 0 else "STOP") for i in range(600)]
    s = backtest.summarise(trials, step=3)
    naive = (0.5 * 0.5 / len(trials)) ** 0.5
    assert s["std_error"] == pytest.approx(naive, abs=5e-5)  # report rounds to 4dp


def _driftless_walk(n: int, seed: int, sub: int = 24, vol: float = 0.01) -> backtest.Bars:
    """Daily bars cut from a finely stepped driftless walk, so each bar's high
    and low are where the path really went — `synthetic` above gives every bar
    the same ±vol range, which is fine for detecting drift and wrong for
    measuring first-passage odds."""
    import random
    rng = random.Random(seed)
    bars = backtest.Bars(symbol="RW")
    price = 100.0
    for i in range(n):
        o = hi = lo = price
        for _ in range(sub):
            price *= math.exp(rng.gauss(0.0, vol / math.sqrt(sub)))
            hi, lo = max(hi, price), min(lo, price)
        bars.time.append(i * 86400)
        bars.open.append(o)
        bars.high.append(hi)
        bars.low.append(lo)
        bars.close.append(price)
    return bars


@pytest.mark.parametrize("k_target", [1.0, scoring.K_TARGET], ids=["1:1", "1.5:1"])
def test_with_no_drift_the_hit_rate_is_one_over_one_plus_rr(k_target):
    """The identity the app rests on (TESTPLAN 7.5): with nothing to find, a
    target k_t and a stop k_s away are hit first k_s/(k_t+k_s) of the time —
    40% at the shipped 1.5:1 — and the backtest must reproduce it, or every
    'edge' it reports is partly its own bias.

    Measured on 2026-10-10 at wider ratios it does *not* hold: trials that
    reach neither barrier inside the hold window are dropped, and those are
    disproportionately the ones a far target had not yet reached, so 2:1 reads
    30.7% against 33.3% and 3:1 reads 14.4% against 25%. Nothing in the app
    runs those ratios today; anyone who adds an R:R control to the Lab needs
    to account for timeouts first."""
    trials = []
    for seed in range(4):
        trials += backtest.run_symbol(_driftless_walk(1500, seed), horizon_days=5,
                                      step=5, k_target=k_target)
    n = len(trials)
    hit = sum(1 for t in trials if t["outcome"] == "TARGET") / n
    expected = scoring.barrier_probability(k_target, scoring.K_STOP)
    assert expected == pytest.approx(scoring.K_STOP / (k_target + scoring.K_STOP))
    se = math.sqrt(expected * (1 - expected) / n)
    assert n > 800
    assert abs(hit - expected) < 3 * se, f"{hit:.3f} vs {expected:.3f} (±{3*se:.3f})"
