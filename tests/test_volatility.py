"""Volatility forecasting — the one thing the evidence says is forecastable.

All five of SONAR's nulls tested *direction*. This does not: it forecasts how
much a thing will move, never which way, and it is measured against the
volatility that actually followed.

The test that matters most here is `test_the_control_that_caught_the_first
_wrong_answer`. The first version of this study reported GARCH beating the
incumbent by 24% across 26 instruments and 6 of 6 time blocks — which looked
decisive and was mostly an artefact: GARCH sees 250 days of history and the
incumbent saw 22, so a large part of the "improvement" was simply having more
data. A random walk with *constant* volatility has no clustering to exploit, and
on one GARCH loses to a long trailing window. That control is what separates a
real finding here from a flattering one.
"""

import math
import random

import pytest

from sonar import volatility as vol


def walk(n=1200, sigma=0.012, seed=3):
    """Constant volatility: no clustering, nothing for a GARCH to find."""
    rng = random.Random(seed)
    out = [100.0]
    for _ in range(n):
        out.append(out[-1] * math.exp(rng.gauss(0.0, sigma)))
    return out


def clustered(n=1200, seed=5):
    """Volatility that clusters — calm stretches and stormy ones."""
    rng = random.Random(seed)
    out, sig = [100.0], 0.01
    for i in range(n):
        sig = 0.9 * sig + 0.1 * (0.03 if (i // 120) % 2 else 0.005)
        out.append(out[-1] * math.exp(rng.gauss(0.0, sig)))
    return out


# --------------------------------------------------------------------------- #
# The estimators
# --------------------------------------------------------------------------- #
def test_returns_guard_both_ends():
    """A zero close is what a halted feed sends; log(0) would take the estimate
    and everything computed from it."""
    got = vol.log_returns([100.0, 0.0, 100.0, 101.0])
    assert all(math.isfinite(r) for r in got)


@pytest.mark.parametrize("name", list(vol.MODELS))
def test_every_model_returns_a_positive_number_or_nothing(name):
    for closes in (walk(), clustered(), [100.0] * 400):
        v = vol.MODELS[name](vol.log_returns(closes))
        assert v is None or (math.isfinite(v) and v > 0)


@pytest.mark.parametrize("name", list(vol.MODELS))
def test_no_model_raises_on_a_short_history(name):
    for n in (0, 1, 2, 5, 25):
        vol.MODELS[name](vol.log_returns(walk(n)))


@pytest.mark.parametrize("name", list(vol.MODELS))
def test_a_flat_series_gives_a_floor_not_a_zero(name):
    v = vol.MODELS[name](vol.log_returns([100.0] * 400))
    assert v is None or v >= vol.MIN_VOL


def test_a_noisier_series_measures_as_noisier():
    for name in ("trailing", "ewma", "garch"):
        calm = vol.MODELS[name](vol.log_returns(walk(sigma=0.004)))
        wild = vol.MODELS[name](vol.log_returns(walk(sigma=0.04)))
        assert wild > calm, name


def test_ewma_reacts_to_a_recent_shock_faster_than_an_equal_window():
    """The property it exists for: recent days count for more."""
    closes = walk(400, sigma=0.004)
    for _ in range(5):
        closes.append(closes[-1] * 1.06)
    rets = vol.log_returns(closes)
    assert vol.ewma(rets) > vol.trailing(rets, 250)


def test_garch_reverts_toward_the_long_run_and_ewma_does_not():
    """After a shock followed by a long calm stretch, a model with mean
    reversion should have come back down further than one without."""
    closes = walk(200, sigma=0.004)
    closes.append(closes[-1] * 1.15)
    calm = walk(400, sigma=0.004, seed=9)
    closes += [closes[-1] * (c / calm[0]) for c in calm[1:]]
    rets = vol.log_returns(closes)
    assert vol.garch_like(rets) < vol.ewma(rets)


def test_the_blend_sits_between_its_parts():
    rets = vol.log_returns(clustered())
    parts = [vol.trailing(rets), vol.ewma(rets), vol.garch_like(rets)]
    assert min(parts) <= vol.blended(rets) <= max(parts)


# --------------------------------------------------------------------------- #
# The loss, and that scoring is causal
# --------------------------------------------------------------------------- #
def test_a_perfect_forecast_scores_zero():
    assert vol.qlike(0.02, 0.02) == pytest.approx(0.0, abs=1e-12)


def test_qlike_punishes_under_forecasting_harder():
    """Asymmetric on purpose — a risk number that is too low is the dangerous
    direction, and plain squared error treats both the same."""
    under = vol.qlike(0.01, 0.02)
    over = vol.qlike(0.04, 0.02)
    assert under > over


def test_qlike_is_never_negative():
    for f, a in ((0.01, 0.02), (0.05, 0.01), (0.02, 0.02), (1e-9, 0.3)):
        assert vol.qlike(f, a) >= -1e-12


def test_forward_volatility_looks_only_forward():
    rets = [0.0] * 50 + [0.05] * 20
    # The quiet stretch floors at MIN_VOL rather than returning a bare zero —
    # a zero divides by zero one call later.
    assert vol.realised_forward(rets, 0, 20) == pytest.approx(vol.MIN_VOL)
    assert vol.realised_forward(rets, 50, 20) == pytest.approx(0.05, abs=1e-9)


def test_forward_volatility_needs_enough_of_the_window():
    assert vol.realised_forward([0.01] * 30, 25, 20) is None


def test_scoring_never_shows_a_model_its_own_answer(monkeypatch):
    """Every forecast must be made from returns strictly before the window it
    is graded on. A model that saw one bar of the future would look brilliant."""
    rets = vol.log_returns(clustered())
    seen = []

    def spy(sample, *a, **k):
        seen.append(len(sample))
        return vol.trailing(sample)

    monkeypatch.setitem(vol.MODELS, "spy", spy)
    score = vol.score_model(rets, "spy", horizon=20, min_history=250, step=5)
    assert score is not None
    # The longest history handed to the model must still leave a full horizon
    # of unseen returns after it.
    assert max(seen) <= len(rets) - 20


# --------------------------------------------------------------------------- #
# The control
# --------------------------------------------------------------------------- #
def test_the_control_that_caught_the_first_wrong_answer():
    """On constant volatility there is nothing to cluster on, so the model with
    the most effective history should win — and GARCH should not.

    The first run of this study compared GARCH against a 22-day trailing window
    and reported +24%, 26/26 instruments, 6/6 blocks. It was mostly sample size.
    This is the test that says so.
    """
    hist = {f"SYN{i}": walk(1200, seed=i) for i in range(5)}
    result = vol.study(hist, horizon=20, min_history=260)
    pooled = result["pooled_qlike"]
    assert pooled["garch"] > pooled["trailing"] or \
        pooled["garch"] > min(v for v in pooled.values() if v), \
        "GARCH should not win where there is no clustering to find"


def test_clustering_is_where_the_model_earns_its_place():
    """The other half of the pair. Given volatility that genuinely clusters and
    a short horizon, the clustering model should beat a plain window."""
    rets = vol.log_returns(clustered(1600))
    garch = vol.score_model(rets, "garch", horizon=5, min_history=260)
    plain = vol.score_model(rets, "trailing", horizon=5, min_history=260)
    assert garch.qlike < plain.qlike


# --------------------------------------------------------------------------- #
# What the app uses
# --------------------------------------------------------------------------- #
def test_short_horizons_get_the_clustering_model():
    closes = clustered()
    assert vol.forecast(closes, 5) == pytest.approx(
        vol.garch_like(vol.log_returns(closes)))


def test_long_horizons_get_the_long_window():
    closes = clustered()
    assert vol.forecast(closes, 60) == pytest.approx(
        vol.trailing(vol.log_returns(closes), vol.LONG_WINDOW))


def test_the_forecast_degrades_rather_than_failing_on_a_short_series():
    """A newly listed instrument has 30 bars, and the screener still has to
    show it a number."""
    assert vol.forecast(walk(40), 5) is not None
    assert vol.forecast(walk(40), 60) is not None


def test_the_forecast_gives_up_only_when_there_is_nothing_to_measure():
    assert vol.forecast([100.0], 5) is None


def test_every_model_carries_what_it_was_predicted_to_do():
    """Pre-registration: the expectation is recorded before the result, so a
    negative cannot be reinterpreted as a positive afterwards."""
    assert set(vol.PRE_REGISTERED) == set(vol.MODELS) - {"spy"} | {"trailing"} - {"spy"}
    assert all(vol.PRE_REGISTERED[k].strip() for k in vol.PRE_REGISTERED)


def test_the_verdict_demands_consistency_across_time_not_just_on_average():
    """The test that killed three of the five directional findings: winning on
    the pooled average is not enough."""
    lucky = vol.Verdict("x", 0.3, versus_trailing=0.20, beat_on=20,
                        instruments=26, blocks_won=3, blocks=6)
    steady = vol.Verdict("x", 0.3, versus_trailing=0.05, beat_on=20,
                         instruments=26, blocks_won=6, blocks=6)
    assert lucky.verdict == "WEAK"
    assert steady.verdict == "KEEP"


def test_a_model_that_loses_is_dropped():
    assert vol.Verdict("x", 0.6, -0.1, 2, 26, 1, 6).verdict == "DROP"
