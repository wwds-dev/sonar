"""Tests for the historical replay.

The result that matters from this module is a *negative* one — momentum shows no
edge — and a negative result is only worth anything if the instrument that
produced it can detect a positive one. So the load-bearing test here feeds the
backtester a series that is rigged to drift and checks that it says so. Without
that, "no edge detected" is indistinguishable from a broken detector.
"""

import functools
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


def _dated(trials: list[dict], dates: int | None = None) -> list[dict]:
    """Stamp hand-built trials with entry times, one day apart, cycling over
    ``dates`` distinct days (every trial its own day by default). A verdict
    needs entry dates to count (owner decision P1-B)."""
    dates = dates or len(trials)
    return [dict(t, t=(i % dates) * 86400) for i, t in enumerate(trials)]


def test_summary_calls_a_real_edge_significant():
    trials = [{"outcome": "TARGET", "predicted": 0.4, "bars_held": 3,
               "momentum": 0.03, "rr": 1.5} for _ in range(700)]
    trials += [{"outcome": "STOP", "predicted": 0.4, "bars_held": 3,
                "momentum": 0.03, "rr": 1.5} for _ in range(300)]
    s = backtest.summarise(_dated(trials))
    assert s["hit_rate"] == pytest.approx(0.70)
    assert s["significant"] is True
    assert s["implied_edge_sigma"] > 0
    # QA-13 copy: a positive result is a measurement with its caveats.
    assert "a reason to look closer, not a finding" in s["verdict"]
    assert "doing something" not in s["verdict"]


def test_summary_calls_a_matching_rate_no_edge():
    trials = [{"outcome": "TARGET" if i < 400 else "STOP", "predicted": 0.4,
               "bars_held": 3, "momentum": 0.03, "rr": 1.5} for i in range(1000)]
    s = backtest.summarise(_dated(trials))
    assert s["significant"] is False and s["withheld"] is None
    assert "no edge" in s["verdict"].lower()


def test_summary_flags_a_harmful_signal():
    trials = [{"outcome": "TARGET" if i < 100 else "STOP", "predicted": 0.4,
               "bars_held": 3, "momentum": 0.03, "rr": 1.5} for i in range(1000)]
    s = backtest.summarise(_dated(trials))
    assert s["significant"] is True
    # QA-13 copy: says what happened on these setups, not "lost money".
    assert "lost money" not in s["verdict"]
    # Loop 5 (validator r5 P2-B): a direction picked at random lands this far
    # below about 1 run in 12, so "below" no longer reads as "worse than a
    # coin flip" — it says it does not show that.
    assert ("does not show the lean is worse than a coin flip"
            in s["verdict"]), s["verdict"]
    assert "did worse" not in s["verdict"]
    # "below" already carries the sign: 10% against 40% is 30 points below,
    # not "-30.0 points below" (code-review P3-2).
    assert "Hit rate is 30.0 points below the prediction" in s["verdict"]


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


def _wobble(n: int) -> backtest.Bars:
    """Closes alternating 100, 101: a steady 1% daily move, so volatility and
    momentum are never zero and every bar is a real decision — but at h = 5
    the barriers sit 2.3% and 3.4% away, which the wobble never reaches."""
    closes = [100.0 if i % 2 == 0 else 101.0 for i in range(n)]
    return backtest.Bars(symbol="WOB", time=[i * 86400 for i in range(n)],
                         open=list(closes), high=list(closes), low=list(closes),
                         close=list(closes))


def test_unresolved_trials_are_dropped_not_counted():
    """Every setup here is decided and runs out of time. None of them is a
    result: the default output drops them, and the summary counts them
    without letting one into n or the hit rate.
    (The old version used flat bars, whose volatility is 0, so no setup was
    ever built and the timeout path never ran — code-review P3-5.)"""
    bars = _wobble(400)
    every = backtest.run_symbol(bars, horizon_days=5, keep_timeouts=True)
    assert len(every) > 100
    assert all(t["outcome"] == "TIMEOUT" and t["predicted"] is None
               for t in every)
    assert backtest.run_symbol(bars, horizon_days=5) == []
    timeouts = [t for t in every if not t["short_window"]]
    short = [t for t in every if t["short_window"]]
    s = backtest.summarise([], timeouts=timeouts, short_windows=short)
    assert s["n"] == 0
    assert s["n_timeout"] == len(timeouts) > 100
    assert s["n_short_window"] == len(short) > 0


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


@functools.lru_cache(maxsize=1)
def _forty_walks() -> tuple[backtest.Bars, ...]:
    """Seeds 0–39 at 1,500 bars: enough for 3 se ≤ 2 points at every ratio,
    so the test can see the 2:1 bias it exists to catch. Built once."""
    return tuple(_driftless_walk(1500, seed) for seed in range(40))


def _driftless_run(k_target: float) -> tuple[list[dict], list[dict]]:
    """The resolved setups and the timeouts, split as run() splits them;
    setups with too little data left after them are set aside uncompared."""
    resolved, timeouts = [], []
    for walk in _forty_walks():
        for row in backtest.run_symbol(walk, horizon_days=5, step=5,
                                       k_target=k_target, keep_timeouts=True):
            if row["short_window"]:
                continue
            (timeouts if row["outcome"] == "TIMEOUT" else resolved).append(row)
    return resolved, timeouts


@pytest.mark.parametrize("k_target", [1.0, 1.5, 2.0, 3.0],
                         ids=["1:1", "1.5:1", "2:1", "3:1"])
def test_with_no_drift_the_hit_rate_is_the_prediction_at_every_ratio(k_target):
    """The identity the app rests on (TESTPLAN 7.5; QA-13 success measure 4):
    with nothing to find, the backtest must land on its own prediction, or
    every 'edge' it reports is partly its own bias.

    The prediction is P(target first | resolved within the hold window), not
    the untimed k_s/(k_t+k_s). Setups that touch neither barrier in time are
    left out of the hit rate, and those are mostly the ones a far target had
    not reached yet — so against the untimed 1/(1+R:R) this same sample
    reads −0.65 points at 1.5:1, −2.7 at 2:1 (5.1 se) and −8.7 at 3:1
    (17.8 se): a market with nothing in it passed off as a harmful signal.
    Measured against the time-aware baseline, |delta|/se is 0.51, 0.16, 0.58
    and 0.20.
    Mutation it catches: `predicted` back on plan.p_profit (fails 2:1, 3:1)."""
    resolved, timeouts = _driftless_run(k_target)
    s = backtest.summarise(resolved, step=5, timeouts=timeouts)
    assert 3 * s["std_error"] <= 0.02, s["std_error"]
    assert abs(s["delta"]) < 3 * s["std_error"], (
        f'{s["hit_rate"]:.4f} vs {s["predicted"]:.4f} (±{3 * s["std_error"]:.4f})')
    assert s["baseline_untimed"] == pytest.approx(1 / (1 + k_target), abs=1e-4)
    # The no-edge expectancy is ~0 beyond its own null (T13-8, below), and the
    # realised timeout share sits near what a driftless walk leaves.
    assert abs(s["timeout_share"] - s["timeout_share_expected"]) < 0.05


def test_the_default_output_is_resolved_rows_only():
    """T13-4. Research callers and attribution see what they always saw;
    `keep_timeouts` adds the TIMEOUT rows, with their window and no
    prediction, so a consumer that forgets to filter fails loudly.
    Mutation it catches: TIMEOUT rows leaking into the default output."""
    walk = _driftless_walk(400, 3)
    plain = backtest.run_symbol(walk, horizon_days=5, step=2, k_target=3.0)
    every = backtest.run_symbol(walk, horizon_days=5, step=2, k_target=3.0,
                                keep_timeouts=True)
    assert all(t["outcome"] in ("TARGET", "STOP") for t in plain)
    assert not any(t["short_window"] for t in plain)
    assert [t for t in every
            if t["outcome"] != "TIMEOUT" and not t["short_window"]] == plain
    out = [t for t in every if t["outcome"] == "TIMEOUT"]
    assert out, "a 3:1 target over 400 bars leaves some setups unresolved"
    for t in out:
        assert t["predicted"] is None
        assert t["window"] == t["bars_held"]
        assert t["truncated"] == (t["window"] < 5 * backtest.MAX_HOLD_MULTIPLE)
    for t in plain:
        assert t["k_target"] == 3.0 and t["k_stop"] == scoring.K_STOP
        assert t["horizons"] == pytest.approx(t["window"] / 5)


def test_a_setup_cut_short_by_the_data_gets_its_own_shorter_odds():
    """T13-5. A setup decided near the end of the data could only be watched
    for the bars that were left. If it still resolved, its prediction is the
    one for *that* window — lower for a far target than the full window's.
    Mutation it catches: T = 4 horizons for every row."""
    walk = _driftless_walk(400, 11)
    rows = backtest.run_symbol(walk, horizon_days=5, step=1, k_target=2.0)
    cut = [t for t in rows if t["truncated"]]
    assert cut, "some setup in the last 20 bars resolved"
    full = scoring.resolved_hit_probability(2.0, scoring.K_STOP, 4.0)
    for t in cut:
        assert 10 <= t["window"] < 20           # two horizons is the floor
        assert t["predicted"] == pytest.approx(
            scoring.resolved_hit_probability(2.0, scoring.K_STOP, t["window"] / 5))
        assert t["predicted"] < full
    assert all(t["predicted"] == pytest.approx(full)
               for t in rows if not t["truncated"])


def test_timeouts_are_counted_but_never_enter_the_hit_rate():
    """T13-6 (success measure 6). The summary says how many setups ran out of
    time, how many of those only because the data ended, and what share a
    driftless walk would have left — and the hit rate is the same whether or
    not they are passed.
    Mutation it catches: timeouts counted in n (or as losses)."""
    resolved, timeouts = _driftless_run(2.0)
    bare = backtest.summarise(resolved, step=5)
    s = backtest.summarise(resolved, step=5, timeouts=timeouts)
    assert s["n"] == bare["n"] == len(resolved)
    assert s["hit_rate"] == bare["hit_rate"]
    assert s["predicted"] == bare["predicted"]
    assert s["n_timeout"] == len(timeouts) > 0 and bare["n_timeout"] == 0
    assert s["n_timeout_data_end"] == sum(1 for t in timeouts if t["truncated"])
    assert 0 < s["n_timeout_data_end"] < s["n_timeout"]
    assert s["timeout_share"] == pytest.approx(
        len(timeouts) / (len(resolved) + len(timeouts)), abs=1e-4)
    assert 0.08 < s["timeout_share_expected"] < 0.2


def test_the_implied_drift_inverts_the_timed_prediction():
    """T13-7. 79 of 200 at 1.5:1 over full windows is 39.5% against a timed
    prediction of 39.46%: essentially no drift. Inverting the *untimed* 40%
    instead reads a negative drift out of a market with nothing in it.
    Mutation it catches: implied drift from the untimed baseline."""
    from sonar import calibration
    q = scoring.resolved_hit_probability(1.5, 1.0, 4.0)
    trials = [{"outcome": "TARGET" if i < 79 else "STOP", "predicted": q,
               "bars_held": 6, "rr": 1.5, "k_target": 1.5, "k_stop": 1.0,
               "horizons": 4.0} for i in range(200)]
    s = backtest.summarise(trials)
    assert abs(s["implied_edge_sigma"]) < 0.003
    assert calibration.implied_edge(0.395) < -0.008      # what it used to say
    # the sign follows delta
    win = [dict(t, outcome="TARGET") for t in trials[:20]]
    assert backtest.summarise(win + trials[79:])["implied_edge_sigma"] < 0
    assert backtest.summarise(trials[:79] + win * 3)["implied_edge_sigma"] > 0
    # exactly on the prediction it is exactly zero (1:1 is 0.5 at any window)
    even = [dict(t, k_target=1.0, rr=1.0, predicted=0.5,
                 outcome="TARGET" if i % 2 else "STOP")
            for i, t in enumerate(trials)]
    assert backtest.summarise(even)["implied_edge_sigma"] == pytest.approx(0, abs=1e-6)


def test_hand_built_trials_reproduce_the_untimed_inversion():
    """T13-7. A trial with no window is untimed, which is exactly what
    calibration.implied_edge inverts — the old figure, kept for them."""
    from sonar import calibration
    for wins in (300, 400, 550, 700):
        trials = [{"outcome": "TARGET" if i < wins else "STOP", "predicted": 0.4,
                   "bars_held": 3, "rr": 1.5} for i in range(1000)]
        s = backtest.summarise(trials)
        assert s["implied_edge_sigma"] == pytest.approx(
            calibration.implied_edge(wins / 1000), abs=1e-4)


def test_expectancy_is_at_each_trials_own_ratio():
    """T13-8. At 3:1 a win pays 3R, whatever the shipped 1.5:1 constant says;
    and over resolved setups a market with nothing in it scores a negative
    raw expectancy, which is why the Lab shows the part beyond that null.
    Mutation it catches: expectancy at the shipped-constant rr."""
    resolved, timeouts = _driftless_run(3.0)
    s = backtest.summarise(resolved, step=5, timeouts=timeouts)
    hit = sum(1 for t in resolved if t["outcome"] == "TARGET") / len(resolved)
    assert s["expectancy_r"] == pytest.approx(hit * 3 - (1 - hit), abs=1e-4)
    assert s["expectancy_r"] < -0.2                       # q·rr − (1−q) at 3:1
    assert abs(s["expectancy_vs_null_r"]) < 3 * (1 + 3) * s["std_error"]


def test_a_whole_run_splits_timeouts_from_everything_downstream(monkeypatch):
    """run() asks for the timeouts, counts them, and hands every downstream
    reading — buckets, timing, attribution — the resolved setups only.
    Mutation it catches: run() not passing the timeouts, or passing them on."""
    walks = {f"S{i}": _driftless_walk(600, 50 + i) for i in range(3)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    r = backtest.run(list(walks), horizon_days=5, step=3)
    assert r["n_timeout"] > 0
    assert sum(b["n"] for b in r["buckets"]) == r["n"]
    assert r["attribution"]["n"] == r["n"]
    assert r["timing"]["hold_median"] is not None


def test_a_setup_with_under_two_horizons_left_is_counted_not_compared(monkeypatch):
    """P1-1 (owner decision: window floor). A setup decided so near the end of
    the data that under two horizons of bars follow it is not compared with
    the baseline, whatever happened to it: it carries no prediction, stays out
    of the default output and n, and run() counts it with the data-end
    exclusions as `n_short_window`. Exactly two horizons is compared.
    Mutation it catches: the floor dropped, or `<` turned into `<=`."""
    walk = _driftless_walk(400, 11)
    every = backtest.run_symbol(walk, horizon_days=5, step=1, keep_timeouts=True)
    short = [t for t in every if t["short_window"]]
    assert short
    assert all(t["window"] < 2 * 5 and t["truncated"] for t in short)
    assert all(t["predicted"] is None for t in short)
    assert any(t["outcome"] != "TIMEOUT" for t in short), \
        "some short-window setup resolved, and still is not compared"
    kept = [t for t in every if not t["short_window"]]
    assert all(t["horizons"] >= backtest.MIN_WINDOW_HORIZONS for t in kept)
    assert any(t["window"] == 10 for t in kept)   # T = 2 exactly is compared
    # A full window is four horizons, so the floor never touches it.
    assert backtest.MAX_HOLD_MULTIPLE >= backtest.MIN_WINDOW_HORIZONS
    assert not any(t["short_window"] for t in every if not t["truncated"])

    plain = backtest.run_symbol(walk, horizon_days=5, step=1)
    assert not any(t["short_window"] for t in plain)
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walk)
    r = backtest.run(["RW"], horizon_days=5, step=1)
    timeouts = [t for t in every
                if t["outcome"] == "TIMEOUT" and not t["short_window"]]
    resolved = [t for t in kept if t["outcome"] != "TIMEOUT"]
    assert resolved == plain
    assert r["n"] == len(resolved)
    assert r["n_short_window"] == len(short)
    assert r["n_timeout"] == len(timeouts)


def _wobble_then_a_jump(decisions: int, up: bool, day: int = 0) -> backtest.Bars:
    """`_wobble`, cut so that at h = 5, step 20 the last decision has two bars
    left, and ending on one 10% jump. Every earlier decision has its full
    20-bar window inside the wobble and runs out of time; the last one sees
    the jump, which no driftless walk with this volatility makes in two bars.
    The jump's direction is the coin: it says nothing about the setup's.
    ``day`` shifts the calendar, so instruments can enter on different dates."""
    bars = _wobble(backtest.MIN_LOOKBACK + 20 * decisions + 3)
    bars.time = [t + day * 86400 for t in bars.time]
    last = bars.close[-2] * (1.10 if up else 0.90)
    bars.close[-1] = bars.open[-1] = last
    bars.high[-1] = max(last, bars.close[-2])
    bars.low[-1] = min(last, bars.close[-2])
    return bars


def test_a_short_window_cannot_pass_a_jump_off_as_a_finding(monkeypatch):
    """P1-1 regression, the false positive in miniature. Over a window this
    short, the driftless baseline calls the far target nearly unreachable
    (about 13% of resolved setups at 1.5:1), so real prices that jump read far
    above it. Here the jump is a coin flip — up on half the instruments, down
    on the other half — and without the floor that run says the hit rate
    *beats the prediction*. With the floor nothing here is compared: the run
    says so, and how many ran out of time and of data.
    Mutation it catches: the floor removed (the floored run would read
    'beats the prediction'). 120 instruments entering on 120 different days,
    so the unfloored run clears the minimum sample for a verdict (P1-B)."""
    walks = {f"J{i}": _wobble_then_a_jump(10, up=i % 2 == 0, day=i)
             for i in range(120)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])

    with monkeypatch.context() as m:
        m.setattr(backtest, "MIN_WINDOW_HORIZONS", 0.0)
        unfloored = backtest.run(list(walks), horizon_days=5, step=20)
    assert unfloored["n"] == 120 and unfloored["hit_rate"] == pytest.approx(0.5)
    assert unfloored["predicted"] < 0.2
    assert unfloored["significant"] and unfloored["delta"] > 0.3
    assert "beats the prediction" in unfloored["verdict"]

    r = backtest.run(list(walks), horizon_days=5, step=20)   # the shipped floor
    assert r["n"] == 0
    assert "beats" not in r["verdict"]
    assert r["n_short_window"] == 120
    assert r["n_timeout"] == 120 * 10


def test_a_run_where_every_setup_runs_out_still_says_how_many(monkeypatch):
    """QA P3-5. n = 0 is not 'nothing happened': every setup ran out of time
    or of data, and the summary carries both counts for the Lab and the
    Terminal to show. With setups too near the end of the data among them
    the headline is 'nothing to compare', not 'no resolved trials' — some
    did resolve (code-review r2 P3-1)."""
    walks = {f"W{i}": _wobble(300) for i in range(3)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    r = backtest.run(list(walks), horizon_days=5, step=3)
    assert r["n"] == 0 and r["verdict"] == "nothing to compare"
    assert r["n_timeout"] > 100 and r["n_short_window"] > 0
    assert r["n_timeout_data_end"] >= 0


def test_no_backtest_verdict_promises_anything():
    """T11-8's copy guard, for the backtest (QA P3-6). Every branch of
    _verdict, either sign, small and large: no 'edge' beyond the two phrases
    that deny one, no profit, no money, no certainty. A reader without finance
    training takes these sentences at face value. 'not a guarantee' is a
    denial, as the two edge phrases are; a bare 'guarantee' still fails.
    None counts standard errors either: the bar is not a calibrated 2-se
    test (validator r5 P2-A)."""
    allowed = ("no edge detected", "what no edge is supposed to look like",
               "not a guarantee")
    cases = {
        "within": [(0.004, 0.005, False), (-0.009, 0.005, False)],
        "beats": [(0.031, 0.01, True), (0.25, 0.002, True)],
        "below": [(-0.031, 0.01, True), (-0.30, 0.002, True)],
    }
    for marker, args in cases.items():
        for delta, se, significant in args:
            verdict = backtest._verdict(delta, se, significant)
            assert marker in verdict, (marker, verdict)
            low = verdict.lower()
            for phrase in allowed:
                low = low.replace(phrase, "")
            for banned in ("edge", "profit", "money", "whale", "guarantee",
                           "certain", "doing something", "standard error"):
                assert banned not in low, (marker, banned, verdict)
            # one sign, in words or in digits, never both
            assert "below the prediction" not in verdict or "-" not in verdict


# --------------------------------------------------------------------------- #
# When there is no verdict (owner decisions P1-A and P1-B, round 2)
# --------------------------------------------------------------------------- #
def _seventy_in_a_hundred(n: int) -> list[dict]:
    """n hand-built trials at 1.5:1, 70% of them wins, interleaved so runs of
    one outcome are short: far above the 40% prediction at any n here."""
    return [{"outcome": "TARGET" if i % 10 < 7 else "STOP", "predicted": 0.4,
             "bars_held": 3, "momentum": 0.03, "rr": 1.5, "symbol": "S"}
            for i in range(n)]


def test_no_verdict_above_a_120_day_horizon():
    """P1-A. Above 120 days an instrument's own trend dominates the
    comparison — a coin-flip direction read +2 to +3 points 'above the
    prediction' at 5y h = 210–250 (model-validator r2). Every number is still
    returned; the verdict says why there is none, and is never 'significant'.
    Mutation it catches: the cap removed, or `>` turned into `>=`."""
    assert backtest.MAX_VERDICT_HORIZON == 120
    trials = _dated(_seventy_in_a_hundred(1000))
    at = backtest.summarise(trials, horizon_days=120)
    above = backtest.summarise(trials, horizon_days=121)
    assert at["significant"] is True and at["withheld"] is None
    assert "beats the prediction" in at["verdict"]
    assert above["significant"] is False and above["withheld"] == "horizon"
    for key in ("n", "hit_rate", "predicted", "delta", "std_error",
                "implied_edge_sigma", "expectancy_vs_null_r"):
        assert above[key] == at[key], key
    v = above["verdict"]
    assert "121-day horizon" in v and "own trend dominates" in v
    assert "without a verdict" in v and "beats" not in v
    # a hand-built summary with no horizon is not capped
    assert backtest.summarise(trials)["withheld"] is None


def test_a_whole_run_at_a_long_horizon_gives_no_verdict(monkeypatch):
    """P1-A through run(): the horizon reaches summarise. A rigged upward
    drift beats the prediction at 120 days and is shown without a verdict
    at 125. The walks are 1,300 bars so the 120-day entries span the five
    horizons (870 days) a verdict also needs (loop 3).
    Mutation it catches: run() not passing the horizon on."""
    walks = {f"D{i}": synthetic(0.004, n=1300, seed=7 + i) for i in range(2)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    at = backtest.run(list(walks), horizon_days=120, step=3)
    assert at["n"] >= backtest.MIN_VERDICT_TRIALS
    assert at["significant"] and at["delta"] > 0 and at["withheld"] is None
    above = backtest.run(list(walks), horizon_days=125, step=3)
    assert above["n"] >= backtest.MIN_VERDICT_TRIALS and above["delta"] > 0
    assert above["significant"] is False and above["withheld"] == "horizon"
    assert "125-day horizon" in above["verdict"]


def test_no_verdict_on_fewer_than_100_compared_setups():
    """P1-B. 99 setups is too few to judge, however far off the prediction;
    100 is enough. The verdict says so with the counts.
    Mutation it catches: the minimum dropped, or `<` turned into `<=`."""
    assert backtest.MIN_VERDICT_TRIALS == 100
    few = backtest.summarise(_dated(_seventy_in_a_hundred(99)))
    enough = backtest.summarise(_dated(_seventy_in_a_hundred(100)))
    assert enough["significant"] is True and enough["withheld"] is None
    assert few["significant"] is False and few["withheld"] == "too_few"
    assert few["hit_rate"] == pytest.approx(70 / 99, abs=1e-4)   # numbers kept
    assert few["verdict"].startswith("Too few to judge: 99 compared setups "
                                     "from 99 entry dates."), few["verdict"]


def test_no_verdict_on_fewer_than_20_entry_dates():
    """P1-B. A thousand setups entered on 19 days are a few market moves,
    not a thousand readings; 20 days is enough. Rows without an entry time
    count no date, so a hand-built sample without them gets no verdict.
    Mutation it catches: the date minimum dropped, `<` turned into `<=`, or
    dates counted per row instead of per day."""
    assert backtest.MIN_VERDICT_DATES == 20
    trials = _seventy_in_a_hundred(1000)
    on19 = backtest.summarise(_dated(trials, dates=19))
    on20 = backtest.summarise(_dated(trials, dates=20))
    assert on20["significant"] is True and on20["n_entry_dates"] == 20
    assert on19["significant"] is False and on19["withheld"] == "too_few"
    assert on19["n_entry_dates"] == 19
    assert "1,000 compared setups from 19 entry dates" in on19["verdict"]
    undated = backtest.summarise(trials)
    assert undated["n_entry_dates"] == 0 and undated["withheld"] == "too_few"
    # Two entries the same day are one date (a timestamp is not a date).
    same_day = [dict(t, t=(i // 2) * 86400 + (i % 2) * 3600)
                for i, t in enumerate(trials[:200])]
    assert backtest.summarise(same_day)["n_entry_dates"] == 100


def test_the_error_bar_can_never_read_zero():
    """P1-B. Every setup a stop gave se = 0 and '±0.00 at 2 s.e.'
    (model-validator r2, 1y h = 114–120). The bar is never below the
    Agresti–Coull standard error at z = 2: two wins and two losses added,
    so the rate it is taken at is never 0 or 1.
    Mutation it catches: the floor removed."""
    stops = [{"outcome": "STOP", "predicted": 0.4, "bars_held": 3, "rr": 1.5}
             for _ in range(15)]
    s = backtest.summarise(_dated(stops))
    p = 2 / 19
    assert s["std_error"] == pytest.approx(math.sqrt(p * (1 - p) / 19), abs=1e-4)
    assert s["std_error"] > 0.05
    wins = [dict(t, outcome="TARGET") for t in stops]
    assert backtest.summarise(_dated(wins))["std_error"] == s["std_error"]
    # Enough of them for a verdict: still a real bar, and still a verdict.
    many = backtest.summarise(_dated(stops * 14))          # 210 stops
    assert many["std_error"] > 0.005 and many["significant"] is True
    assert "below the prediction" in many["verdict"]


def test_the_error_bar_floor_leaves_an_ordinary_sample_alone():
    """At 40 in 100 the binomial bar is already the wider one; the floor only
    reaches in when the sample is lopsided."""
    # T S T S S: no two wins in a row, so overlap does not widen it either
    trials = [{"outcome": "TARGET" if i % 5 in (0, 2) else "STOP",
               "predicted": 0.4, "bars_held": 1, "rr": 1.5} for i in range(1000)]
    s = backtest.summarise(_dated(trials))
    assert s["std_error"] == pytest.approx(math.sqrt(0.24 / 1000), abs=5e-5)


def test_withheld_verdicts_promise_nothing_either():
    """T11-8's copy guard over the two new verdicts."""
    texts = [backtest._withheld_verdict("horizon", 250, 1234, 300),
             backtest._withheld_verdict("too_few", 120, 15, 9)]
    for verdict in texts:
        low = verdict.lower()
        for banned in ("edge", "profit", "money", "whale", "guarantee",
                       "certain", "doing something", "beats", "below"):
            assert banned not in low, (banned, verdict)
    assert "250-day horizon" in texts[0]
    assert "15 compared setups from 9 entry dates" in texts[1]


def test_a_positive_verdict_has_one_sign_in_words():
    """'beats … by +3.1 points' says the sign twice (QA r2 P3)."""
    v = backtest._verdict(0.031, 0.01, True)
    assert "beats the prediction by 3.1 points" in v and "+" not in v


def test_the_verdicts_name_the_error_bar_and_what_it_misses():
    """Loop 5 (validator r5 P2-A, P2-B). The verdicts say Δ is outside its
    error bar, not 'more than two standard errors': on these prices a
    direction picked at random for a whole asset class landed outside it
    about 1 run in 10, not 1 in 20. 'beats' says so; 'below' no longer says
    the lean did worse than a coin flip. 'within' is unchanged.
    Mutation it catches: the old copy back, or the bar left out."""
    assert backtest._verdict(0.031, 0.009, True) == (
        "Hit rate beats the prediction by 3.1 points, outside its error bar "
        "(±1.8). That bar is not a guarantee: in our tests on these prices, a "
        "direction picked at random for a whole asset class landed outside it "
        "about 1 run in 10. Before costs, from one replay of past prices: a "
        "reason to look closer, not a finding.")
    assert backtest._verdict(-0.031, 0.009, True) == (
        "Hit rate is 3.1 points below the prediction, outside its error bar "
        "(±1.8). A direction picked at random can land this far below too, "
        "so this does not show the lean is worse than a coin flip. Before "
        "costs, from one replay of past prices.")
    assert backtest._verdict(0.011, 0.009, False) == (
        "Realised hit rate is within 1.8 points of the barrier model's "
        "prediction — no edge detected. This is what no edge is supposed to "
        "look like.")
    assert "can read above the prediction" in backtest._withheld_verdict(
        "horizon", 250, 1234, 300)


# --------------------------------------------------------------------------- #
# What was compared (orchestrator, round 2: P2-A and P2-C disclosure)
# --------------------------------------------------------------------------- #
def test_the_summary_names_the_instruments_and_dates_actually_compared(monkeypatch):
    """A long horizon can leave only crypto compared while 129 instruments
    were fetched, and the floor moves the compared entries earlier
    (model-validator r2 P2-A, P2-C). The summary carries the instruments that
    reached the comparison, by class, and the first and last entry dates.
    Mutation it catches: the fetched count reported as the compared one."""
    import datetime as dt
    walks = {"AAPL": _driftless_walk(400, 1), "BTC-USD": _driftless_walk(400, 2),
             "ETH-USD": _driftless_walk(400, 3), "ZZZ": _driftless_walk(400, 4),
             "MSFT": _wobble(300)}               # fetched, never compared
    for sym, bars in walks.items():
        bars.symbol = sym
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    r = backtest.run(list(walks), horizon_days=5, step=3)
    assert r["symbols"] == 5
    assert r["symbols_compared"] == 4
    assert r["compared_by_class"] == {"Crypto": 2, "Equity": 1, "other": 1}
    rows = [t for sym in walks for t in backtest.run_symbol(walks[sym], 5, step=3)]
    days = sorted({dt.datetime.utcfromtimestamp(t["t"]).date() for t in rows})
    assert r["n_entry_dates"] == len(days)
    assert r["first_entry"] == days[0].isoformat()
    assert r["last_entry"] == days[-1].isoformat()
    # n = 0 still says how many were compared: none.
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: _wobble(300))
    assert backtest.run(["MSFT"], horizon_days=5)["symbols_compared"] == 0


def test_the_longest_comparable_horizon_matches_what_a_run_compares():
    """A compared setup needs one horizon of bars before it and two after it,
    on the step grid, so two years of weekday bars stop at about 166 days
    (code-review r2). The figure the screen quotes is checked against
    run_symbol itself, not against the formula."""
    assert backtest.longest_comparable_horizon(502, step=3) == 166
    for n_bars, step in ((140, 1), (140, 3), (260, 5), (502, 3)):
        walk = _driftless_walk(n_bars, 5)
        h = backtest.longest_comparable_horizon(n_bars, step=step)

        def compared(hz):
            return [t for t in backtest.run_symbol(walk, hz, step=step,
                                                   keep_timeouts=True)
                    if not t["short_window"]]
        assert compared(h), (n_bars, step, h)
        assert not compared(h + 1), (n_bars, step, h)


def test_a_run_reports_the_longest_horizon_its_data_can_compare(monkeypatch):
    walks = {"A": _driftless_walk(300, 1), "B": _driftless_walk(140, 2)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    r = backtest.run(list(walks), horizon_days=120, step=3)
    assert r["n"] == 0 and r["verdict"] == "nothing to compare"
    assert r["longest_comparable_horizon"] == \
        backtest.longest_comparable_horizon(300, step=3)


def test_the_terminal_range_covers_the_profiles_horizon():
    """code-review r2 P2-1: the 'This year' profile (250 days) on two years of
    bars compared nothing. A horizon needs one horizon of history and two
    after the entry, so past ~156 days the replay reads five years."""
    from sonar import horizon
    assert backtest.range_for_horizon(5) == "2y"
    assert backtest.range_for_horizon(156) == "2y"
    assert backtest.range_for_horizon(157) == "5y"
    assert backtest.range_for_horizon(horizon.YEAR.momentum_days) == "5y"
    for hz in (horizon.INTRADAY, horizon.WEEK, horizon.MONTH, horizon.QUARTER):
        assert backtest.range_for_horizon(hz.momentum_days) == "2y", hz.name


def test_data_end_timeouts_count_only_the_compared_windows(monkeypatch):
    """code-review r2 P3-3. `n_timeout_data_end` is the timeouts cut short by
    the end of the data that were still long enough to compare (2 ≤ T < 4);
    the shorter ones are `n_short_window`, never both.
    Mutation it catches: short windows also counted as data-end timeouts."""
    walks = {f"R{i}": _driftless_walk(400, 20 + i) for i in range(4)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    r = backtest.run(list(walks), horizon_days=5, step=1)
    every = [t for w in walks.values()
             for t in backtest.run_symbol(w, 5, step=1, keep_timeouts=True)]
    data_end = [t for t in every if t["outcome"] == "TIMEOUT"
                and t["truncated"] and not t["short_window"]]
    assert data_end and r["n_short_window"] > 0
    assert r["n_timeout_data_end"] == len(data_end)


# --------------------------------------------------------------------------- #
# Non-positive prices (model-validator r2 P2-D: CL=F closed at −37.63)
# --------------------------------------------------------------------------- #
def _with_a_negative_close(at: int = 150, n: int = 320) -> backtest.Bars:
    bars = synthetic(0.0, n=n, seed=3)
    bars.close[at] = bars.open[at] = -37.63
    bars.low[at] = -40.32
    bars.close[at + 1] = 0.0
    return bars


def test_volatility_skips_returns_through_a_non_positive_close():
    """A 10y run on CL=F crashed with a math domain error: the guard covered
    the earlier close and not the later one."""
    closes = [10.0, 11.0, -37.63, 12.0, 0.0, 13.0, 12.5, 13.5]
    v = backtest._vol(closes)
    # only the returns between two positive closes
    good = [math.log(b / a) for a, b in ((10.0, 11.0), (13.0, 12.5), (12.5, 13.5))]
    mean = sum(good) / 3
    assert v == pytest.approx(math.sqrt(sum((r - mean) ** 2 for r in good) / 2))


def test_a_non_positive_price_never_makes_a_decision():
    """No setup is decided at a price at or below zero, nor from a momentum
    reading that divides by one; the rest of the series is still replayed.
    Mutation it catches: either guard removed (the decision on the negative
    close, or the SHORT read off a negative base, comes back)."""
    bars = _with_a_negative_close()
    for h, step in ((5, 1), (20, 1)):
        rows = backtest.run_symbol(bars, h, step=step, keep_timeouts=True)
        assert rows
        for t in rows:
            i = bars.time.index(t["t"])
            assert bars.close[i] > 0 and bars.close[i - h] > 0, (h, i)
        assert any(bars.time.index(t["t"]) > 151 + h for t in rows)


# --------------------------------------------------------------------------- #
# When there is no verdict, round 3 (owner decisions P1-C and P1-B remainder)
# --------------------------------------------------------------------------- #
def _spread(trials: list[dict], dates: int, every: int) -> list[dict]:
    """Stamp trials with entry times on ``dates`` distinct days ``every``
    calendar days apart, starting at day 0: the entries span
    ``(dates - 1) * every`` days."""
    return [dict(t, t=(i % dates) * every * 86400) for i, t in enumerate(trials)]


def _span_of(trials: list[dict], span_days: int, dates: int = 20) -> list[dict]:
    """Entries on ``dates`` distinct days, the first on day 0 and the last on
    day ``span_days`` exactly."""
    marks = sorted({round(k * span_days / (dates - 1)) for k in range(dates)})
    assert len(marks) == dates and marks[-1] == span_days
    return [dict(t, t=marks[i % dates] * 86400) for i, t in enumerate(trials)]


def test_no_verdict_on_a_single_class_universe():
    """P1-C. The instruments in one class tend to move together on one trend,
    so a coin-flip direction got 'beats the prediction' on 2y Equity, Index
    and Commodity at h ≤ 120 (model-validator r3). A run over one class keeps
    every number and gets no verdict; the whole watchlist gets one. The
    universe is passed in, never guessed from the symbols; a hand-built
    sample (None) is not gated.
    Mutation it catches: the single-class gate removed, or applied to "all"."""
    assert backtest.WHOLE_WATCHLIST == "all"
    trials = _dated(_seventy_in_a_hundred(1000))
    whole = backtest.summarise(trials, horizon_days=5, universe="all")
    equity = backtest.summarise(trials, horizon_days=5, universe="Equity")
    assert whole["significant"] is True and whole["withheld"] is None
    assert equity["significant"] is False and equity["withheld"] == "single_class"
    for key in ("n", "hit_rate", "predicted", "delta", "std_error",
                "implied_edge_sigma", "expectancy_vs_null_r", "n_entry_dates"):
        assert equity[key] == whole[key], key
    v = equity["verdict"]
    assert v.startswith("No verdict on Equity alone."), v
    assert "move together on one trend" in v and "whole watchlist gets one" in v
    assert backtest.summarise(trials, horizon_days=5)["withheld"] is None


def test_a_run_over_one_class_gives_no_verdict(monkeypatch):
    """P1-C through run(): the universe reaches summarise. The same rigged
    drift gets a verdict over the whole watchlist (the default) and none when
    the run is told it covers one class.
    Mutation it catches: run() not passing the universe on."""
    walks = {f"D{i}": synthetic(0.004, n=900, seed=7 + i) for i in range(2)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    whole = backtest.run(list(walks), horizon_days=20, step=3)
    assert whole["significant"] and whole["withheld"] is None
    one = backtest.run(list(walks), horizon_days=20, step=3, universe="Crypto")
    assert one["n"] == whole["n"] and one["delta"] == whole["delta"]
    assert one["significant"] is False and one["withheld"] == "single_class"
    assert one["verdict"].startswith("No verdict on Crypto alone.")


def test_no_verdict_unless_the_entries_span_five_horizons():
    """P1-B remainder. Entries a few weeks apart are mostly one market move
    counted many times: a coin's false 'beats' rate was 9.1% under 2 horizons
    of entry span and 0.9% at 5–10 (model-validator r3). The span is the
    calendar days from the first entry date to the last, and a horizon counts
    trading days, so five horizons of h days is 5 × h × 365/252 calendar
    days, rounded up: 37 at h = 5, 870 at h = 120. A hand-built sample
    without a horizon is not gated.
    Mutation it catches: the gate removed, `<` turned into `<=`, the span
    measured in raw days against 5 × h, or the constant changed."""
    assert backtest.MIN_VERDICT_SPAN_HORIZONS == 5
    assert backtest.min_verdict_span_days(5) == 37
    assert backtest.min_verdict_span_days(60) == 435
    assert backtest.min_verdict_span_days(120) == 870
    rows = _seventy_in_a_hundred(1000)
    for h, need in ((5, 37), (120, 870)):
        short = backtest.summarise(_span_of(rows, need - 1), horizon_days=h)
        enough = backtest.summarise(_span_of(rows, need), horizon_days=h)
        assert enough["significant"] is True and enough["withheld"] is None, h
        assert short["significant"] is False and short["withheld"] == "span", h
        assert short["hit_rate"] == enough["hit_rate"]            # numbers kept
        assert short["entry_span_days"] == need - 1
        assert enough["entry_span_horizons"] == pytest.approx(
            need * 252 / 365 / h, abs=0.01)
    v = backtest.summarise(_span_of(rows, 36), horizon_days=5)["verdict"]
    assert v.startswith("Too close together to judge: these setups were "
                        "entered over 36 days, 4.9 times the 5-day horizon."), v
    assert "at least 5 times the horizon (37 days;" in v
    assert backtest.summarise(_span_of(rows, 19))["withheld"] is None


def test_why_a_verdict_is_withheld_has_one_fixed_order():
    """When several reasons apply the reader gets one, always the same one:
    horizon, then single class, then too few, then span. The two a reader
    can change by picking another setting come before the two that depend
    on the sample. Each step below lifts one reason and the next shows.
    Mutation it catches: any two of the four checks swapped (QA r3 G2)."""
    few_close = _span_of(_seventy_in_a_hundred(99), 19)
    many_close = _span_of(_seventy_in_a_hundred(1000), 19)
    many_wide = _spread(_seventy_in_a_hundred(1000), dates=20, every=50)
    steps = [
        (few_close, 121, "Equity", "horizon"),
        (few_close, 120, "Equity", "single_class"),
        (few_close, 120, "all", "too_few"),
        (many_close, 120, "all", "span"),
        (many_wide, 120, "all", None),
    ]
    for trials, h, universe, why in steps:
        s = backtest.summarise(trials, horizon_days=h, universe=universe)
        assert s["withheld"] == why, (h, universe, len(trials), s["verdict"])
        assert s["significant"] is (why is None)


def test_the_new_withheld_verdicts_promise_nothing_either():
    """T11-8's copy guard over the round-3 sentences: the single-class and
    span verdicts, the attention sentence and the attribution note on a run
    that gets no verdict."""
    texts = [backtest._withheld_verdict("single_class", 60, 5000, 300,
                                        universe="Commodity"),
             backtest._withheld_verdict("span", 120, 1900, 47, span_days=201),
             backtest._news_verdict([{"name": "spike", "delta": 0.1, "n": 50,
                                      "significant": False}], withheld="span"),
             backtest.NOT_JUDGED]
    for verdict in texts:
        low = verdict.lower()
        for banned in ("edge", "profit", "money", "whale", "guarantee",
                       "certain", "doing something", "beats", "below",
                       "shifts the odds", "keep", "drop", "invert"):
            assert banned not in low, (banned, verdict)
    assert "No verdict on Commodity alone." in texts[0]
    assert "201 days" in texts[1] and "120-day horizon" in texts[1]


def _rigged_rows(n: int, dates: int = 100, seed: int = 1) -> list[dict]:
    """Compared rows as run_symbol returns them, in which momentum and an
    attention spike both genuinely sort winners from losers — so, judged,
    the attention test reports a finding and attribution keeps momentum."""
    import random
    rng = random.Random(seed)
    out = []
    for i in range(n):
        m = rng.random()
        spike = i % 2 == 0
        att = 3.0 if spike else -1.0
        p = 0.1 + 0.5 * m + (0.25 if spike else 0.0)
        out.append({"symbol": "AAPL", "t": (i % dates) * 86400,
                    "direction": "LONG", "momentum": 0.2 * m, "vol": 0.01,
                    "outcome": "TARGET" if rng.random() < p else "STOP",
                    "bars_held": 3, "predicted": 0.4, "rr": 1.5,
                    "k_target": 1.5, "k_stop": 1.0, "window": 20,
                    "horizons": 4.0, "truncated": False, "short_window": False,
                    "attention": att, "c_momentum": m, "c_volatility": 0.3,
                    "c_news": max(0.0, min(1.0, (att + 1.0) / 4.0)),
                    "c_catalyst": None})
    return out


def _rigged_run(monkeypatch, rows, **kw) -> dict:
    monkeypatch.setattr(backtest, "fetch_bars",
                        lambda sym, rng: synthetic(0.0, n=60))
    monkeypatch.setattr(backtest, "run_symbol", lambda *a, **k: list(rows))
    return backtest.run(["AAPL"], step=3, **kw)


_JUDGED = {"KEEP", "DROP", "INVERTED", "WEAK", "UNCLEAR"}


def test_a_run_without_a_verdict_claims_no_attention_or_attribution_finding(
        monkeypatch):
    """P2-1 (code-review r3) and P2-F (model-validator r3). A run shown
    without a verdict still printed 'A news spike shifts the odds … beyond
    two standard errors' and attribution KEEP/DROP/INVERTED on the same page.
    Now, whatever the reason — a 121-day horizon, one class, 99 setups, a
    short span — every attention bucket is not significant, the attention
    sentence says there is no reading, and every measured component is 'not
    judged'. The numbers stay. The control, judged, shows both findings,
    each worded as one replay's reading (validator r6 P2-A).
    Mutation it catches: either gate removed, or keyed to one reason only;
    KEEP or INVERTED back to an unhedged instruction."""
    judged = _rigged_run(monkeypatch, _rigged_rows(1000), horizon_days=5)
    assert judged["withheld"] is None
    assert judged["news_verdict"].startswith("A news spike shifts the odds")
    assert any(b["significant"] for b in judged["attention_buckets"])
    verdicts = {c["component"]: c.get("verdict")
                for c in judged["attribution"]["components"]}
    assert verdicts["momentum"] == "KEEP", verdicts
    # Judged, a grade is still one replay's reading, not an instruction
    # (validator r6 P2-A): KEEP says so, and INVERTED, the same readings the
    # other way round, suggests a test rather than a sign flip.
    mom = next(c for c in judged["attribution"]["components"]
               if c["component"] == "momentum")
    spread = mom["spread"]["spread"]
    assert spread > 0
    assert mom["why"] == (f"IC {mom['ic']:+.3f} survives FDR and the top "
                          f"quintile beats the bottom by {spread * 100:.1f} "
                          "points — from one replay of past prices"), mom
    inv = backtest._verdict_for(dict(mom, ic=-mom["ic"],
                                     spread=dict(mom["spread"], spread=-spread)))
    assert inv == {"verdict": "INVERTED", "why": (
        f"IC {-mom['ic']:+.3f} is significant and *negative* — the top "
        f"quintile trails the bottom by {spread * 100:.1f} points. Added with "
        "a positive weight, this component would push the wrong instruments "
        "up the board. Worth testing with its sign flipped, or dropped. From "
        "one replay of past prices: a reason to look closer, not a "
        "finding.")}, inv
    for why in (mom["why"], inv["why"]):
        for banned in ("edge", "profit", "money", "guarantee", "certain",
                       "flip its sign or drop"):
            assert banned not in why.lower(), (banned, why)
    cases = {
        "horizon": (_rigged_rows(1000, dates=1000), {"horizon_days": 121}),
        "single_class": (_rigged_rows(1000),
                         {"horizon_days": 5, "universe": "Equity"}),
        "too_few": (_rigged_rows(99), {"horizon_days": 5}),
        "span": (_rigged_rows(1000, dates=30), {"horizon_days": 5}),
    }
    for why, (rows, kw) in cases.items():
        r = _rigged_run(monkeypatch, rows, **kw)
        assert r["withheld"] == why, (why, r["verdict"])
        assert r["attention_buckets"], why
        assert not any(b["significant"] for b in r["attention_buckets"]), why
        assert r["news_verdict"] == backtest._news_verdict(
            r["attention_buckets"], withheld=why)
        assert r["news_verdict"].startswith("No reading on attention either"), why
        a = r["attribution"]
        assert a["withheld"] == why and a["note"] == backtest.NOT_JUDGED
        measured = [c for c in a["components"] if c.get("ic") is not None]
        assert measured, why
        for c in a["components"]:
            assert c.get("verdict") not in _JUDGED, (why, c)
        for c in measured:
            assert c["verdict"] == "not judged" and c["survives_fdr"] is False
            assert c["ic"] is not None                         # numbers kept
    # 99 is too few, 100 is not: the same gate as the headline
    assert _rigged_run(monkeypatch, _rigged_rows(100),
                       horizon_days=5)["withheld"] is None


def test_attribution_without_a_reason_is_judged_as_before():
    """attribute() with no reason to withhold is unchanged."""
    rows = _rigged_rows(1000)
    assert backtest.attribute(rows) == backtest.attribute(rows, withheld=None)
    assert {c["verdict"] for c in backtest.attribute(rows)["components"]
            if c.get("ic") is not None} <= _JUDGED


# --------------------------------------------------------------------------- #
# Momentum buckets (code-review r3 P2-2: the Lab read '?' and '+0.0')
# --------------------------------------------------------------------------- #
def test_momentum_buckets_carry_a_label_and_their_gap_to_the_prediction(
        monkeypatch):
    """The Lab's bucket table reads `label` and `delta`; the momentum buckets
    had neither, so every row read '?' and '+0.0 vs baseline'. Checked on
    run()'s own output, not on a hand-built shape.
    Mutation it catches: either key dropped, or delta taken against 0 or the
    untimed baseline."""
    walks = {f"D{i}": synthetic(0.004, n=900, seed=7 + i) for i in range(2)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    r = backtest.run(list(walks), horizon_days=20, step=3)
    rows = [t for w in walks.values() for t in backtest.run_symbol(w, 20, step=3)]
    assert r["buckets"]
    labels = {(0.0, 0.02): "0–2%", (0.02, 0.05): "2–5%",
              (0.05, 0.10): "5–10%", (0.10, 1.0): "10–100%"}
    for b in r["buckets"]:
        sel = [t for t in rows if b["lo"] <= abs(t["momentum"]) < b["hi"]]
        hit = sum(1 for t in sel if t["outcome"] == "TARGET") / len(sel)
        pred = sum(t["predicted"] for t in sel) / len(sel)
        assert b["label"] == labels[(b["lo"], b["hi"])]
        assert b["delta"] == pytest.approx(hit - pred, abs=1e-4)
        assert b["delta"] == pytest.approx(b["hit_rate"] - b["predicted"],
                                           abs=2e-4)
    assert any(abs(b["delta"]) > 0.05 for b in r["buckets"])


# --------------------------------------------------------------------------- #
# Setups entered on the same days (owner decisions P1-D and P1-E, loop 4)
# --------------------------------------------------------------------------- #
def test_the_date_clustered_error_bar_is_driscoll_kraay_by_hand():
    """P1-D. The residuals (win − predicted − the run's gap) are summed per
    UTC entry date across every instrument, the daily sums get a Bartlett
    kernel over ``lag_days`` calendar days, and the result is the standard
    error of the mean gap. A trial with no entry time is its own cluster.
    Mutation it catches: no centring on the gap, dates counted per row or by
    timestamp, Bartlett weights 1 or off by one, calendar gaps closed up, or
    undated trials dropped."""
    day = 86400
    rows = [("TARGET", 0 * day + 3600, 0.4), ("TARGET", 0 * day + 82800, 0.4),
            ("STOP", 1 * day + 50000, 0.4), ("TARGET", 3 * day + 10, 0.5),
            ("STOP", None, 0.4), ("STOP", None, 0.4)]
    trials = [{"outcome": o, "t": t, "predicted": p} for o, t, p in rows]
    gap = (0.6 + 0.6 - 0.4 + 0.5 - 0.4 - 0.4) / 6
    d0, d1, d2, d3 = 1.2 - 2 * gap, -0.4 - gap, 0.0, 0.5 - gap
    undated = 2 * (0.4 + gap) ** 2
    lag0 = d0 ** 2 + d1 ** 2 + d3 ** 2 + undated
    assert backtest._dk_se(trials, 0) == pytest.approx(math.sqrt(lag0) / 6)
    lag2 = (lag0 + 2 * (2 / 3) * (d0 * d1 + d1 * d2 + d2 * d3)
            + 2 * (1 / 3) * (d0 * d2 + d1 * d3))
    assert backtest._dk_se(trials, 2) == pytest.approx(math.sqrt(lag2) / 6)
    # A lag longer than the dated days adds nothing past the last one.
    lag9 = (lag0 + 2 * (9 / 10) * (d0 * d1 + d2 * d3) + 2 * (8 / 10) * d1 * d3
            + 2 * (7 / 10) * d0 * d3)
    assert backtest._dk_se(trials, 9) == pytest.approx(math.sqrt(lag9) / 6)


def test_the_lag_is_one_average_hold_in_calendar_days():
    """P1-D's lag rule: L = ceil(avg_bars_held · 365/252) calendar days, the
    conversion the span rule uses. Mutation it catches: the hold read as
    calendar days, rounded down, or the lag dropped."""
    assert backtest._dk_lag_days(3.0) == 5          # 4.35 → 5
    assert backtest._dk_lag_days(5.0) == 8          # 7.24 → 8
    assert backtest._dk_lag_days(1.0) == 2
    assert backtest._dk_lag_days(0.0) == 0
    # in the summary, from the trials' own average hold
    trials = [{"outcome": "TARGET" if (i // 10) % 2 else "STOP", "t": i * 86400,
               "predicted": 0.5, "bars_held": 3, "rr": 1.0} for i in range(400)]
    s = backtest.summarise(trials)
    assert s["dk_lag_days"] == 5
    assert s["se_dk"] == pytest.approx(backtest._dk_se(trials, 5), abs=5e-5)
    # runs of ten days alike: the lag sees them, a shorter one sees less
    assert backtest._dk_se(trials, 5) > backtest._dk_se(trials, 3) \
        > backtest._dk_se(trials, 0)


def _by_day(outcomes_per_day: list[list[str]], every: int = 10) -> list[dict]:
    """Hand-built trials, one inner list per entry date, the dates ``every``
    calendar days apart — wider than the Bartlett lag at a 3-bar hold, so
    only same-day setups count together."""
    return [{"outcome": o, "t": d * every * 86400 + 60 * k, "predicted": 0.4,
             "bars_held": 3, "momentum": 0.03, "rr": 1.5, "symbol": f"S{k}"}
            for d, day in enumerate(outcomes_per_day) for k, o in enumerate(day)]


def test_setups_entered_on_the_same_day_are_one_reading():
    """P1-D. 25 instruments entered on each of 40 days, 45% wins against a
    40% prediction. When each day's setups win or lose together, the 1,000
    setups are 40 readings, and the gap of 5 points is well inside its error
    bar; when every day holds the same mix of wins, the same gap is a
    verdict. The binomial and Newey-West bars cannot tell the two apart.
    Mutation it catches: the date-clustered bar left out of the headline."""
    together = _by_day([["TARGET" if d % 20 < 9 else "STOP"] * 25
                        for d in range(40)])
    # wins and losses alternate within a day, so overlap cannot widen it
    mixed = _by_day([["TARGET", "STOP"] * (12 if d < 10 else 11)
                     + ["STOP"] * (1 if d < 10 else 3) for d in range(40)])
    a, b = backtest.summarise(together), backtest.summarise(mixed)
    assert a["hit_rate"] == b["hit_rate"] == pytest.approx(0.45)
    assert a["withheld"] is None and b["withheld"] is None
    # 40 days whose sums are 25 × (0.55 or −0.45), no cross-day terms
    dk = math.sqrt(625 * (18 * 0.55 ** 2 + 22 * 0.45 ** 2)) / 1000
    assert a["se_dk"] == pytest.approx(dk, abs=5e-5)
    assert a["std_error"] == a["se_dk"] and a["significant"] is False
    assert "no edge detected" in a["verdict"]
    assert b["se_dk"] < b["std_error"] == pytest.approx(
        math.sqrt(0.45 * 0.55 / 1000), abs=5e-5)
    assert b["significant"] is True and "beats the prediction" in b["verdict"]


# A world of correlated instruments for the clustered coin. The measured live
# correlations (model-validator r4, corr.py) are 0.21–0.31 between daily
# returns within a class and 0.06–0.10 between classes, and absolute returns
# co-move at 0.22–0.29 within and 0.08–0.11 between. Here a global factor
# (ρ 0.10) and a class factor (ρ 0.15) give 0.25 within and 0.10 between, and
# a shared log-volatility, global and per class, makes absolute returns
# co-move at about 0.18 within and 0.07 between.
_WORLD_VOL = {"Equity": 0.015, "Index": 0.011, "Forex": 0.006,
              "Crypto": 0.035, "Commodity": 0.018}


def _correlated_world(seed: int, per_class: int = 6, n: int = 504,
                      sub: int = 4, rho_g: float = 0.10, rho_c: float = 0.15
                      ) -> tuple[dict[str, backtest.Bars], dict[str, str]]:
    import datetime as dt
    import random
    rng = random.Random(seed)
    times, d = [], dt.date(2020, 1, 6)
    while len(times) < n:
        if d.weekday() < 5:
            times.append(int(dt.datetime(d.year, d.month, d.day, 21,
                                         tzinfo=dt.timezone.utc).timestamp()))
        d += dt.timedelta(days=1)

    def log_vol(sd: float, phi: float = 0.97) -> list[float]:
        a, out = rng.gauss(0, sd), []
        for _ in range(n):
            a = phi * a + rng.gauss(0, sd * math.sqrt(1 - phi * phi))
            out.append(a)
        return out
    vg = log_vol(0.35)
    vc = {c: log_vol(0.25) for c in _WORLD_VOL}
    g = [[rng.gauss(0, 1) for _ in range(sub)] for _ in range(n)]
    cf = {c: [[rng.gauss(0, 1) for _ in range(sub)] for _ in range(n)]
          for c in _WORLD_VOL}
    wg, wc, we = math.sqrt(rho_g), math.sqrt(rho_c), math.sqrt(1 - rho_g - rho_c)
    walks, cls = {}, {}
    for c, base in _WORLD_VOL.items():
        for k in range(per_class):
            sym = f"{c[:3].upper()}{k}"
            cls[sym] = c
            bars, p = backtest.Bars(symbol=sym), 100.0
            for t in range(n):
                s = base * math.exp(vg[t] + vc[c][t]) / math.sqrt(sub)
                o = hi = lo = p
                for j in range(sub):
                    p *= math.exp(s * (wg * g[t][j] + wc * cf[c][t][j]
                                       + we * rng.gauss(0, 1)))
                    hi, lo = max(hi, p), min(lo, p)
                bars.time.append(times[t])
                bars.open.append(o)
                bars.high.append(hi)
                bars.low.append(lo)
                bars.close.append(p)
            walks[sym] = bars
    return walks, cls


def _clustered_coin_runs(monkeypatch, worlds, horizons, coins) -> list[dict]:
    """Every (world, horizon, coin) summary of a clustered coin: one random
    direction per (class, block of one horizon in calendar days), shared by
    every instrument of the class — correlated across instruments the way
    momentum is, and carrying no information. Each instrument is replayed
    forced LONG and forced SHORT once; a coin picks one row of each pair."""
    import random
    import zlib
    real_plan = scoring.build_plan
    out = []
    for seed in worlds:
        walks, cls = _correlated_world(seed)
        for h in horizons:
            pairs = {}
            for sym, bars in walks.items():
                sides = []
                for side in ("LONG", "SHORT"):
                    monkeypatch.setattr(
                        scoring, "build_plan",
                        lambda price, vol, days, _d, side=side, **kw:
                        real_plan(price, vol, days, side, **kw))
                    sides.append(backtest.run_symbol(bars, h, step=3,
                                                     keep_timeouts=True))
                monkeypatch.setattr(scoring, "build_plan", real_plan)
                pairs[sym] = list(zip(*sides, strict=True))
            block = math.ceil(h * 365 / 252) * 86400
            for coin in coins:
                side, resolved, timeouts, short = {}, [], [], []
                for sym, rows in pairs.items():
                    for long_row, short_row in rows:
                        key = (cls[sym], long_row["t"] // block)
                        if key not in side:
                            side[key] = random.Random(zlib.crc32(
                                f"{seed}|{h}|{coin}|{key}".encode())).random() < 0.5
                        row = long_row if side[key] else short_row
                        (short if row["short_window"] else
                         timeouts if row["outcome"] == "TIMEOUT" else
                         resolved).append(row)
                out.append(backtest.summarise(
                    resolved, step=3, timeouts=timeouts, short_windows=short,
                    horizon_days=h, universe=backtest.WHOLE_WATCHLIST))
    return out


def test_a_correlated_coin_rarely_gets_a_verdict(monkeypatch):
    """P1-D's acceptance test: the clustered coin. Directions that move
    together across a class, as momentum's do, and mean nothing. 5 worlds of
    30 correlated instruments over two years, at the Lab's 5 days and the
    Terminal's 20, 6 coins each: 60 judged runs.

    Measured on 720 such runs (60 worlds): a verdict 18.9% [16.2–21.9] of the
    time with the binomial / Newey-West bar alone, 7.5% [5.8–9.7] with the
    date-clustered floor; the mean z² falls from 2.23 to 1.30. A 2-se
    verdict would be wrong 4.6% of the time if the bar were right, so the
    floor narrows the gap without closing it (the validator's real-bar
    clustered coin: 59% → 11%). Bound: at most 7 of these 60 (11.7%) and a
    mean z² of at most 1.5. These 60 read 5 and 1.35 with the floor, 9 and
    2.32 without it; across twelve disjoint sets of 60 the floored count
    ranged 1–7 and z² 0.78–1.57, the unfloored 2–16 and 1.31–2.60.
    Mutation it catches: the date-clustered floor left out of the headline."""
    runs = _clustered_coin_runs(monkeypatch, worlds=range(5), horizons=(5, 20),
                                coins=range(6))
    assert len(runs) == 60
    assert all(s["withheld"] is None and s["n"] > 2000 for s in runs)
    false = sum(1 for s in runs if s["significant"])
    assert false <= 7, f"{false} of 60 runs gave a verdict on a coin"
    z2 = sum((s["delta"] / s["std_error"]) ** 2 for s in runs) / len(runs)
    assert z2 <= 1.5, z2
    # the floor is what moved: the clustered bar is the wider one on average
    assert sum(s["se_dk"] for s in runs) > 1.2 * sum(
        math.sqrt(s["hit_rate"] * (1 - s["hit_rate"]) / s["n"]) for s in runs)


def test_a_meaningless_clustered_component_is_rarely_graded():
    """Loop 5 (model-validator r5 P1-A, QA r5 P2-1): attribution's tests
    count setups entered on the same day together. The placebo: a news
    component that is one random value per (class, block of one horizon in
    calendar days), plus a little per-setup noise, and says nothing about
    the outcome; replayed with momentum's own directions on correlated walks
    of 20 instruments a class (100), the watchlist's breadth. On real bars
    it was graded KEEP or INVERTED on 24% of judged runs.

    Measured on 360 such runs (60 worlds, h = 20): KEEP or INVERTED 14.7%
    [11.4–18.8] with the Newey-West IC and binomial spread alone, 5.6%
    [3.6–8.4] with the date-clustered floor on both; the mean spread z² from
    4.29 to 1.37, the IC's from 2.29 to 1.52. Over 15 disjoint sets of 24
    the floored spread z² ranged 0.88–1.89 and the unfloored 2.66–5.71; the
    graded count 0–4 against 0–7. These 24 (worlds 0–3) read 2, 1.61 and
    1.57 with the floor; 6, 2.59 and 5.55 without. Bound: at most 3 of 24
    graded, spread z² at most 2.2, IC z² at most 2.0. A regression guard,
    fitted like the clustered coin's: the IC still runs over its nominal
    rate, because a block outlasts the one-hold lag.
    A real component, one setup at a time (IC about 0.08), still reads KEEP.
    Mutation it catches: the date-clustered floor left out of the IC test
    or of the quintile spread."""
    import random
    import zlib
    from statistics import NormalDist
    h, block = 20, math.ceil(20 * 365 / 252) * 86400
    graded, ic_z2, sp_z2, runs = 0, 0.0, 0.0, 0
    for seed in range(4):
        walks, cls = _correlated_world(seed, per_class=20)
        rows = []
        for sym, bars in walks.items():
            for row in backtest.run_symbol(bars, h, step=3, keep_timeouts=True):
                if not row["short_window"] and row["outcome"] != "TIMEOUT":
                    rows.append(dict(row, cls=cls[sym]))
        s = backtest.summarise(rows, step=3, horizon_days=h,
                               universe=backtest.WHOLE_WATCHLIST)
        assert s["withheld"] is None and s["n"] > 10000
        for k in range(6):
            noise = random.Random(zlib.crc32(f"p|{seed}|{h}|{k}|cls".encode()))
            draws: dict = {}
            for t in rows:
                key = (t["cls"], t["t"] // block)
                if key not in draws:
                    draws[key] = random.Random(zlib.crc32(
                        f"{seed}|{h}|{k}|cls|{key}".encode())).random()
                t["c_news"] = 0.8 * draws[key] + 0.2 * noise.random()
            news = next(c for c in backtest.attribute(rows)["components"]
                        if c["component"] == "news")
            graded += news["verdict"] in ("KEEP", "INVERTED")
            ic_z2 += NormalDist().inv_cdf(1 - max(news["p"], 1e-12) / 2) ** 2
            sp_z2 += (news["spread"]["spread"] / news["spread"]["se"]) ** 2
            runs += 1
        if seed == 0:
            real = random.Random(3)
            for t in rows:
                t["c_news"] = 0.05 * (t["outcome"] == "TARGET") + real.random()
            news = next(c for c in backtest.attribute(rows)["components"]
                        if c["component"] == "news")
            assert news["verdict"] == "KEEP", news
    assert runs == 24
    assert graded <= 3, f"{graded} of 24 meaningless components graded"
    assert sp_z2 / runs <= 2.2, sp_z2 / runs
    assert ic_z2 / runs <= 2.0, ic_z2 / runs


def test_the_ic_test_counts_setups_entered_on_the_same_day_together():
    """Loop 5. 40 days of 25 setups: each day the component is high or low
    for every setup and they all win or lose together, so the day is the
    reading. Newey-West, in trial order (one instrument after another, as
    run() lists them), sees 1,000 setups and a large t; clustered by date it
    is about the t of 40 days. The t is the mean of the centred products
    over the wider of the two bars. attribute() runs it at the component's
    own lag, one average hold (5 bars: 8 days), which reaches the next day
    a week on; half of it does not (QA r6 E4).
    Mutation it catches: the date-clustered bar left out of _ic_t, or the
    component's lag shortened."""
    import random

    from sonar.research import stats
    rng = random.Random(4)
    days = []
    for _ in range(40):
        x = rng.random()
        days.append((x, 1.0 if rng.random() < 0.3 + 0.3 * x else 0.0))
    xs, ys, ts = [], [], []
    for _sym in range(25):
        for d, (x, y) in enumerate(days):
            xs.append(x)
            ys.append(y)
            ts.append(d * 7 * 86400)
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    prods = [(x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)]
    t_nw, se_nw = stats.newey_west_t(prods)
    se_dk = backtest._dk_mean_se(prods, ts, 0)
    assert se_dk > 3 * se_nw
    t = backtest._ic_t(xs, ys, ts, 0)
    assert t == pytest.approx(sum(prods) / len(prods) / se_dk)
    assert abs(t) < abs(t_nw) / 3
    # undated setups are each their own cluster: the plain bar, no day sums
    m = sum(prods) / len(prods)
    plain = math.sqrt(sum((p - m) ** 2 for p in prods)) / len(prods)
    assert backtest._ic_t(xs, ys, [None] * len(xs), 0) == pytest.approx(
        m / max(se_nw, plain))
    # attribute() tests the component at its own lag of one average hold
    rows = [{"outcome": "TARGET" if y else "STOP", "predicted": 0.4,
             "bars_held": 5, "t": t, "c_momentum": x, "c_volatility": None,
             "c_news": None, "c_catalyst": None}
            for x, y, t in zip(xs, ys, ts, strict=True)]
    assert backtest._dk_lag_of(rows) == 8
    mom = backtest.attribute(rows)["components"][0]
    assert mom["component"] == "momentum"
    at = {lag: round(stats.normal_p(backtest._ic_t(xs, ys, ts, lag)), 4)
          for lag in (4, 8)}
    assert at[4] != at[8], at                  # the fixture tells them apart
    assert mom["p"] == at[8], (mom["p"], at)


def test_the_quintile_spread_counts_setups_entered_on_the_same_day_together():
    """Loop 5. Each day's 20 setups share one component value and one
    outcome, so the top and bottom fifths are 20 days each, not 200 setups.
    The spread's bar is the wider of the binomial one and the date-clustered
    one; here the clustered one, √20 times wider.
    Mutation it catches: the spread's bar left binomial, or the bottom
    fifth's share added instead of taken away."""
    rows = []
    for d in range(50):
        win = "TARGET" if (d % 2 == 0) == (d < 25) else "STOP"
        for k in range(20):
            rows.append({"t": d * 7 * 86400 + k, "outcome": win,
                         "bars_held": 0, "c_x": d})
    sp = backtest._quintile_spread(rows, "c_x")
    assert sp["n_per_side"] == 200
    binomial = math.sqrt(2 * sp["top"] * (1 - sp["top"]) / 200)
    assert sp["se_dk"] == pytest.approx(math.sqrt(20) * binomial, rel=0.02)
    assert sp["se"] == sp["se_dk"]
    # A day's common move that lands in both fifths cancels in the
    # difference: here every day puts 2 setups in each fifth and all 10 win
    # or lose together, so the clustered bar is 0 and the binomial one shows.
    rows = []
    for d in range(50):
        win = "TARGET" if d % 5 < 2 else "STOP"
        for k, x in enumerate([1000 + d] * 2 + [500 + d] * 6 + [d] * 2):
            rows.append({"t": d * 86400 + k, "outcome": win, "bars_held": 0,
                         "c_x": x})
    sp = backtest._quintile_spread(rows, "c_x")
    assert sp["n_per_side"] == 100 and sp["spread"] == 0
    assert sp["se_dk"] == pytest.approx(0, abs=1e-9)
    assert sp["se"] == pytest.approx(math.sqrt(2 * 0.4 * 0.6 / 100), abs=1e-4)


def _attention_rows(buckets: list[tuple[float, list[list[str]]]],
                    every: int = 10, held: int = 0) -> list[dict]:
    """Compared rows for the attention test: per bucket, an attention z and
    its outcomes grouped by entry date (one inner list a day, the days
    ``every`` calendar days apart). ``held`` 0 makes the Bartlett lag 0."""
    out = []
    for z, days in buckets:
        for d, day in enumerate(days):
            for k, o in enumerate(day):
                out.append({"symbol": f"S{k}", "t": d * every * 86400 + 60 * k,
                            "outcome": o, "predicted": 0.4, "bars_held": held,
                            "attention": z})
    return out


def _singly(wins: int, n: int = 400) -> list[list[str]]:
    """n setups each on its own date, the first ``wins`` of them wins."""
    return [["TARGET" if i < wins else "STOP"] for i in range(n)]


def test_attention_buckets_are_read_against_the_run_not_the_prediction():
    """P1-E. A run whose every setup beats the prediction by the same amount
    has buckets that each beat it too; that says nothing about attention.
    Each bucket is compared with the run's own gap. Here attention is noise
    and the setups that have it sit 15 points above the prediction. "The
    run" is the setups that carry attention (code review r5 P2-1): the
    setups without an attention series, here on the prediction, do not move
    the reference.
    Mutation it catches: buckets compared with the prediction again, or the
    run's gap taken over every compared setup, attention or not."""
    import random
    rng = random.Random(5)
    levels = (-1.0, 0.5, 1.5, 3.0)
    trials = [{"symbol": "S", "t": (i % 400) * 86400, "predicted": 0.4,
               "bars_held": 3, "attention": levels[i % 4],
               "outcome": "TARGET" if rng.random() < 0.55 else "STOP"}
              for i in range(2000)]
    # and setups with no attention series, on the prediction: they are not
    # part of the reference the buckets are read against
    trials += [{"symbol": "N", "t": i * 86400, "predicted": 0.4, "bars_held": 3,
                "attention": None, "outcome": "TARGET" if i % 5 < 2 else "STOP"}
               for i in range(400)]
    covered = [t for t in trials if t["attention"] is not None]
    run_gap = sum((t["outcome"] == "TARGET") - 0.4 for t in covered) / 2000
    whole = sum((t["outcome"] == "TARGET") - 0.4 for t in trials) / 2400
    assert run_gap - whole > 0.02                  # the two references differ
    buckets = backtest._attention_buckets(trials)
    assert [b["name"] for b in buckets] == ["below normal", "normal",
                                            "elevated", "spike"]
    for b in buckets:
        assert b["delta"] > 0.1                        # each beats the prediction
        assert b["vs_run"] == pytest.approx(b["delta"] - run_gap, abs=1e-4)
        assert abs(b["vs_run"]) < 0.06
        assert b["significant"] is False, b
    assert backtest._news_verdict(buckets).startswith(
        "No attention level stood apart from the run as a whole")


def test_partial_attention_coverage_does_not_shift_every_bucket():
    """Code review r5 P2-1, the reviewer's case. 25 of 129 instruments carry
    attention, as in production; they sit 3 points above the prediction and
    the other 104 on it; attention is pure noise and the setups are
    independent. Read against the whole run, every bucket was about 2.4
    points 'above' it and two to four survived BH on each of 20 seeds. Read
    against the setups that carry attention, none stood apart on any.
    Mutation it catches: the run's gap taken over every compared setup."""
    import random
    from sonar.research import stats
    rng = random.Random(11)
    levels = (-1.0, 0.5, 1.5, 3.0)
    trials = []
    for k in range(129):
        covered = k < 25
        for d in range(600):
            trials.append({
                "symbol": f"S{k}", "t": d * 86400 + k, "predicted": 0.4,
                "bars_held": 0,
                "attention": rng.choice(levels) if covered else None,
                "outcome": ("TARGET" if rng.random() < (0.43 if covered
                                                         else 0.40) else "STOP")})
    buckets = backtest._attention_buckets(trials)
    assert len(buckets) == 4
    # the fixture carries the bias: against the whole run, three of the four
    # buckets survive the same BH
    whole = sum((t["outcome"] == "TARGET") - 0.4 for t in trials) / len(trials)
    assert sum(stats.benjamini_hochberg(
        [stats.normal_p((b["delta"] - whole) / b["std_error"]) for b in buckets],
        q=backtest.ATTENTION_FDR_Q)) == 3
    assert not any(b["significant"] for b in buckets), buckets
    assert all(abs(b["vs_run"]) < 2 * b["std_error"] for b in buckets)
    assert backtest._news_verdict(buckets).startswith(
        "No attention level stood apart")


def test_one_attention_bucket_must_survive_the_four_tested_together():
    """P1-E. Four attention levels are four chances to be fooled, so they go
    through Benjamini–Hochberg at q = 0.05 together. The spike bucket here
    is 2.40 standard errors from the run (p = 0.016): beyond two standard
    errors alone, not beyond what four tries allow (0.05/4). At 3.0 (p =
    0.003) it survives, and the sentence names it against the run.
    Mutation it catches: BH dropped, run at q = 0.10, or the ranks
    mis-thresholded."""
    def buckets(spike_wins: int) -> list[dict]:
        return backtest._attention_buckets(_attention_rows(
            [(-1.0, _singly(160)), (0.5, _singly(160)), (1.5, _singly(160)),
             (3.0, _singly(spike_wins))]))
    near = buckets(192)
    spike = near[-1]
    assert spike["name"] == "spike"
    # the fixture is where it says: 0.75 × 8 points over a binomial bar
    assert spike["std_error"] == pytest.approx(math.sqrt(0.48 * 0.52 / 400),
                                               abs=5e-5)
    z = spike["vs_run"] / spike["std_error"]
    assert 2.24 < z < 2.50, z
    assert spike["p"] == pytest.approx(0.0163, abs=0.001)
    assert not any(b["significant"] for b in near)
    assert backtest._news_verdict(near).startswith(
        "No attention level stood apart from the run as a whole")

    clear = buckets(200)
    assert clear[-1]["vs_run"] / clear[-1]["std_error"] > 2.9
    assert [b["significant"] for b in clear] == [False, False, False, True]
    v = backtest._news_verdict(clear)
    assert v.startswith("A news spike shifts the odds: spike +7.5 pts against "
                        "the run as a whole (n=400)"), v


def test_an_attention_bucket_counts_same_day_setups_once():
    """P1-E. The spike bucket's 400 setups are 40 days of 10 that win or lose
    together: 55% against a run 3.75 points above a 40% prediction. Counted
    as 400 independent setups it is 4.5 binomial errors from the run; counted
    by day it is 1.4, so it is not significant.
    Mutation it catches: the bucket's bar left binomial."""
    spike = [["TARGET" if d % 20 < 11 else "STOP"] * 10 for d in range(40)]
    rows = _attention_rows([(-1.0, _singly(160)), (0.5, _singly(160)),
                            (1.5, _singly(160)), (3.0, spike)], held=3)
    b = backtest._attention_buckets(rows)[-1]
    assert b["hit_rate"] == pytest.approx(0.55)
    binomial = math.sqrt(0.55 * 0.45 / 400)
    assert b["vs_run"] / binomial > 4.4
    dk = math.sqrt(22 * 4.5 ** 2 + 18 * 5.5 ** 2) / 400
    assert b["se_dk"] == pytest.approx(dk, abs=5e-5)
    assert b["std_error"] == b["se_dk"]
    assert b["significant"] is False
    # Entered on consecutive days, the bucket's bar also runs on over one
    # average hold, as the headline's does (5 days at 3 bars).
    close = _attention_rows([(-1.0, _singly(160)), (0.5, _singly(160)),
                             (1.5, _singly(160)), (3.0, spike)], every=1, held=3)
    sel = [t for t in close if t["attention"] == 3.0]
    b = backtest._attention_buckets(close)[-1]
    assert b["se_dk"] == pytest.approx(backtest._dk_se(sel, 5), abs=5e-5)
    assert backtest._dk_se(sel, 5) > backtest._dk_se(sel, 0) + 0.005


def test_the_news_verdict_says_how_the_buckets_were_judged():
    """The sentences match the test: against the run as a whole, with the
    four levels judged together, and with same-day setups counted together.
    Neither promises anything (T11-8's guard). The null sentence is the
    owner's round-5 wording in full: no effect detected is not none (QA r6
    T2)."""
    none = backtest._news_verdict([{"name": "spike", "delta": 0.1, "vs_run": 0.0,
                                    "n": 50, "significant": False}])
    some = backtest._news_verdict([{"name": "elevated", "delta": 0.1,
                                    "vs_run": -0.052, "n": 80,
                                    "significant": True}])
    assert none == ("No attention level stood apart from the run as a whole "
                    "(the setups with an attention reading), with setups "
                    "entered on the same day counted together and the levels "
                    "judged together: no effect of a news spike was detected, "
                    "which is not the same as none."), none
    assert some.startswith("Some attention levels shift the odds: elevated "
                           "-5.2 pts against the run as a whole (n=80)"), some
    for text in (none, some):
        low = text.lower()
        for banned in ("edge", "profit", "money", "guarantee", "certain",
                       "two standard errors"):
            assert banned not in low, (banned, text)


def _blend_trials(n: int, seed: int, backwards: bool) -> list[dict]:
    """Setups where the blended score genuinely ranks backwards (``True``:
    high momentum and volatility lose), or is noise."""
    import random
    rng = random.Random(seed)
    out = []
    for i in range(n):
        m, v = rng.random(), rng.random()
        p = 0.75 - 0.5 * (0.3 * m + 0.15 * v) / 0.45 if backwards else 0.4
        out.append({"outcome": "TARGET" if rng.random() < p else "STOP",
                    "predicted": 0.4, "bars_held": 5, "momentum": m, "vol": v,
                    "t": i * 86400, "c_momentum": m, "c_volatility": v,
                    "c_news": None, "c_catalyst": None})
    return out


def test_the_blend_ranks_backwards_only_when_judged_and_significant():
    """Code review r4 P2-1. 'The score as a whole is ranking the wrong way
    round' is a finding: it needs the blend's IC significant, by the same
    test the components get, at Z_CLAIM, and a run that gets a
    verdict. A negative blend in noise, or on a withheld run, is a number.
    Mutation it catches: the sign alone deciding, the significance test
    dropped, or the withheld gate dropped."""
    from sonar import calibration
    from sonar.research import stats
    strong = backtest.attribute(_blend_trials(1500, 1, backwards=True))
    assert strong["blend_ic"] < 0
    assert strong["blend_ic_t"] <= -calibration.Z_CLAIM
    assert strong["blend_ranks_backwards"] is True
    withheld = backtest.attribute(_blend_trials(1500, 1, backwards=True),
                                  withheld="span")
    assert withheld["blend_ic"] == strong["blend_ic"]
    assert withheld["blend_ranks_backwards"] is False
    # noise past two standard errors, inside the claim bar (t −2.56)
    noise = backtest.attribute(_blend_trials(1500, 43, backwards=False))
    assert noise["blend_ic"] < 0, noise["blend_ic"]
    assert -calibration.Z_CLAIM < noise["blend_ic_t"] < -2
    assert noise["blend_ranks_backwards"] is False
    # the t is the components' test, on the blend: the mean centred product
    # over the wider of Newey-West and the date-clustered bar (loop 5), at
    # the lag of one average hold (5 bars: 8 days)
    rows = _blend_trials(1500, 43, backwards=False)
    xs = [(0.3 * t["c_momentum"] + 0.15 * t["c_volatility"]) / 0.45 for t in rows]
    ys = [1.0 if t["outcome"] == "TARGET" else 0.0 for t in rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    prods = [(x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)]
    _t, se_nw = stats.newey_west_t(prods)
    se = max(se_nw, backtest._dk_mean_se(prods, [t["t"] for t in rows], 8))
    assert noise["blend_ic_t"] == pytest.approx(
        sum(prods) / len(prods) / se, abs=0.01)
    assert backtest._dk_lag_of(rows) == 8
