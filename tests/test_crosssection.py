"""Standardising a component within its own asset class.

The defect, measured on a live 129-instrument screen: the volatility component
had a median of 1.00 in Crypto and 0.14 in Forex, never once exceeding 0.23 for
any currency pair. It was not measuring volatility. It was measuring asset
class — and an extraordinary day in EUR/USD ranked below a dull one in Dogecoin.

The test that matters most is `test_standardising_a_clipped_component_does
_nothing`, because that was the first attempt and it silently did not work.
"""

import pytest

from sonar import crosssection as cs


def test_median_of_an_even_and_an_odd_sample():
    assert cs.median([1, 2, 3]) == 2
    assert cs.median([1, 2, 3, 4]) == 2.5
    assert cs.median([]) == 0.0


def test_mad_is_not_moved_by_one_extreme_member():
    """Which is why it is here rather than a standard deviation: one instrument
    having an extraordinary day is the normal case on this screen."""
    calm = [10, 11, 12, 13, 14]
    with_outlier = calm + [1000]
    assert cs.mad(with_outlier) <= cs.mad(calm) * 2


def test_a_class_too_small_to_standardise_says_so():
    """Two instruments have a median and a deviation. Neither means anything —
    this is exactly what blocked the idea until the watchlist grew."""
    assert cs.zscore(5.0, [1.0, 9.0]) is None


def test_a_class_where_every_member_is_identical_says_so():
    """A real state on a quiet day, not an error."""
    assert cs.zscore(1.0, [1.0] * 20) is None


def test_z_is_clipped_so_one_member_cannot_flatten_the_rest():
    sample = [1.0, 1.1, 0.9, 1.05, 0.95, 1.02, 0.98, 1.01, 1.0, 1.0]
    assert cs.zscore(1e6, sample) == cs.Z_CLIP
    assert cs.zscore(-1e6, sample) == -cs.Z_CLIP


def test_a_typical_member_lands_in_the_middle():
    assert cs.squash(0.0) == pytest.approx(0.5)


def test_squash_is_monotonic_and_bounded():
    xs = [cs.squash(z / 2) for z in range(-8, 9)]
    assert xs == sorted(xs)
    assert all(0.0 < x < 1.0 for x in xs)


# --------------------------------------------------------------------------- #
# The bug the first attempt walked into
# --------------------------------------------------------------------------- #
def test_standardising_a_clipped_component_does_nothing():
    """`assets` derives each component as `min(1, x / scale)`, which pins most
    of Crypto to exactly 1.0. Standardising *that* leaves a within-class
    deviation of zero, so the class that most needed rescaling is the one class
    it cannot touch. This is why `standardise_raw` takes the raw quantity.
    """
    clipped = {f"C{i}": 1.0 for i in range(20)}          # all saturated
    classes = {k: "Crypto" for k in clipped}
    out = cs.standardise(clipped, classes)
    assert all(v == 1.0 for v in out.values()), "nothing to standardise against"


def test_standardising_the_raw_quantity_recovers_the_spread():
    """The same class, but fed the unclipped volatilities underneath."""
    raw = {f"C{i}": 0.03 + i * 0.004 for i in range(20)}  # genuinely different
    absolute = {k: 1.0 for k in raw}                      # all clipped to 1.0
    classes = {k: "Crypto" for k in raw}
    out = cs.standardise_raw(raw, classes, absolute)
    assert max(out.values()) - min(out.values()) > 0.3, "the spread is visible now"


# --------------------------------------------------------------------------- #
# Behaviour
# --------------------------------------------------------------------------- #
def _two_classes():
    """Forex moves in tenths of a percent, Crypto in whole percents — the real
    shape of the problem."""
    raw, classes, absolute = {}, {}, {}
    for i in range(20):
        raw[f"FX{i}"] = 0.002 + i * 0.0004
        classes[f"FX{i}"] = "Forex"
        absolute[f"FX{i}"] = min(1.0, raw[f"FX{i}"] / 0.03)
        raw[f"CR{i}"] = 0.03 + i * 0.004
        classes[f"CR{i}"] = "Crypto"
        absolute[f"CR{i}"] = min(1.0, raw[f"CR{i}"] / 0.03)
    return raw, classes, absolute


def test_a_quiet_class_can_finally_compete():
    """Before: no currency pair exceeded 0.23 however it behaved."""
    raw, classes, absolute = _two_classes()
    out = cs.standardise_raw(raw, classes, absolute)
    best_fx = max(out[k] for k in out if k.startswith("FX"))
    median_crypto = cs.median([out[k] for k in out if k.startswith("CR")])
    assert best_fx > max(absolute[k] for k in absolute if k.startswith("FX"))
    assert best_fx > median_crypto * 0.6


def test_the_gap_between_classes_shrinks():
    raw, classes, absolute = _two_classes()
    out = cs.standardise_raw(raw, classes, absolute)
    before = cs.spread_across({
        "Forex": [absolute[k] for k in absolute if k.startswith("FX")],
        "Crypto": [absolute[k] for k in absolute if k.startswith("CR")]})
    after = cs.spread_across({
        "Forex": [out[k] for k in out if k.startswith("FX")],
        "Crypto": [out[k] for k in out if k.startswith("CR")]})
    assert after < before


def test_ranking_within_a_class_is_preserved():
    """Standardisation may move a class up or down; it must not reorder it."""
    raw, classes, absolute = _two_classes()
    out = cs.standardise_raw(raw, classes, absolute)
    fx = [out[f"FX{i}"] for i in range(20)]
    assert fx == sorted(fx), "the quietest pair should still rank lowest"


def test_a_thin_class_keeps_its_absolute_score():
    """Degrading to today's behaviour is right; degrading to noise is not."""
    raw = {"A": 0.01, "B": 0.05}
    absolute = {"A": 0.3, "B": 0.9}
    out = cs.standardise_raw(raw, {"A": "Tiny", "B": "Tiny"}, absolute)
    assert out == absolute


def test_the_absolute_level_is_still_audible():
    """Not a pure z-score on purpose. At mix 1.0 every class is forced to the
    same distribution, so "nothing is happening anywhere" becomes
    indistinguishable from a normal day and the board always looks busy."""
    assert 0.0 < cs.RELATIVE_MIX < 1.0
    quiet = {f"X{i}": 0.001 for i in range(20)}
    quiet["X0"] = 0.0011
    classes = {k: "Forex" for k in quiet}
    absolute = {k: v / 0.03 for k, v in quiet.items()}
    out = cs.standardise_raw(quiet, classes, absolute)
    assert max(out.values()) < 0.7, "a quiet class should not read as a busy one"


def test_spread_across_needs_more_than_one_group():
    assert cs.spread_across({"only": [1.0, 2.0]}) == 0.0
