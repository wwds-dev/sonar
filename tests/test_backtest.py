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

from sonar import backtest, randomisation, scoring


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


def _paired(trials: list[dict]) -> list[dict]:
    """Hand-built trials with the opposite direction's outcome, as run_symbol
    gives every row: the mirror of each (a win the other way is a loss), at
    the same prediction. A run over a stated universe is judged only with
    them (docs/adr/0003); a hand-built one without a universe needs none."""
    flip = {"TARGET": "STOP", "STOP": "TARGET", "TIMEOUT": "TIMEOUT"}
    return [dict(t, opp_outcome=flip[t["outcome"]],
                 opp_bars_held=t.get("bars_held"),
                 opp_predicted=(None if t["outcome"] == "TIMEOUT"
                                else t.get("predicted")))
            for t in trials]


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


def test_summary_calls_a_matching_rate_not_shown_to_differ():
    """A gap inside its bar is not shown, which is not the same as shown to
    be absent: the sentence says so and never 'no edge' (measure 9)."""
    trials = [{"outcome": "TARGET" if i < 400 else "STOP", "predicted": 0.4,
               "bars_held": 3, "momentum": 0.03, "rr": 1.5} for i in range(1000)]
    s = backtest.summarise(_dated(trials))
    assert s["significant"] is False and s["withheld"] is None
    assert s["verdict_state"] == "within" and s["outside_bar"] is False
    assert ("not shown to differ from the prediction, which is not the same "
            "as no difference") in s["verdict"]
    assert "no edge" not in s["verdict"].lower()


def test_summary_flags_a_harmful_signal():
    trials = [{"outcome": "TARGET" if i < 100 else "STOP", "predicted": 0.4,
               "bars_held": 3, "momentum": 0.03, "rr": 1.5} for i in range(1000)]
    s = backtest.summarise(_dated(trials))
    assert s["significant"] is True
    # QA-13 copy: says what happened on these setups, not "lost money".
    assert "lost money" not in s["verdict"]
    # Under the gate "below" is a one-sided 2.5% reading, as "beats" is, so
    # it reads the same way (code review P2-2): the reading, then the
    # measured chance rate — and no longer "does not show … a coin flip".
    assert ("further below it than directions picked at random"
            in s["verdict"]), s["verdict"]
    assert backtest.CHANCE_VERDICT_RATE in s["verdict"]
    assert "coin flip" not in s["verdict"]
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
    Mutation it catches: the floor removed (the floored run would compare
    the 120 jumps). 120 instruments entering on 120 different days three
    days apart, so the unfloored run clears the minimum sample for a verdict
    (P1-B) and falls in a dozen stretches. Since the direction
    randomisation (docs/adr/0003) the unfloored run lands outside its bar
    and still gets no verdict: the jump favours whichever direction it
    happens to go, so the opposite directions land as far above the
    prediction, and the run is not told apart from chance — the second
    defence against the same false positive."""
    walks = {f"J{i}": _wobble_then_a_jump(10, up=i % 2 == 0, day=3 * i)
             for i in range(120)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])

    with monkeypatch.context() as m:
        m.setattr(backtest, "MIN_WINDOW_HORIZONS", 0.0)
        unfloored = backtest.run(list(walks), horizon_days=5, step=20)
    assert unfloored["n"] == 120 and unfloored["hit_rate"] == pytest.approx(0.5)
    assert unfloored["predicted"] < 0.2
    assert unfloored["withheld"] is None and unfloored["delta"] > 0.3
    assert unfloored["outside_bar"] is True
    assert unfloored["verdict_state"] == "unconfirmed"
    assert not unfloored["significant"]
    assert "not told apart from chance" in unfloored["verdict"]
    assert "beats" not in unfloored["verdict"]

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
    """T11-8's copy guard, for the backtest (QA P3-6). Every verdict state,
    either sign, small and large: no edge, no profit, no money, no
    certainty, no luck. A reader without finance training takes these
    sentences at face value. 'not a guarantee' is a denial; a bare
    'guarantee' still fails. None counts standard errors (the bar is not a
    calibrated 2-se test, validator r5 P2-A), none says 'confirmed' or
    'verified' (measure 11), and every one says it is before costs and from
    one replay of past prices (Design)."""
    allowed = ("not a guarantee",)
    cases = {
        "within": [(0.004, 0.005, "within"), (-0.009, 0.005, "within")],
        "beats": [(0.031, 0.01, "beats"), (0.25, 0.002, "beats")],
        "below": [(-0.031, 0.01, "below"), (-0.30, 0.002, "below")],
        "not told apart from chance": [(0.031, 0.01, "unconfirmed"),
                                       (-0.031, 0.01, "unconfirmed")],
    }
    for marker, args in cases.items():
        for delta, se, state in args:
            verdict = backtest._verdict(delta, se, state)
            assert marker in verdict, (marker, verdict)
            low = verdict.lower()
            assert "before costs" in low and "one replay of past prices" in low
            for phrase in allowed:
                low = low.replace(phrase, "")
            for banned in ("edge", "profit", "money", "whale", "guarantee",
                           "certain", "doing something", "standard error",
                           "confirmed", "verified", "luck"):
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


def _seventy_at_random(n: int, seed: int = 1) -> list[dict]:
    """As _seventy_in_a_hundred, but each setup a win with chance 0.7 on its
    own. The randomisation's t is clustered by stretch, and stretches with
    exactly the same mix of wins leave it no spread between stretches to
    read (V = 0, so t = 0: fail closed); real samples always have one."""
    import random
    rng = random.Random(seed)
    return [{"outcome": "TARGET" if rng.random() < 0.7 else "STOP",
             "predicted": 0.4, "bars_held": 3, "momentum": 0.03, "rr": 1.5,
             "symbol": "S"} for _ in range(n)]


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
    at 125. The walks are 7,000 bars so the 120-day entries span the five
    horizons (870 days) a verdict also needs (loop 3), and fall in at least
    eight stretches of 696 days (docs/adr/0003).
    Mutation it catches: run() not passing the horizon on."""
    walks = {f"D{i}": synthetic(0.004, n=7000, seed=7 + i) for i in range(2)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    at = backtest.run(list(walks), horizon_days=120, step=3)
    assert at["n"] >= backtest.MIN_VERDICT_TRIALS
    assert at["randomisation"]["q"] >= backtest.MIN_VERDICT_CLUSTERS
    assert at["significant"] and at["delta"] > 0 and at["withheld"] is None
    assert at["verdict_state"] == "beats"
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
    """T11-8's copy guard over the withheld verdicts."""
    texts = [backtest._withheld_verdict("horizon", 250, 1234, 300),
             backtest._withheld_verdict("too_few", 120, 15, 9),
             backtest._withheld_verdict("few_clusters", 20, 4000, 300,
                                        clusters=5)]
    for verdict in texts:
        low = verdict.lower()
        for banned in ("edge", "profit", "money", "whale", "guarantee",
                       "certain", "doing something", "beats", "below"):
            assert banned not in low, (banned, verdict)
    assert "250-day horizon" in texts[0]
    assert "15 compared setups from 9 entry dates" in texts[1]


def test_a_positive_verdict_has_one_sign_in_words():
    """'beats … by +3.1 points' says the sign twice (QA r2 P3)."""
    v = backtest._verdict(0.031, 0.01, "beats")
    assert "beats the prediction by 3.1 points" in v and "+" not in v
    u = backtest._verdict(-0.031, 0.01, "unconfirmed")
    assert "3.1 points under the prediction" in u and "-" not in u


# What beats and below say of the chance rate (owner, after validator r7).
_CAVEAT = (
    "That is not a guarantee: in our tests, directions picked at random and "
    "held for up to eight holding periods still got a verdict either way "
    "about 1 run in 10, and about 1 in 5 at some settings. That rate is per "
    "run, so trying many settings makes a chance verdict likely, and nearby "
    "settings can disagree. A direction fixed per instrument, such as "
    "always long, can also land outside the bar, because the list holds "
    "today's survivors; this check cannot see that.")


def test_the_verdicts_name_the_error_bar_and_what_it_misses():
    """Measure 9: every sentence restates the rule — outside the error bar
    *and* further out than directions picked at random over stretches of
    time. 'beats' and 'below' read the same way (code review P2-2) and
    quote the measured chance rate of any verdict (validator r7: 9.11%,
    'about 1 run in 10', the worst setting band about 1 in 5), per run,
    with its scope of up to eight holding periods, never a pre-filled
    '1 in 20'. 'within' is not 'no edge'. Outside the bar without the
    randomisation is 'not told apart from chance', never 'within'. Every
    sentence that reads outside the bar names the residual a direction
    fixed per instrument leaves (owner, after validator r7 P1-2), in words
    that fit a 'below' reading too and are not a tip (code review P3-3,
    domain P3-1).
    Mutation it catches: the old copy back, the bar left out, the scope
    back at four holding periods, or the residual dropped."""
    assert backtest.CHANCE_VERDICT_RATE == "about 1 run in 10"
    assert backtest.CHANCE_VERDICT_RATE_WORST == "about 1 in 5"
    assert backtest._verdict(0.031, 0.009, "beats") == (
        "Hit rate beats the prediction by 3.1 points, outside its error bar "
        "(±1.8), and further above it than directions picked at random over "
        "stretches of time across the watchlist usually land. " + _CAVEAT +
        " Before costs, from one replay of past prices: a reason to look "
        "closer, not a finding.")
    assert backtest._verdict(-0.031, 0.009, "below") == (
        "Hit rate is 3.1 points below the prediction, outside its error bar "
        "(±1.8), and further below it than directions picked at random over "
        "stretches of time across the watchlist usually land. " + _CAVEAT +
        " Before costs, from one replay of past prices: a reason to look "
        "closer, not a finding.")
    assert backtest._verdict(0.011, 0.009, "within") == (
        "Before costs, the realised hit rate is within 1.8 points of the "
        "barrier model's prediction: not shown to differ from the "
        "prediction, which is not the same as no difference. From one "
        "replay of past prices.")
    assert backtest._verdict(0.031, 0.009, "unconfirmed") == (
        "Before costs, 3.1 points above the prediction, outside its error "
        "bar (±1.8), but directions picked at random over stretches of time "
        "across the watchlist land this far out often enough that this is "
        "not told apart from chance. A direction fixed per instrument, such "
        "as always long, can also land outside the bar, because the list "
        "holds today's survivors; this check cannot see that. From one "
        "replay of past prices.")
    assert "can read above the prediction" in backtest._withheld_verdict(
        "horizon", 250, 1234, 300)


def test_too_few_stretches_names_the_fix_the_reader_has():
    """The few_clusters sentence names the fix (domain P3-5): the Lab's
    reader picks a range and a horizon, the Terminal's only a profile. The
    Lab's longer range stops at five years, which ten-year runs are not
    judged past (owner, Lab 10y). Both say the numbers are before costs,
    from one replay of past prices (QA P3-5). A sample that cannot be
    swapped whole says that instead, and never blames the range or the
    horizon (code review P3-3).
    Mutation it catches: the Terminal told to pick a longer range, the Lab
    pointed at ten years, or the unpaired run given the few-stretches
    advice."""
    lab = backtest.few_clusters_verdict(3, 60)
    term = backtest.few_clusters_verdict(3, 60, terminal=True)
    assert lab == backtest._withheld_verdict("few_clusters", 60, 4000, 300,
                                             clusters=3)
    assert "3 stretches of 348 days" in lab and "3 stretches of 348" in term
    assert ("A shorter horizon gives more, or a longer range up to five "
            "years.") in lab
    assert "A longer range or" not in lab
    assert "A shorter profile gives more." in term
    assert "range" not in term
    for v in (lab, term):
        assert "before costs, from one replay of past prices" in v
    unpaired = backtest._withheld_verdict("unpaired", 5, 4000, 300)
    assert "opposite direction" in unpaired
    for word in ("range", "horizon gives", "stretches of", "longer"):
        assert word not in unpaired, word
    assert "before costs, from one replay of past prices" in unpaired


@pytest.mark.release
def test_no_verdict_ships_with_an_unfilled_figure():
    """Release gate (code review P2-1, domain P1-1): the chance rate the
    beats and below sentences quote is the validator's measured figure,
    never a placeholder. Deselected by default; sre-release runs
    `pytest -m release` (TESTING.md), and a "{" or "}" left in the figure or
    in any judged sentence blocks the release.
    Mutation it catches: a placeholder such as "{measured}" put back."""
    for figure in (backtest.CHANCE_VERDICT_RATE,
                   backtest.CHANCE_VERDICT_RATE_WORST,
                   backtest.FIXED_PER_INSTRUMENT):
        assert "{" not in figure and "}" not in figure, figure
    for state, delta in (("beats", 0.031), ("below", -0.031),
                         ("unconfirmed", 0.031), ("within", 0.011)):
        v = backtest._verdict(delta, 0.009, state)
        assert "{" not in v and "}" not in v, (state, v)


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


def _weekday_walk(years: int, end=(2026, 10, 9)) -> backtest.Bars:
    """A driftless walk on a weekday calendar of ``years`` years of bars
    ending on a fixed Friday, 21:00 UTC: the calendar Yahoo's range gives
    an equity."""
    import datetime as dt
    import random
    rng = random.Random(years)
    last = dt.date(*end)
    d, times = last.replace(year=last.year - years), []
    while d <= last:
        if d.weekday() < 5:
            times.append(int(dt.datetime(d.year, d.month, d.day, 21,
                                         tzinfo=dt.timezone.utc).timestamp()))
        d += dt.timedelta(days=1)
    bars, p = backtest.Bars(symbol="WK"), 100.0
    for t in times:
        o = hi = lo = p
        for _ in range(4):
            p *= math.exp(rng.gauss(0, 0.005))
            hi, lo = max(hi, p), min(lo, p)
        bars.time.append(t)
        bars.open.append(o)
        bars.high.append(hi)
        bars.low.append(lo)
        bars.close.append(p)
    return bars


def _stretches(bars: backtest.Bars, h: int) -> int:
    """How many stretches the compared setups of one replay fall in, as the
    direction randomisation counts them."""
    rows = [t for t in backtest.run_symbol(bars, h, step=3, keep_timeouts=True)
            if not t["short_window"]]
    clusters, _lines = backtest._direction_clusters(
        rows, backtest.randomisation_block_days(h))
    return len(clusters)


def test_the_terminal_range_gives_its_horizon_enough_stretches():
    """[A15], as amended by the owner after validator r7 (2026-10-12): the
    Terminal reads the shorter of two and five years whose setups fall in
    the eight stretches a verdict needs — two years to 10 days, five to 30
    — and never ten years, where a direction fixed per instrument read
    "beats" (validator r7 P1-2). Checked on a weekday calendar: each rule
    edge gives at least 8, and two years gives fewer at the 20-day profile,
    which it left always withheld. Past 30 days the range is the one that
    compares anything (code-review r2 P2-1: the 250-day profile on two
    years compared nothing, so past ~156 days it reads five years), and the
    60-day profile falls in under 8 stretches there: numbers, no verdict.
    Mutation it catches: the rule dropped, an edge moved, or ten years back."""
    from sonar import horizon
    assert backtest.range_for_horizon(1) == "2y"
    assert backtest.range_for_horizon(10) == "2y"
    assert backtest.range_for_horizon(11) == "5y"
    assert backtest.range_for_horizon(30) == "5y"
    assert backtest.range_for_horizon(31) == "2y"
    assert backtest.range_for_horizon(80) == "2y"
    assert backtest.range_for_horizon(156) == "2y"
    assert backtest.range_for_horizon(157) == "5y"
    assert backtest.range_for_horizon(horizon.YEAR.momentum_days) == "5y"
    assert all(backtest.range_for_horizon(h) in ("2y", "5y")
               for h in range(1, 300))
    years = {"2y": 2, "5y": 5}
    walks = {n: _weekday_walk(n) for n in (2, 5)}
    for h in (1, 10, 30):
        assert _stretches(walks[years[backtest.range_for_horizon(h)]], h) \
            >= backtest.MIN_VERDICT_CLUSTERS, h
    for hz, rng, shorter in ((horizon.INTRADAY, "2y", None),
                             (horizon.WEEK, "2y", None),
                             (horizon.MONTH, "5y", 2)):
        h = hz.momentum_days
        assert backtest.range_for_horizon(h) == rng, hz.name
        assert _stretches(walks[years[rng]], h) >= 8, hz.name
        if shorter:
            assert _stretches(walks[shorter], h) < 8, hz.name
    quarter = horizon.QUARTER.momentum_days
    assert backtest.range_for_horizon(quarter) == "2y"
    assert _stretches(walks[2], quarter) < backtest.MIN_VERDICT_CLUSTERS


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
    trials = _paired(_dated(_seventy_in_a_hundred(1000)))
    whole = backtest.summarise(trials, horizon_days=5, universe="all",
                               timeouts=[])
    equity = backtest.summarise(trials, horizon_days=5, universe="Equity",
                                timeouts=[])
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


def test_a_ten_year_run_shows_its_numbers_without_a_verdict(monkeypatch):
    """Owner, Lab 10y (domain pass 4 P2-1): the range reaches summarise, and
    a run over ten years is withheld 'drift' — over ten years of today's
    list a direction fixed per instrument lands outside the bar far more
    often than the rate a verdict quotes (validator r7 P1-2), so the run
    is not judged. The numbers stay; no component is graded, and the
    attention buckets read as numbers only, as on every withheld run. Five
    years of the same bars is judged. The sentence says why in plain words,
    before costs, from one replay of past prices, and gives no tip.
    Mutation it catches: run() not passing the range on, the rule dropped,
    or ten years graded in attribution."""
    walks = {f"D{i}": synthetic(0.004, n=900, seed=7 + i) for i in range(2)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    assert backtest.NO_VERDICT_RANGES == ("10y",)
    five = backtest.run(list(walks), horizon_days=20, step=3, rng="5y")
    assert five["significant"] and five["withheld"] is None
    assert any(c["verdict"] != "not judged"
               for c in five["attribution"]["components"]
               if c.get("ic") is not None)
    ten = backtest.run(list(walks), horizon_days=20, step=3, rng="10y")
    assert ten["range"] == "10y"
    assert ten["n"] == five["n"] and ten["delta"] == five["delta"]
    assert ten["withheld"] == "drift" and ten["verdict_state"] == "withheld"
    assert ten["significant"] is False and ten["outside_bar"] is False
    assert ten["randomisation"]["p_tail"] is None
    assert ten["attribution"]["withheld"] == "drift"
    measured = [c for c in ten["attribution"]["components"]
                if c.get("ic") is not None]
    assert measured and all(c["verdict"] == "not judged" and
                            c["why"] == backtest.NOT_JUDGED for c in measured)
    assert ten["attribution"]["blend_ranks_backwards"] is False
    assert ten["verdict"] == (
        "No verdict on ten years. Over ten years of today's list, a direction "
        "fixed per instrument, such as always long, lands outside the bar far "
        "more often than the chance rate a verdict quotes (about 1 run in "
        "10), because the list holds only today's survivors: instruments "
        "that fell away are missing. So ten-year runs are not judged; five "
        "years or less can be. The numbers are shown without a verdict, "
        "before costs, from one replay of past prices.")
    # the horizon still comes first, and a hand-built sample without a
    # range is not held to the rule [A11]
    assert backtest.summarise([], rng="10y")["n"] == 0
    rows = _rigged_rows(400)
    assert backtest.summarise(rows, horizon_days=150, rng="10y",
                              universe="all", timeouts=[])[
        "withheld"] == "horizon"
    assert backtest.summarise(rows)["withheld"] is None


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
    horizon, then single class, then too few, then span, then a sample that
    cannot be swapped whole (its timeouts not passed), then too few
    stretches. The two a reader can change by picking another setting come
    before those that depend on the sample. Each step below lifts one reason
    and the next shows.
    Mutation it catches: any two of the six checks swapped (QA r3 G2)."""
    few_close = _paired(_span_of(_seventy_in_a_hundred(99), 19))
    many_close = _paired(_span_of(_seventy_in_a_hundred(1000), 19))
    many_wide = _paired(_spread(_seventy_in_a_hundred(1000), dates=20, every=50))
    # 20 dates 400 days apart: eleven 696-day stretches
    wider = _paired([dict(t, t=(i // 50) * 400 * 86400)
                     for i, t in enumerate(_seventy_at_random(1000))])
    # None: the timeouts not passed, so the sample cannot be swapped whole
    steps = [
        (few_close, 121, "Equity", None, "horizon"),
        (few_close, 120, "Equity", None, "single_class"),
        (few_close, 120, "all", None, "too_few"),
        (many_close, 120, "all", None, "span"),
        (many_wide, 120, "all", None, "unpaired"),
        (many_wide, 120, "all", [], "few_clusters"),
        (wider, 120, "all", [], None),
    ]
    for trials, h, universe, timeouts, why in steps:
        s = backtest.summarise(trials, horizon_days=h, universe=universe,
                               timeouts=timeouts)
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


def _rigged_rows(n: int, dates: int = 100, seed: int = 1,
                 every: int = 3) -> list[dict]:
    """Compared rows as run_symbol returns them, in which momentum and an
    attention spike both genuinely sort winners from losers — so, judged,
    the attention test reports a finding and attribution keeps momentum.
    Entered on ``dates`` days ``every`` calendar days apart: 100 dates three
    days apart fall in ten 32-day stretches at h = 5. Each row carries its
    opposite outcome, the mirror of its own (docs/adr/0003)."""
    import random
    rng = random.Random(seed)
    out = []
    for i in range(n):
        m = rng.random()
        spike = i % 2 == 0
        att = 3.0 if spike else -1.0
        p = 0.1 + 0.5 * m + (0.25 if spike else 0.0)
        out.append({"symbol": "AAPL", "t": (i % dates) * every * 86400,
                    "direction": "LONG", "momentum": 0.2 * m, "vol": 0.01,
                    "outcome": "TARGET" if rng.random() < p else "STOP",
                    "bars_held": 3, "predicted": 0.4, "rr": 1.5,
                    "k_target": 1.5, "k_stop": 1.0, "window": 20,
                    "horizons": 4.0, "truncated": False, "short_window": False,
                    "attention": att, "c_momentum": m, "c_volatility": 0.3,
                    "c_news": max(0.0, min(1.0, (att + 1.0) / 4.0)),
                    "c_catalyst": None})
    return _paired(out)


def _rigged_run(monkeypatch, rows, **kw) -> dict:
    monkeypatch.setattr(backtest, "fetch_bars",
                        lambda sym, rng: synthetic(0.0, n=60))
    monkeypatch.setattr(backtest, "run_symbol", lambda *a, **k: list(rows))
    return backtest.run(["AAPL"], step=3, **kw)


_JUDGED = {"KEEP", "DROP", "INVERTED", "WEAK", "UNCLEAR", "UNCONFIRMED",
           "UNTESTED"}


def test_a_run_without_a_verdict_claims_no_attention_or_attribution_finding(
        monkeypatch):
    """P2-1 (code-review r3) and P2-F (model-validator r3). A run shown
    without a verdict still printed 'A news spike shifts the odds … beyond
    two standard errors' and attribution KEEP/DROP/INVERTED on the same page.
    Now, whatever the reason — a 121-day horizon, one class, 99 setups, a
    short span, too few stretches, ten years — every attention bucket is not
    significant, the attention
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
                          "points — before costs, from one replay of past "
                          "prices"), mom
    inv = backtest._verdict_for(dict(mom, ic=-mom["ic"],
                                     spread=dict(mom["spread"], spread=-spread)))
    assert inv == {"verdict": "INVERTED", "why": (
        f"IC {-mom['ic']:+.3f} is significant and *negative* — the top "
        f"quintile trails the bottom by {spread * 100:.1f} points. Added with "
        "a positive weight, this component would push the wrong instruments "
        "up the board. Worth testing with its sign flipped, or dropped. "
        "Before costs, from one replay of past prices: a reason to look "
        "closer, not a finding.")}, inv
    for why in (mom["why"], inv["why"]):
        for banned in ("edge", "profit", "money", "guarantee", "certain",
                       "flip its sign or drop"):
            assert banned not in why.lower(), (banned, why)
    cases = {
        "horizon": (_rigged_rows(1000, dates=1000), {"horizon_days": 121}),
        "single_class": (_rigged_rows(1000),
                         {"horizon_days": 5, "universe": "Equity"}),
        "too_few": (_rigged_rows(99), {"horizon_days": 5}),
        "span": (_rigged_rows(1000, dates=30, every=1), {"horizon_days": 5}),
        "few_clusters": (_rigged_rows(1000, dates=100, every=1),
                         {"horizon_days": 5}),
        "drift": (_rigged_rows(1000), {"horizon_days": 5, "rng": "10y"}),
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
    """attribute() with no reason to withhold, on a hand-built sample that
    opts out of the randomisation (gate=False), is graded as before."""
    rows = _rigged_rows(1000)
    assert backtest.attribute(rows, gate=False) == backtest.attribute(
        rows, withheld=None, gate=False)
    assert {c["verdict"] for c in backtest.attribute(rows, gate=False)[
        "components"] if c.get("ic") is not None} <= _JUDGED


def test_attribution_without_a_horizon_fails_closed():
    """Code review P3-5: the randomisation's exemption is explicit. A call
    without a horizon cannot build the stretches, so unless it says
    gate=False it grades nothing — withheld 'unpaired', every measured
    component 'not judged', the readings kept — rather than grading on
    today's rule alone, as it used to by default.
    Mutation it catches: the exemption keyed on the horizon again."""
    rows = _rigged_rows(1000)
    closed = backtest.attribute(rows)
    assert closed["withheld"] == "unpaired" and closed["randomisation"] is None
    assert closed["note"] == backtest.NOT_JUDGED
    open_ = backtest.attribute(rows, gate=False)
    for c, o in zip(closed["components"], open_["components"], strict=True):
        if c.get("ic") is None:
            continue
        assert c["verdict"] == "not judged" and c["ic"] == o["ic"]
    assert {c["verdict"] for c in open_["components"]
            if c.get("ic") is not None} & {"KEEP", "INVERTED"}


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
    assert a["verdict_state"] == "within"
    assert "not shown to differ from the prediction" in a["verdict"]
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


# --------------------------------------------------------------------------- #
# The direction randomisation (owner decisions at the Build gate, 2026-10-12;
# docs/adr/0003)
# --------------------------------------------------------------------------- #
def test_every_row_carries_the_opposite_directions_outcome(monkeypatch):
    """The replay contract: each row says how the opposite direction would
    have gone from the same bar, volatility and window — exactly the row a
    replay forced to that side gives, row for row — and the opposite is
    never a row of its own. A short-window row carries None and is not
    resolved the other way. At 3:1 some setups time out one way and resolve
    the other, so n changes under a swap.
    Mutation it catches: the opposite resolved with the chosen direction,
    over a different window, or from a different bar."""
    real_plan = scoring.build_plan
    walk = _driftless_walk(400, 3)
    rows = backtest.run_symbol(walk, 5, step=2, k_target=3.0, keep_timeouts=True)
    forced = {}
    for side in ("LONG", "SHORT"):
        monkeypatch.setattr(scoring, "build_plan",
                            lambda price, vol, days, _d, side=side, **kw:
                            real_plan(price, vol, days, side, **kw))
        forced[side] = backtest.run_symbol(walk, 5, step=2, k_target=3.0,
                                           keep_timeouts=True)
    monkeypatch.setattr(scoring, "build_plan", real_plan)
    assert len(rows) == len(forced["LONG"]) == len(forced["SHORT"])
    for r, lng, sht in zip(rows, forced["LONG"], forced["SHORT"], strict=True):
        same, opp = (lng, sht) if r["direction"] == "LONG" else (sht, lng)
        assert r["t"] == opp["t"] == same["t"]
        assert (r["outcome"], r["bars_held"], r["predicted"]) == (
            same["outcome"], same["bars_held"], same["predicted"])
        if r["short_window"]:
            assert (r["opp_outcome"], r["opp_bars_held"],
                    r["opp_predicted"]) == (None, None, None)
        else:
            assert (r["opp_outcome"], r["opp_bars_held"],
                    r["opp_predicted"]) == (opp["outcome"], opp["bars_held"],
                                            opp["predicted"])
    assert any(r["outcome"] == "TIMEOUT" and r["opp_outcome"] in ("TARGET", "STOP")
               for r in rows)
    assert any(r["opp_outcome"] == "TIMEOUT" and r["outcome"] != "TIMEOUT"
               for r in rows)
    # the default output carries them too, and run() hands them on
    assert all(r["opp_outcome"] for r in backtest.run_symbol(walk, 5, step=2))


def test_a_whole_run_is_swapped_from_its_own_opposite_outcomes(monkeypatch):
    """run() supplies the opposite outcomes, so a whole-watchlist run is
    held to the randomisation: it reports its stretches, method and p.
    Mutation it catches: run() dropping the opposite fields (the run would
    be withheld for no stretches)."""
    walks = {f"S{i}": _driftless_walk(600, 50 + i) for i in range(3)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    r = backtest.run(list(walks), horizon_days=5, step=3)
    rand = r["randomisation"]
    assert rand["block_days"] == 32 and rand["q"] >= 8
    assert r["withheld"] is None and rand["p_tail"] is not None
    assert rand["method"] == "monte_carlo" and rand["draws"] == 11_999
    assert r["verdict_state"] in ("within", "unconfirmed", "beats", "below")
    assert r["attribution"]["randomisation"]["block_days"] == 32


def test_the_stretches_are_four_horizons_across_every_class():
    """[A6]: a stretch is MAX_HOLD_MULTIPLE horizons of trading days in
    calendar days, across every class at once, edges at Unix day 0, by UTC
    entry date. A timeout adds nothing to its side's sums; a stretch where
    nothing resolved either way is not counted; a short window is skipped;
    sums are exact whatever the row order; a row without its opposite gives
    no stretches at all (fail closed).
    Mutation it catches: the class put back into the key, the edges moved
    to the sample, timeouts counted, or a missing pair let through."""
    assert [backtest.randomisation_block_days(h) for h in (1, 5, 15, 20, 60)] \
        == [8, 32, 88, 116, 348]
    day = 86400
    q = 0.39
    rows = [
        # stretch 0: two classes, one stretch; a timeout either way
        {"symbol": "AAPL", "t": 3 * day, "outcome": "TARGET", "predicted": q,
         "opp_outcome": "STOP", "opp_predicted": q},
        {"symbol": "BTC-USD", "t": 31 * day + 82000, "outcome": "TIMEOUT",
         "predicted": None, "opp_outcome": "TARGET", "opp_predicted": q},
        {"symbol": "GC=F", "t": 10 * day, "outcome": "STOP", "predicted": q,
         "opp_outcome": "TIMEOUT", "opp_predicted": None},
        # stretch 1 starts on day 32, the day after stretch 0's last
        {"symbol": "EURUSD=X", "t": 32 * day, "outcome": "STOP",
         "predicted": q, "opp_outcome": "STOP", "opp_predicted": q},
        # stretch 2 (day 64): nothing resolved either way, not counted, and
        # a short window that is skipped
        {"symbol": "AAPL", "t": 64 * day, "outcome": "TIMEOUT",
         "predicted": None, "opp_outcome": "TIMEOUT", "opp_predicted": None},
        {"symbol": "EURUSD=X", "t": 65 * day, "outcome": "TARGET",
         "predicted": None, "opp_outcome": None, "short_window": True},
    ]
    clusters, lines = backtest._direction_clusters(rows, 32)
    assert clusters == [((1 - q + 0 - q, 2), (0 - q + 1 - q, 2)),
                        ((-q, 1), (-q, 1))]
    assert len(lines) == 5
    assert backtest._direction_clusters(list(reversed(rows)), 32) == (
        clusters, list(reversed(lines)))
    # edges are Unix-day multiples of the stretch, not the first entry: a
    # day later, day 31's timeout and day 32's setup share stretch 1
    shifted = [dict(r, t=r["t"] + day) for r in rows]
    assert backtest._direction_clusters(shifted, 32)[0] == [
        ((1 - q - q, 2), (-q, 1)), ((-q, 1), (1 - q - q, 2))]
    # a compared row without its opposite outcome: no stretches at all
    assert backtest._direction_clusters(rows + [{"symbol": "X", "t": 0,
                                                 "outcome": "STOP",
                                                 "predicted": q}], 32) == ([], [])
    assert backtest._direction_clusters(rows, None) == ([], [])


def _in_stretches(trials: list[dict], stretches: int, per: int = 20,
                  offset: int = 0) -> list[dict]:
    """Entries on ``per`` days in each of the first ``stretches`` 32-day
    stretches (h = 5), starting ``offset`` days into each."""
    days = [k * 32 + offset + d for k in range(stretches) for d in range(per)]
    return [dict(t, t=days[i % len(days)] * 86400) for i, t in enumerate(trials)]


def test_too_few_stretches_is_withheld_and_says_how_to_get_more():
    """[A2]: under 8 stretches the run is withheld 'few_clusters', after the
    span rule, and the sentence names the fix as the span one does: a
    shorter horizon, or a longer range up to five years (owner, Lab 10y).
    7 stretches is withheld, 8 is
    judged. A hand-built sample without a universe is not held to it [A11].
    Mutation it catches: the minimum dropped, `<` turned into `<=`, or the
    hand-built exemption lost."""
    assert backtest.MIN_VERDICT_CLUSTERS == 8
    rows = _paired(_seventy_at_random(1000))
    seven = backtest.summarise(_in_stretches(rows, 7), horizon_days=5,
                               universe="all", timeouts=[])
    eight = backtest.summarise(_in_stretches(rows, 8), horizon_days=5,
                               universe="all", timeouts=[])
    assert seven["randomisation"]["q"] == 7 and eight["randomisation"]["q"] == 8
    assert seven["withheld"] == "few_clusters" and not seven["significant"]
    assert seven["verdict_state"] == "withheld"
    assert seven["randomisation"]["p_tail"] is None
    assert seven["hit_rate"] == eight["hit_rate"]                 # numbers kept
    assert eight["withheld"] is None and eight["verdict_state"] == "beats"
    assert eight["randomisation"]["method"] == "enumerate"
    assert eight["randomisation"]["draws"] == 256
    assert seven["verdict"] == (
        "Too few separate stretches of time, across asset classes, to judge: "
        "these setups fall in 7 stretches of 32 days (four holding periods "
        "each, every asset class together), and a verdict needs at least 8. "
        "A shorter horizon gives more, or a longer range up to five years. "
        "The numbers are shown without a verdict, before costs, from one "
        "replay of past prices.")
    hand = backtest.summarise(_in_stretches(rows, 7), horizon_days=5)
    assert hand["withheld"] is None and hand["randomisation"] is None
    assert hand["verdict_state"] == "beats"


def test_a_sample_that_cannot_be_swapped_whole_is_withheld_unpaired():
    """Fail closed (code review P3-3, validator r7 P2-2): a run over a
    universe needs every compared row's opposite outcome and entry time, a
    horizon, and its timeouts passed — without them a timeout that resolved
    the other way is missing from the swap, which then reads only the
    setups the run's own directions resolved. Each is withheld 'unpaired',
    with its own sentence and none of the few-stretches advice; the same
    sample with all of them is judged.
    Mutation it catches: any of the four checks dropped, or the unpaired
    run read as too few stretches."""
    rows = _in_stretches(_paired(_seventy_at_random(1000)), 8)
    judged = backtest.summarise(rows, horizon_days=5, universe="all",
                                timeouts=[])
    assert judged["withheld"] is None and judged["verdict_state"] == "beats"
    cases = {
        "timeouts not passed": dict(rows=rows, horizon_days=5),
        "no opposite outcome": dict(
            rows=[dict(t, opp_outcome=None) if i == 7 else t
                  for i, t in enumerate(rows)], horizon_days=5, timeouts=[]),
        "no entry time": dict(
            rows=[dict(t, t=None) if i == 7 else t
                  for i, t in enumerate(rows)], horizon_days=5, timeouts=[]),
        "a timeout without its opposite": dict(
            rows=rows, horizon_days=5,
            timeouts=[{"symbol": "S", "t": 0, "outcome": "TIMEOUT",
                       "predicted": None, "bars_held": 20}]),
        "no horizon": dict(rows=rows, horizon_days=None, timeouts=[]),
    }
    for name, kw in cases.items():
        s = backtest.summarise(kw.pop("rows"), universe="all", **kw)
        assert s["withheld"] == "unpaired", (name, s["withheld"])
        assert s["verdict_state"] == "withheld" and not s["significant"], name
        assert s["randomisation"]["q"] == 0, name
        assert s["verdict"] == backtest._withheld_verdict(
            "unpaired", 5, 0, 0), name
        assert "stretches of" not in s["verdict"], name
    # a hand-built sample without a universe needs none of them [A11]
    assert backtest.summarise(_in_stretches(_seventy_at_random(1000), 8),
                              horizon_days=5)["withheld"] is None


def test_the_gate_reads_the_tail_in_the_direction_of_the_gap():
    """QA P2-1 (mutant R4): Δ is above the prediction and outside its bar,
    but the opposite directions read further above it still, so almost every
    swap reads higher: p_hi 255/256, p_lo 2/256. The gate reads the tail in
    Δ's direction, p_tail = min(1, 2·p_hi) = 1, and the run is not told
    apart from chance. Reading the smaller tail instead (2·min(p_hi, p_lo)
    = 0.0156) would call it 'beats'.
    Mutation it catches: p_tail = 2·min(p_hi, p_lo)."""
    rows = []
    for i, t in enumerate(_in_stretches(_seventy_in_a_hundred(1000), 8)):
        # even stretches 90% wins, odd ones 30%; the other way 95% everywhere
        win = i % 10 < 9 if int(t["t"] // 86400) // 32 % 2 == 0 else i % 10 < 3
        rows.append(dict(t, outcome="TARGET" if win else "STOP",
                         opp_outcome="TARGET" if i % 20 < 19 else "STOP",
                         opp_predicted=0.4, opp_bars_held=3))
    s = backtest.summarise(rows, horizon_days=5, universe="all", timeouts=[])
    r = s["randomisation"]
    assert s["withheld"] is None and r["q"] == 8 and r["method"] == "enumerate"
    assert s["delta"] > 0 and s["outside_bar"] is True
    clusters, _lines = backtest._direction_clusters(rows, 32)
    full = randomisation.direction_p(clusters, r["seed"])
    assert full["p_lo"] < full["p_hi"]
    assert (full["p_hi"], full["p_lo"]) == (255 / 256, 2 / 256)
    assert r["p_tail"] == min(1.0, 2 * full["p_hi"]) == 1.0
    assert s["verdict_state"] == "unconfirmed" and s["significant"] is False


def test_outside_the_bar_but_not_told_apart_from_chance_is_its_own_state():
    """Measure 11 (P1-1). Δ outside its bar, where the opposite directions
    read the same (every swap ties, p_tail = 1): verdict_state
    'unconfirmed', not significant, a sentence that says 'not told apart
    from chance' and names the bar — never 'within', 'no edge', 'beats',
    'below' or the internal name. The mirror (the opposite directions read
    the other way, p_tail small) still reads 'beats', and 'below' for a run
    below the prediction.
    Mutation it catches: the gate removed, or the wrong tail read."""
    up = _dated(_seventy_in_a_hundred(1000))
    down = _dated([dict(t, outcome="STOP" if t["outcome"] == "TARGET"
                        else "TARGET") for t in _seventy_in_a_hundred(1000)])
    for rows, word in ((up, "beats"), (down, "below")):
        same = [dict(t, opp_outcome=t["outcome"], opp_predicted=t["predicted"],
                     opp_bars_held=t["bars_held"]) for t in rows]
        s = backtest.summarise(same, horizon_days=5, universe="all",
                               timeouts=[])
        assert s["withheld"] is None and s["outside_bar"] is True
        assert s["randomisation"]["p_tail"] == 1.0
        assert s["verdict_state"] == "unconfirmed" and s["significant"] is False
        v = s["verdict"]
        assert "not told apart from chance" in v and "outside its error bar" in v
        low = v.lower()
        for banned in ("within", "no edge", "beats", "below", "unconfirmed",
                       "confirmed", "verified"):
            assert banned not in low, (banned, v)
        mirror = backtest.summarise(_paired(rows), horizon_days=5,
                                    universe="all", timeouts=[])
        assert mirror["verdict_state"] == word and mirror["significant"]
        assert mirror["randomisation"]["p_tail"] < 0.05
        assert mirror["delta"] == s["delta"] and mirror["std_error"] == s["std_error"]


def _two_stretch_component(n_per_day: int = 20, strong: tuple = (0, 1),
                           seed: int = 2) -> list[dict]:
    """Setups over eight 32-day stretches (20 entry days each, 20 setups a
    day): the component x sorts winners from losers strongly in the
    ``strong`` stretches and not at all in the others."""
    import random
    rng = random.Random(seed)
    rows = []
    for k in range(8):
        for d in range(20):
            for j in range(n_per_day):
                x = rng.random()
                p = 0.05 + 0.9 * x if k in strong else 0.4
                rows.append({"symbol": f"S{j}", "t": (k * 32 + d) * 86400,
                             "outcome": "TARGET" if rng.random() < p else "STOP",
                             "predicted": 0.4, "bars_held": 3,
                             "c_momentum": x, "c_volatility": None,
                             "c_news": None, "c_catalyst": None})
    return rows


def test_a_component_not_told_apart_from_chance_is_not_graded():
    """Measure 11 for attribution. A component that ranks setups in two of
    eight stretches and not in the others passes today's rule (its IC
    survives FDR and its quintile spread clears its bar: KEEP on a
    hand-built sample, which is not held to the randomisation), but a sign
    change of whole stretches reads that well often enough: 'UNCONFIRMED',
    worded 'not told apart from chance', never 'survives FDR', 'confirmed'
    or 'verified'. Ranking in every stretch, it is KEEP under the gate too.
    Mutation it catches: the gate removed from the grade."""
    rows = _two_stretch_component()
    today = backtest.attribute(rows, gate=False)["components"][0]
    gated_a = backtest.attribute(rows, horizon_days=5)
    gated = gated_a["components"][0]
    assert today["component"] == gated["component"] == "momentum"
    assert today["verdict"] == "KEEP" and today["confirmed"] is True
    # the one measured component: BH at q = 0.10 asks p_rand ≤ 0.10
    assert gated["survives_fdr"] is True and gated["p_rand"] > 0.10
    assert gated["confirmed"] is False and gated["verdict"] == "UNCONFIRMED"
    assert gated_a["randomisation"] == {"q": 8, "draws": 256, "block_days": 32,
                                        "measured": 1}
    why = gated["why"]
    assert why.startswith(f"IC {gated['ic']:+.3f}: it looks like it ranks "
                          "setups on this replay, but a meaningless reading "
                          "held for stretches of time ranked them this well "
                          "often enough that this is not told apart from "
                          "chance."), why
    low = why.lower()
    for banned in ("survives fdr", "unconfirmed", "confirmed", "verified",
                   "edge", "profit", "beats", "certain"):
        assert banned not in low, (banned, why)
    assert "before costs" in low
    every = backtest.attribute(_two_stretch_component(strong=tuple(range(8))),
                               horizon_days=5)["components"][0]
    assert every["verdict"] == "KEEP" and every["confirmed"] is True
    assert every["p_rand"] <= 0.10
    assert "before costs" in every["why"]
    # the same reading the other way round is 'ranks setups backwards'
    inv = backtest._verdict_for(dict(gated, ic=-gated["ic"], spread=dict(
        gated["spread"], spread=-gated["spread"]["spread"])))
    assert inv["verdict"] == "UNCONFIRMED"
    assert "it looks like it ranks setups backwards on this replay" in inv["why"]


def test_a_component_the_randomisation_could_not_test_says_so():
    """Code review P3-4, QA P3-4: a component whose setups include one
    without an entry time cannot be put through the sign change
    (_ic_rand_p gives None). It counts as p = 1, so it is not graded — and
    its label and sentence say the check could not run, not that a
    reshuffle read it as chance: 'UNTESTED', an internal name read "not
    tested" (domain P3-2). The same component with every entry time is KEEP.
    Mutation it catches: the untested component graded, or given the
    reshuffle's label or sentence."""
    rows = _two_stretch_component(strong=tuple(range(8)))
    rows[5] = dict(rows[5], t=None)
    c = backtest.attribute(rows, horizon_days=5)["components"][0]
    assert c["p_rand"] is None and c["survives_fdr"] is True
    assert c["confirmed"] is False and c["verdict"] == "UNTESTED"
    assert c["why"] == (
        f"IC {c['ic']:+.3f}: it looks like it ranks setups on this replay, "
        "but the check against random stretches of time could not run on it "
        "(a setup without an entry time, or under two stretches), so it is "
        "not graded. Before costs, from one replay of past prices.")
    assert "meaningless reading" not in c["why"]


def test_no_keep_or_inverted_sentence_says_confirmed_or_verified():
    """Measure 11: a grade that passed the randomisation still reads as one
    replay's reading, never 'confirmed' or 'verified', and says it is before
    costs (domain P3-3).
    Mutation it catches: 'before costs' dropped from either why line."""
    keep = backtest._verdict_for({"ic": 0.05, "survives_fdr": True,
                                  "confirmed": True, "loo_cost": 0.01,
                                  "spread": {"spread": 0.06, "se": 0.01}})
    inv = backtest._verdict_for({"ic": -0.05, "survives_fdr": True,
                                 "confirmed": True, "loo_cost": 0.01,
                                 "spread": {"spread": -0.06, "se": 0.01}})
    assert keep["verdict"] == "KEEP" and inv["verdict"] == "INVERTED"
    assert "before costs, from one replay of past prices" in keep["why"]
    assert "Before costs, from one replay of past prices" in inv["why"]
    for text in (keep["why"], inv["why"], backtest._verdict(0.03, 0.01, "beats"),
                 backtest._verdict(-0.03, 0.01, "below")):
        assert "confirmed" not in text.lower() and "verified" not in text.lower()


def test_a_caller_that_opts_out_of_the_gate_grades_on_todays_rule():
    """[A11], code review P3-5, QA P3-A: attribute(rows, horizon_days=h,
    gate=False) grades on today's rule even with a horizon — the
    two-stretch component that the gate would not grade is KEEP, with no
    p_rand and no randomisation block.
    Mutation it catches (G3): the horizon alone switching the gate on."""
    a = backtest.attribute(_two_stretch_component(), horizon_days=5,
                           gate=False)
    c = a["components"][0]
    assert c["verdict"] == "KEEP" and c["confirmed"] is True
    assert c["p_rand"] is None and a["randomisation"] is None
    assert a["blend_p_rand"] is None and a["withheld"] is None


def test_ranking_backwards_needs_ten_stretches_under_the_gate():
    """[A7]: 'the score ranks backwards' also needs the blend's randomisation
    p at the claim bar (normal_p(Z_CLAIM), 0.0027). At 9 stretches the
    smallest p is 2/512 = 0.0039, so it cannot fire; at 10 it can (2/1024).
    The same strongly backwards setups, put in 9 and in 10 stretches.
    Mutation it catches: the blend's randomisation left out of the claim."""
    from sonar import calibration
    from sonar.research import stats
    assert stats.normal_p(calibration.Z_CLAIM) == pytest.approx(0.0027, abs=1e-4)
    rows = _blend_trials(1500, 1, backwards=True)
    nine = [dict(t, t=(i % 180) // 20 * 32 * 86400 + (i % 20) * 86400)
            for i, t in enumerate(rows)]
    ten = [dict(t, t=(i % 200) // 20 * 32 * 86400 + (i % 20) * 86400)
           for i, t in enumerate(rows)]
    a9 = backtest.attribute(nine, horizon_days=5)
    a10 = backtest.attribute(ten, horizon_days=5)
    assert a9["randomisation"]["q"] == 9 and a10["randomisation"]["q"] == 10
    assert a9["blend_ic_t"] <= -calibration.Z_CLAIM
    assert a9["blend_p_rand"] == pytest.approx(2 / 512, abs=1e-4)
    assert a9["blend_ranks_backwards"] is False
    assert a10["blend_p_rand"] == pytest.approx(2 / 1024, abs=1e-4)
    assert a10["blend_ranks_backwards"] is True
    assert backtest.attribute(nine, gate=False)[
        "blend_ranks_backwards"] is True                               # [A11]


# The rate tests (docs/specs/sign-randomisation-verdicts.md, measure 8 and
# Architecture §11, tests 8–12). Bounds are set in advance from Binomial(N, p),
# never fitted to the seeds.
_H15 = 15
# The keys summarise reads, so the cached worlds stay small.
_SLIM = ("symbol", "t", "direction", "outcome", "bars_held", "predicted",
         "opp_outcome", "opp_bars_held", "opp_predicted", "rr", "k_target",
         "k_stop", "window", "horizons", "truncated", "short_window")


def _both_ways(seed: int, h: int = _H15) -> list[tuple]:
    """Every decision of one correlated world at horizon ``h``, both ways:
    (class, entry time, the row taken LONG, the row taken SHORT). Each
    instrument is replayed once: run_symbol resolves the opposite direction
    of every decision too (pinned row for row against a forced replay in
    test_every_row_carries_the_opposite_directions_outcome), so swapping a
    row's outcome for its opposite one gives the other forced row, with its
    opposite outcome attached as the pair. A short-window row is counted
    only, so it is the same either way."""
    walks, cls = _correlated_world(seed)
    out = []
    for sym, bars in walks.items():
        for row in backtest.run_symbol(bars, h, step=3, keep_timeouts=True):
            kept = {k: row[k] for k in _SLIM}
            if row["short_window"]:
                out.append((cls[sym], row["t"], kept, kept))
                continue
            other = dict(kept, direction=("SHORT" if row["direction"] == "LONG"
                                          else "LONG"),
                         outcome=row["opp_outcome"],
                         bars_held=row["opp_bars_held"],
                         predicted=row["opp_predicted"],
                         opp_outcome=row["outcome"],
                         opp_bars_held=row["bars_held"],
                         opp_predicted=row["predicted"])
            long_row, short_row = ((kept, other) if row["direction"] == "LONG"
                                   else (other, kept))
            out.append((cls[sym], row["t"], long_row, short_row))
    return out


# Worlds 0–29 at h15, replayed once per session and shared by the two
# headline tests, the exactness test, the guards and the power test. A
# replay is cheap (about a quarter of a second a world); the cost is the
# summarise of each coin run, so no test summarises a run another needs:
# the exactness test reads the randomisation alone (code review P2-4).
_cached_world = functools.lru_cache(maxsize=30)(_both_ways)


def _coin_rows(world: list[tuple], tag: str, block_days: int,
               per_class: bool) -> tuple[list, list, list]:
    """The rows one coin takes — resolved, timed out, short-window — when it
    picks one direction per (class, stretch of ``block_days`` calendar days
    from Unix day 0), or per stretch for the whole watchlist when not
    ``per_class``, shared by every instrument it covers: correlated the way
    momentum is, and meaning nothing."""
    import random
    import zlib
    side: dict = {}
    resolved, timeouts, short = [], [], []
    for cls, t, long_row, short_row in world:
        key = (cls if per_class else "ALL", int(t // 86400) // block_days)
        if key not in side:
            side[key] = random.Random(zlib.crc32(
                f"{tag}|{key}".encode())).random() < 0.5
        row = long_row if side[key] else short_row
        (short if row["short_window"] else
         timeouts if row["outcome"] == "TIMEOUT" else resolved).append(row)
    return resolved, timeouts, short


def _coin_run(world: list[tuple], tag: str, block_days: int,
              per_class: bool, h: int = _H15) -> dict:
    """One coin run (:func:`_coin_rows`), summarised as run() would."""
    resolved, timeouts, short = _coin_rows(world, tag, block_days, per_class)
    return backtest.summarise(resolved, step=3, timeouts=timeouts,
                              short_windows=short, horizon_days=h,
                              universe=backtest.WHOLE_WATCHLIST)


def _coin_block(multiple: int, h: int = _H15) -> int:
    """A coin's stretch: ``multiple`` horizons of trading days in calendar
    days, rounded up once — 22 days at h15, 87 for four horizons, 174 for
    eight. The one-horizon coin is nested in the test's 88-day stretches
    (4 × 22); the 87- and 174-day coins cut across them. The test rounds up
    per horizon (backtest.randomisation_block_days, 4 × 22 = 88), which is
    the nested four-horizon coin."""
    return math.ceil(multiple * h * 365 / 252)


def _headline_tag(seed: int, coin: int) -> str:
    return f"{seed}|{_H15}|{coin}|cls"


@functools.lru_cache(maxsize=2)
def _per_class_h_coin(first_world: int) -> tuple[tuple, ...]:
    """The 300 runs of one headline test — 15 worlds from ``first_world`` ×
    20 per-class one-horizon coins at h15 — as (withheld, verdict_state,
    p_tail, stretches)."""
    out = []
    for seed in range(first_world, first_world + 15):
        world = _cached_world(seed)
        for coin in range(20):
            s = _coin_run(world, _headline_tag(seed, coin), _coin_block(1),
                          per_class=True)
            r = s["randomisation"]
            out.append((s["withheld"], s["verdict_state"], r["p_tail"], r["q"]))
    return tuple(out)


def _headline_randomisation(seed: int, coin: int) -> dict:
    """The randomisation of one headline run on its own, as summarise reads
    it — the same stretches (:func:`backtest._direction_clusters`) and the
    same p (:func:`backtest._randomisation`) — without the rest of the
    summary, which is most of a run's cost."""
    resolved, timeouts, _short = _coin_rows(
        _cached_world(seed), _headline_tag(seed, coin), _coin_block(1),
        per_class=True)
    block = backtest.randomisation_block_days(_H15)
    clusters, lines = backtest._direction_clusters(resolved + timeouts, block)
    return backtest._randomisation(clusters, lines, _H15, block, judged=True)


def _assert_headline_rate(runs: tuple[tuple, ...]) -> None:
    assert len(runs) == 300
    # Every run judged, at exactly 8 stretches: a change in the calendar
    # fails here, loudly, instead of quietly withholding runs.
    assert all(w is None for w, _s, _p, _q in runs), [w for w, *_ in runs]
    assert all(q == 8 for _w, _s, _p, q in runs), {q for *_, q in runs}
    verdicts = sum(s in ("beats", "below") for _w, s, _p, _q in runs)
    beats = sum(s == "beats" for _w, s, _p, _q in runs)
    assert verdicts <= 24, f"{verdicts} of 300 coin runs got a verdict"
    assert beats <= 14, f"{beats} of 300 coin runs read 'beats'"


@pytest.mark.slow
def test_a_correlated_coin_rarely_gets_a_verdict():
    """Measure 8, the headline rate test (first of two, split for the 60 s
    cap). 15 worlds of 30 correlated instruments over two years, 20 coins
    each that pick one direction per (class, one-horizon stretch) — the
    validator's per-class coin — at h15: 300 judged runs, every one at
    exactly 8 stretches. Bounds, pre-registered: at most 24 verdicts, the
    99th percentile of Binomial(300, 5%), and at most 14 'beats', that of
    Binomial(300, 2.5%).

    This is a gate against today's code, not proof of 5%. With the error bar
    alone (the gate removed) this coin read 24 verdicts here, exactly at the
    bound, and 31 on the twin's worlds; its rate on these worlds is 9.2%
    (QA, 10 world sets: 7.7–12.8%), at which this test fails with
    probability about 0.73 and one of the two about 0.93. With the
    randomisation it reads 11 here and 9 on the twin's worlds. Proof of 5%
    is measure 1, on real bars at full scale.
    Mutation it catches, with its twin: the randomisation gate removed."""
    _assert_headline_rate(_per_class_h_coin(0))


@pytest.mark.slow
def test_a_correlated_coin_rarely_gets_a_verdict_on_other_worlds():
    """Measure 8, the second headline rate test: worlds 15–29, the same 20
    coins and bounds as the first (see its docstring). A gate against
    today's code, not proof of 5%; with the gate removed it read 31 and
    fails."""
    _assert_headline_rate(_per_class_h_coin(15))


@pytest.mark.slow
def test_the_randomisation_alone_rejects_near_its_size():
    """Measure 8 / Architecture §11 test 9: exactness, on the 600 runs of
    the two headline tests. The coin is nested in the test's stretches, so
    the randomisation alone (p_tail < 0.05, outside the bar or not) is exact
    for it: measured 33 of 600 (5.5%) here, and 22–32 on ten other world
    sets (QA), against 4.0% expected, under 5% because an enumerated p at 8
    stretches steps in 1/256. The count must lie in 13–37, the 0.5–99.5%
    band of Binomial(600, 4.0%).

    It reads each run's randomisation alone, not the whole summary — the
    same stretches and p as summarise, checked on the first three runs — so
    it stays well under the 60 s cap run on its own (code review P2-4).
    Mutation it catches: a dead statistic (never rejects) or an inverted
    one (the wrong tail)."""
    for coin in range(3):
        s = _coin_run(_cached_world(0), _headline_tag(0, coin),
                      _coin_block(1), per_class=True)
        assert s["randomisation"] == _headline_randomisation(0, coin)
    runs = [_headline_randomisation(seed, coin)
            for seed in range(30) for coin in range(20)]
    assert all(r["q"] == 8 and r["method"] == "enumerate" for r in runs)
    rejected = sum(r["p_tail"] < 0.05 for r in runs)
    assert 13 <= rejected <= 37, rejected


def _guard(block_days: int, per_class: bool, name: str) -> int:
    """Verdicts of one guard coin over worlds 0–14, 20 coins each: 300 runs,
    every one judged at exactly 8 stretches."""
    verdicts, judged, stretches = 0, 0, set()
    for seed in range(15):
        world = _cached_world(seed)
        for coin in range(20):
            s = _coin_run(world, f"{seed}|{_H15}|{coin}|{name}", block_days,
                          per_class)
            judged += s["withheld"] is None
            stretches.add(s["randomisation"]["q"])
            verdicts += s["significant"]
    assert judged == 300, judged
    assert stretches == {8}, stretches
    return verdicts


@pytest.mark.slow
def test_a_coin_slower_than_the_stretches_rarely_gets_a_verdict():
    """Measure 2's circular-pass guard: one coin per class held for eight
    horizons (174 days at h15), longer than the test's 88-day stretches and
    not nested in them, so the randomisation is not exact for it. 300
    judged runs on worlds 0–14; at most 34 verdicts, the 99th percentile of
    Binomial(300, 7.5%), measure 2's bar, set before the rate was measured:
    21 here (7.0%), 63 with the gate removed.

    A regression guard, not measure 2. On real bars this coin reads 9.48%
    [8.0–11.3] (r5) and 9.11% [7.6–10.9] held out (validator r7), so
    measure 2 is not met; the owner accepted that and the copy discloses it
    (spec, decisions after validator r7). This bound cannot tell 7.5% from
    9%: it catches the gate gone, not a rate a little over the bar."""
    v = _guard(_coin_block(8), per_class=True, name="cls8h")
    assert v <= 34, f"{v} of 300 runs of the eight-horizon coin got a verdict"


@pytest.mark.slow
def test_a_market_wide_coin_rarely_gets_a_verdict():
    """Measure 2's circular-pass guard: one direction per one-horizon
    stretch for the whole watchlist at once — the failure that forced the
    all-class stretch (8.2% at full scale under (class, stretch) clusters).
    Nested in the test's stretches. 300 judged runs; at most 34 verdicts
    (Binomial(300, 7.5%), 99th percentile). The prototype read 4.7% at h15
    and this test 14 (4.7%); real bars 4.17% (r5) and 3.73% held out
    (validator r7)."""
    v = _guard(_coin_block(1), per_class=False, name="mkt1h")
    assert v <= 34, f"{v} of 300 runs of the market-wide coin got a verdict"


@pytest.mark.slow
def test_a_market_wide_four_horizon_coin_rarely_gets_a_verdict():
    """Measure 2's market-wide four-horizon coin, nested: one direction per
    stretch for the whole watchlist, its stretch rounded as the test rounds
    its own (backtest.randomisation_block_days: 4 × 22 = 88 days at h15),
    so the coin's stretches are the test's (21.9% at full scale under
    (class, stretch) clusters). 300 judged runs; at most 34 verdicts
    (Binomial(300, 7.5%), 99th percentile). Measured 14 here (4.7%), 60 with
    the gate removed (code review P2-3 read 11 and 49 on other coins); real
    bars 5.88% (r5) and 6.25% held out (validator r7)."""
    block = backtest.randomisation_block_days(_H15)
    assert block == 4 * _coin_block(1) == 88
    v = _guard(block, per_class=False, name="mkt4h88")
    assert v <= 34, f"{v} of 300 runs of the nested four-horizon coin got a verdict"


@pytest.mark.slow
def test_an_off_grid_market_wide_coin_rarely_gets_a_verdict():
    """Measure 2's stronger guard, off the grid: one direction per 87-day
    stretch for the whole watchlist (four horizons rounded up once,
    ceil(4 × 15 × 365/252)), so its edges drift one day a stretch across
    the test's 88-day ones — the shifted-edge failure, which the nested
    coin cannot show. 300 judged runs; at most 34 verdicts (Binomial(300,
    7.5%), 99th percentile). Measured 24 here (8.0%), 58 with the gate
    removed (code review P2-3); real bars 8.66% [7.2–10.4] (r5) and 5.73%
    held out (validator r7).

    Its weakness, stated: the bound passes a true 8.7% rate about 95% of the
    time (Binomial(300, 8.7%); validator r7 P2-1). Telling 8.7% from 7.5% needs thousands of
    runs, and 600 would already pass the 60 s cap on a loaded machine, so
    this catches the gate gone (58), not a rate a little over the bar.
    Measure 2 is not met and is disclosed (owner, after validator r7)."""
    assert _coin_block(4) == 87
    v = _guard(_coin_block(4), per_class=False, name="mkt4h")
    assert v <= 34, f"{v} of 300 runs of the off-grid market coin got a verdict"


@pytest.mark.slow
def test_a_strong_edge_still_beats_the_prediction():
    """Architecture §11 test 12: the gate is not blind. On world 0 at h15
    (8 stretches), half the setups take the direction that hit its target
    when exactly one of the two did, the rest a per-setup coin: Δ about +8
    points, and the run reads 'beats' with the randomisation's agreement.
    Mutation it catches: the gate reading the wrong tail, or a dead
    statistic."""
    import random
    rng = random.Random(15)
    resolved, timeouts, short = [], [], []
    for _cls, _t, long_row, short_row in _cached_world(0):
        lw, sw = (long_row["outcome"] == "TARGET",
                  short_row["outcome"] == "TARGET")
        if rng.random() < 0.5 and lw != sw:
            row = long_row if lw else short_row
        else:
            row = long_row if rng.random() < 0.5 else short_row
        (short if row["short_window"] else
         timeouts if row["outcome"] == "TIMEOUT" else resolved).append(row)
    s = backtest.summarise(resolved, step=3, timeouts=timeouts,
                           short_windows=short, horizon_days=_H15,
                           universe=backtest.WHOLE_WATCHLIST)
    assert s["withheld"] is None and s["randomisation"]["q"] == 8
    assert s["delta"] > 0.05, s["delta"]
    assert s["verdict_state"] == "beats", (s["delta"], s["randomisation"])
    assert s["randomisation"]["p_tail"] < backtest.RANDOMISATION_ALPHA


@functools.lru_cache(maxsize=4)
def _attribution_world(seed: int) -> tuple[tuple, tuple]:
    """One correlated world of 20 instruments a class (100), the
    watchlist's breadth, replayed at h15 with momentum's own directions:
    its resolved rows, each tagged with its class, and its timeouts. Built
    once per session for the attribution guard and its real-component
    check."""
    walks, cls = _correlated_world(seed, per_class=20)
    rows, timeouts = [], []
    for sym, bars in walks.items():
        for row in backtest.run_symbol(bars, _H15, step=3, keep_timeouts=True):
            if row["short_window"]:
                continue
            (timeouts if row["outcome"] == "TIMEOUT" else rows).append(
                dict(row, cls=cls[sym]))
    return tuple(rows), tuple(timeouts)


@pytest.mark.slow
def test_a_meaningless_clustered_component_is_rarely_graded():
    """A regression guard, labelled as one: the attribution size gate is the
    real-bar figure of measure 3 (n ≥ 480 per design), not this test.

    The placebo: a news component that is one random value per (class,
    one-horizon stretch), plus a little per-setup noise, and says nothing
    about the outcome; replayed with momentum's own directions on correlated
    walks of 20 instruments a class (100), the watchlist's breadth, at h15 —
    where these two-year worlds fall in 8 stretches, so the run is judged
    (at h20, as this test used to run, they fall in 6 and are withheld).

    Measured before the bound was set, on 240 runs (40 worlds, 6 draws):
    KEEP or INVERTED 2.5% (6) on today's rule, the error bars alone; 0.8%
    (2) with the randomisation, 4 more not told apart from chance. Over ten
    disjoint sets of 24 the graded count was 0–1, the mean spread z² 0.97–
    1.59 and the IC z² 0.48–1.67; with the quintile spread's date-clustered
    bar removed the spread z² was 2.35–4.00. Bounds: at most 4 of 24 graded,
    the 99th percentile of Binomial(24, 5%), measure 3's bar; the spread
    and IC z² bounds of 2.2 and 2.0 are kept from the h20 version. It
    cannot tell the gate from no gate (QA P3-2); the UNCONFIRMED fixtures
    above pin the gate.
    Mutation it catches: the date-clustered floor left out of the quintile
    spread. (The IC's floor is pinned by
    test_the_ic_test_counts_setups_entered_on_the_same_day_together: at h15
    its removal moved the IC z² to 0.65–3.63, which this guard catches on
    half the sets only.)"""
    import random
    import zlib
    from statistics import NormalDist
    h, block = _H15, _coin_block(1)
    graded, ic_z2, sp_z2, runs = 0, 0.0, 0.0, 0
    for seed in range(4):
        cached, timeouts = _attribution_world(seed)
        rows = [dict(t) for t in cached]
        s = backtest.summarise(rows, step=3, timeouts=list(timeouts),
                               horizon_days=h,
                               universe=backtest.WHOLE_WATCHLIST)
        assert s["withheld"] is None and s["n"] > 10000
        for k in range(6):
            noise = random.Random(zlib.crc32(f"p|{seed}|{h}|{k}|cls".encode()))
            draws: dict = {}
            for t in rows:
                key = (t["cls"], int(t["t"] // 86400) // block)
                if key not in draws:
                    draws[key] = random.Random(zlib.crc32(
                        f"{seed}|{h}|{k}|cls|{key}".encode())).random()
                t["c_news"] = 0.8 * draws[key] + 0.2 * noise.random()
            a = backtest.attribute(rows, horizon_days=h)
            assert a["randomisation"]["q"] == 8
            news = next(c for c in a["components"] if c["component"] == "news")
            graded += news["verdict"] in ("KEEP", "INVERTED")
            ic_z2 += NormalDist().inv_cdf(1 - max(news["p"], 1e-12) / 2) ** 2
            sp_z2 += (news["spread"]["spread"] / news["spread"]["se"]) ** 2
            runs += 1
    assert runs == 24
    assert graded <= 4, f"{graded} of 24 meaningless components graded"
    assert sp_z2 / runs <= 2.2, sp_z2 / runs
    assert ic_z2 / runs <= 2.0, ic_z2 / runs


@pytest.mark.slow
def test_a_real_component_is_still_graded_keep_under_the_gate():
    """The attribution guard's other half: on the guard's first world, a
    real component, one setup at a time (IC about 0.08), still reads KEEP
    with the randomisation's agreement — the gate is not blind for
    attribution either.
    Mutation it catches: the gate reading a dead statistic."""
    import random
    cached, _timeouts = _attribution_world(0)
    rows = [dict(t) for t in cached]
    real = random.Random(3)
    for t in rows:
        t["c_news"] = 0.05 * (t["outcome"] == "TARGET") + real.random()
    news = next(c for c in backtest.attribute(
        rows, horizon_days=_H15)["components"] if c["component"] == "news")
    assert news["verdict"] == "KEEP", news
    assert news["confirmed"] is True


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
    mom = backtest.attribute(rows, gate=False)["components"][0]
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
    strong = backtest.attribute(_blend_trials(1500, 1, backwards=True),
                                gate=False)
    assert strong["blend_ic"] < 0
    assert strong["blend_ic_t"] <= -calibration.Z_CLAIM
    assert strong["blend_ranks_backwards"] is True
    withheld = backtest.attribute(_blend_trials(1500, 1, backwards=True),
                                  withheld="span", gate=False)
    assert withheld["blend_ic"] == strong["blend_ic"]
    assert withheld["blend_ranks_backwards"] is False
    # noise past two standard errors, inside the claim bar (t −2.56)
    noise = backtest.attribute(_blend_trials(1500, 43, backwards=False),
                               gate=False)
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
