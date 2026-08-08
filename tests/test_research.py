"""Tests for the research apparatus.

A study that reports "nothing found" is only worth anything if it *could* have
found something. So the load-bearing tests here plant a known signal and demand
the machinery detect it, then plant pure noise and demand it stay quiet. Without
both halves, a null result is indistinguishable from a broken instrument.
"""

import math
import random

import pytest

from sonar.research import stats


def test_spearman_is_monotonic_not_linear():
    xs = [1, 2, 3, 4, 5, 6, 7, 8]
    assert stats.spearman(xs, [x ** 3 for x in xs]) == pytest.approx(1.0)
    assert stats.spearman(xs, [-x ** 3 for x in xs]) == pytest.approx(-1.0)


def test_spearman_handles_ties():
    assert stats.spearman([1, 1, 2, 2, 3, 3], [1, 1, 2, 2, 3, 3]) == pytest.approx(1.0)


def test_spearman_needs_a_real_sample():
    assert stats.spearman([1, 2], [1, 2]) is None


def test_newey_west_punishes_autocorrelation():
    """The correction must widen the error bar on overlapping data.

    This is the single most important line in the module: without it, a series
    of overlapping forward returns produces a t-statistic several times too
    large and noise gets published as discovery.
    """
    rng = random.Random(3)
    base = [rng.gauss(0.02, 1.0) for _ in range(400)]
    # heavy overlap: each point shares most of its content with its neighbour
    smeared = [sum(base[max(0, i - 19):i + 1]) / min(20, i + 1)
               for i in range(len(base))]
    t_naive = (sum(smeared) / len(smeared)) / (
        math.sqrt(sum((x - sum(smeared) / len(smeared)) ** 2
                      for x in smeared) / (len(smeared) - 1)) / math.sqrt(len(smeared)))
    t_hac, _ = stats.newey_west_t(smeared, lags=20)
    assert abs(t_hac) < abs(t_naive), "HAC correction did not widen the error bar"


def test_benjamini_hochberg_rejects_a_field_of_nulls():
    """Twenty p-values from pure noise should yield ~no discoveries."""
    rng = random.Random(7)
    pvals = [rng.uniform(0, 1) for _ in range(20)]
    assert sum(stats.benjamini_hochberg(pvals, q=0.10)) <= 2


def test_benjamini_hochberg_keeps_a_strong_signal():
    pvals = [1e-6, 1e-5] + [0.4, 0.6, 0.7, 0.8, 0.9, 0.95]
    keep = stats.benjamini_hochberg(pvals, q=0.10)
    assert keep[0] and keep[1]
    assert not any(keep[2:])


def test_bootstrap_interval_brackets_the_truth():
    rng = random.Random(5)
    xs = [rng.gauss(0.05, 1.0) for _ in range(500)]
    lo, hi = stats.bootstrap_ci(xs)
    assert lo < 0.05 < hi


def test_bootstrap_declines_a_tiny_sample():
    lo, hi = stats.bootstrap_ci([0.1] * 5)
    assert math.isnan(lo) and math.isnan(hi)


# --- the two that decide whether any null result can be believed ---------- #

def _ic_series(effect: float, n: int = 400, seed: int = 1) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(effect, 0.08) for _ in range(n)]


def test_a_planted_signal_is_detected():
    """A genuine IC of 0.04 must come out significant."""
    res = stats.evaluate("planted", "test", +1, _ic_series(0.04), [50] * 400, 20)
    assert res is not None
    assert res.p_value < 0.01
    assert res.sign_agrees
    assert res.ci_low > 0


def test_pure_noise_stays_quiet():
    """A zero-mean IC series must not be called significant."""
    res = stats.evaluate("noise", "test", +1, _ic_series(0.0, seed=9), [50] * 400, 20)
    assert res is not None
    assert res.p_value > 0.05
    assert res.ci_low < 0 < res.ci_high


def test_a_wrong_signed_result_fails_its_hypothesis():
    """Pre-registration means a feature predicted up but measured down does
    not get to count as a win."""
    res = stats.evaluate("backwards", "test", +1, _ic_series(-0.04), [50] * 400, 20)
    assert res.p_value < 0.01           # it is a real effect...
    assert not res.sign_agrees          # ...but not the one claimed


def test_grinolds_law_is_sane():
    assert stats.ic_to_sharpe(0.02, 100) == pytest.approx(0.2)
    assert stats.ic_to_sharpe(0.0, 100) == 0.0


def test_every_feature_declares_a_hypothesis():
    """No feature may enter the study without a pre-registered direction."""
    from sonar.research import features
    assert len(features.REGISTRY) >= 15
    for f in features.REGISTRY:
        assert f.expected in (-1, 0, 1)
        assert f.rationale and len(f.rationale) > 20
        assert f.family


def test_controls_exist_and_are_directionless():
    """The canaries must be present, or a broken pipeline goes unnoticed."""
    from sonar.research import features
    ctrl = [f for f in features.REGISTRY if f.family == "control"]
    assert len(ctrl) >= 2
    assert all(f.expected == 0 for f in ctrl)
