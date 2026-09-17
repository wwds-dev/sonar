"""Research features: everything knowable on day *t*, and nothing else.

`research/features.py` was 31%, and it is the module where a bug does the most
damage for the least noise. A wrong feature does not crash a study — it
*invalidates* one, and the conclusion still reads like a conclusion.

Two things make that worse here. `panel.build` wraps every call in a bare
`except Exception`, so a feature that raises becomes an all-None column and the
study reports "no signal" rather than "this is broken". And the whole point of
the registry is the **pre-registered direction**: a sign recorded before the
result, so a negative finding cannot be quietly reinterpreted as a positive one
with the sign flipped.

So most of what follows is parametrised across `REGISTRY` — it covers every
feature that exists now and every one added later, which is the only way this
stays true.
"""

import datetime as dt
import math
import random

import pytest

from sonar.research import features as feat
from sonar.research.panel import Ctx

ALL = pytest.mark.parametrize("f", feat.REGISTRY, ids=lambda f: f.name)


def ctx(closes, date=dt.date(2026, 6, 15), symbol="TEST", **kw):
    return Ctx(symbol=symbol, date=date, closes=list(closes),
               highs=[c * 1.01 for c in closes],
               lows=[c * 0.99 for c in closes], **kw)


def walk(n=400, seed=7, sigma=0.01):
    rng = random.Random(seed)
    out = [100.0]
    for _ in range(n):
        out.append(out[-1] * math.exp(rng.gauss(0.0, sigma)))
    return out


def full_ctx(closes=None):
    """A context with everything populated, so no feature returns None for want
    of an input rather than for want of history."""
    closes = closes or walk()
    return ctx(closes, attention_z=1.2,
               attention_recent=[100.0 + i for i in range(25)])


# --------------------------------------------------------------------------- #
# The registry itself
# --------------------------------------------------------------------------- #
def test_the_registry_is_populated():
    assert len(feat.REGISTRY) >= 18


def test_no_two_features_share_a_name():
    names = [f.name for f in feat.REGISTRY]
    assert len(names) == len(set(names))


@ALL
def test_every_feature_pre_registers_a_direction(f):
    """The sign is recorded *before* the result. Without it a negative finding
    can be reinterpreted as a positive one with the sign flipped, which is the
    most common way a backtest lies."""
    assert f.expected in (-1, 0, +1)


@ALL
def test_every_feature_says_why_it_is_there(f):
    assert f.rationale.strip()
    assert f.family.strip()


def test_the_noise_controls_exist_and_claim_nothing():
    """`random_control` must never be significant. If it ever is, the
    multiple-testing correction is broken and every other result is void — so
    it has to be in the registry, and it has to have no directional prior."""
    controls = {f.name: f for f in feat.REGISTRY if f.family == "control"}
    assert {"random_control", "price_level"} <= set(controls)
    assert all(c.expected == 0 for c in controls.values())


def test_every_feature_belongs_to_a_family_by_family_reports():
    grouped = feat.by_family()
    assert sum(len(v) for v in grouped.values()) == len(feat.REGISTRY)
    assert {"price", "risk", "structure", "calendar", "control"} <= set(grouped)


# --------------------------------------------------------------------------- #
# Robustness — because the harness hides an exception as "no signal"
# --------------------------------------------------------------------------- #
@ALL
def test_a_feature_never_raises_on_a_short_history(f):
    """`panel.build` swallows exceptions, so a feature that throws on a short
    window turns into an all-None column and the study calls it 'no signal'."""
    for n in (0, 1, 2, 5, 30):
        f.fn(full_ctx(walk(n)))


@ALL
def test_a_feature_never_raises_on_a_flat_series(f):
    """Zero variance is the divide-by-zero case, and a halted instrument is
    exactly that."""
    f.fn(full_ctx([100.0] * 400))


@ALL
def test_a_feature_never_raises_on_zeros_in_the_history(f):
    """The shape a delisted or halted feed sends. `log(0)` would take it down."""
    closes = walk()
    closes[50] = 0.0
    closes[-1] = 0.0
    f.fn(full_ctx(closes))


@ALL
def test_a_feature_returns_a_finite_number_or_nothing(f):
    """A NaN propagates silently through a whole study; None is honest."""
    value = f.fn(full_ctx())
    assert value is None or (isinstance(value, float) and math.isfinite(value))


@ALL
def test_a_feature_is_deterministic(f):
    """Called twice on the same context it must give the same answer — a
    feature carrying state between rows would leak across instruments."""
    c = full_ctx()
    assert f.fn(c) == f.fn(c)


@ALL
def test_a_feature_does_not_mutate_the_history_it_is_given(f):
    """Every feature shares one Ctx per row. One that sorts or trims in place
    would silently corrupt every feature evaluated after it."""
    c = full_ctx()
    before = list(c.closes)
    f.fn(c)
    assert c.closes == before


# --------------------------------------------------------------------------- #
# Price statistics
# --------------------------------------------------------------------------- #
def test_momentum_is_the_return_over_its_window():
    closes = [100.0] * 395 + [10.0, 20.0, 30.0, 40.0, 50.0, 110.0]
    assert feat.mom_5(ctx(closes)) == pytest.approx(110.0 / 10.0 - 1)


def test_reversal_is_exactly_the_negative_of_momentum():
    """They are built from the same window, so the sign is the only thing
    separating them — and the sign is the whole claim."""
    c = ctx(walk())
    assert feat.reversal_5(c) == pytest.approx(-feat.mom_5(c))


def test_the_long_momentum_skips_the_last_month():
    """The skip is what separates twelve-month momentum from short reversal.
    A spike in the final days must not move it."""
    closes = walk(400)
    quiet = feat.mom_250_ex1m(ctx(closes))
    closes[-5:] = [closes[-6] * 3] * 5
    assert feat.mom_250_ex1m(ctx(closes)) == pytest.approx(quiet)


def test_short_momentum_does_notice_that_spike():
    """The other half of the pair, so 'skips the last month' cannot become
    'ignores everything'."""
    closes = walk(400)
    before = feat.mom_5(ctx(closes))
    closes[-5:] = [closes[-6] * 3] * 5
    assert feat.mom_5(ctx(closes)) != pytest.approx(before)


def test_distance_to_the_high_is_never_positive():
    """Price cannot exceed its own running maximum, so this is bounded at 0 —
    and 0 means 'at the high', which is what the anomaly is about."""
    for seed in range(5):
        assert feat.dist_52w_high(ctx(walk(seed=seed))) <= 0.0
    rising = [100.0 + i for i in range(300)]
    assert feat.dist_52w_high(ctx(rising)) == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Risk and higher moments
# --------------------------------------------------------------------------- #
def test_volatility_is_never_negative():
    assert feat.vol_20(ctx(walk())) > 0.0


def test_a_calmer_name_has_lower_volatility():
    assert feat.vol_20(ctx(walk(sigma=0.002))) < feat.vol_20(ctx(walk(sigma=0.05)))


def test_the_vol_ratio_rises_when_a_name_heats_up():
    calm = walk(400, sigma=0.002)
    heated = calm[:-10] + [calm[-10] * math.exp(0.08 * (-1) ** i) for i in range(10)]
    assert feat.vol_ratio(ctx(heated)) > feat.vol_ratio(ctx(calm))


def test_skew_is_near_zero_for_a_symmetric_series():
    alternating = [100.0 * math.exp(0.01 * (-1) ** i) for i in range(200)]
    assert abs(feat.skew_60(ctx(alternating))) < 0.5


def test_a_one_way_jump_up_skews_the_window_positive():
    """The jump has to *stay*. Raising a single close spikes up and straight
    back down again, which is symmetric and correctly scores zero — my first
    version of this test asserted otherwise and was simply wrong about the
    series, not about the code.
    """
    closes = [100.0 * math.exp(0.001 * (-1) ** i) for i in range(200)]
    for i in range(len(closes) - 3, len(closes)):
        closes[i] *= 1.5
    assert feat.skew_60(ctx(closes)) > 0.5


def test_a_spike_that_immediately_reverses_is_not_skew():
    """The control for the test above — one up move plus one matching down
    move is a symmetric pair, whatever it looks like on a chart."""
    closes = [100.0 * math.exp(0.001 * (-1) ** i) for i in range(200)]
    closes[-3] = closes[-4] * 1.5
    assert abs(feat.skew_60(ctx(closes))) < 0.5


def test_excess_kurtosis_is_measured_against_the_normal():
    """It subtracts 3, so a normal-ish window sits near zero rather than near
    three — an easy sign to lose."""
    assert abs(feat.kurt_60(ctx(walk()))) < 3.0


def test_a_fat_tail_lifts_kurtosis():
    closes = [100.0 * math.exp(0.001 * (-1) ** i) for i in range(200)]
    closes[-5] = closes[-6] * 2.0
    assert feat.kurt_60(ctx(closes)) > feat.kurt_60(ctx(walk()))


def test_drawdown_is_never_positive():
    assert feat.max_dd_60(ctx(walk())) <= 0.0
    assert feat.max_dd_60(ctx([100.0 + i for i in range(300)])) == pytest.approx(0.0)


def test_a_deeper_fall_is_a_deeper_drawdown():
    mild = [100.0] * 250 + [100.0 - i * 0.1 for i in range(60)]
    severe = [100.0] * 250 + [100.0 - i * 1.0 for i in range(60)]
    assert feat.max_dd_60(ctx(severe)) < feat.max_dd_60(ctx(mild))


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #
def test_lag_one_autocorrelation_finds_perfect_mean_reversion():
    """A series that alternates every bar is the textbook case, and it should
    come out close to -1."""
    alternating = [100.0 * math.exp(0.01 * (-1) ** i) for i in range(200)]
    assert feat.autocorr_1(ctx(alternating)) < -0.9


def test_autocorrelation_is_bounded():
    for seed in range(4):
        assert -1.01 <= feat.autocorr_1(ctx(walk(seed=seed))) <= 1.01


def test_hurst_separates_mean_reversion_from_a_random_walk():
    """Asserted as an ordering, not a level. With 60 bars and three window
    sizes the estimator is far too noisy to pin to 0.5, and a test that
    pretended otherwise would just be flaky."""
    alternating = [100.0 * math.exp(0.01 * (-1) ** i) for i in range(200)]
    assert feat.hurst_60(ctx(alternating)) < feat.hurst_60(ctx(walk()))


def test_hurst_needs_enough_history_to_mean_anything():
    assert feat.hurst_60(ctx(walk(30))) is None


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("day", [28, 29, 30, 31, 1, 2, 3])
def test_the_turn_of_the_month_is_flagged(day):
    date = dt.date(2026, 1, day)
    assert feat.turn_of_month(ctx(walk(), date=date)) == 1.0


@pytest.mark.parametrize("day", [4, 12, 20, 27])
def test_mid_month_is_not(day):
    assert feat.turn_of_month(ctx(walk(), date=dt.date(2026, 1, day))) == 0.0


def test_the_month_is_reported_as_a_bare_number():
    """Deliberately crude — it is a control. If a raw month number 'works',
    the pipeline is overfitting."""
    assert feat.month_of_year(ctx(walk(), date=dt.date(2026, 9, 15))) == 9.0


# --------------------------------------------------------------------------- #
# Attention
# --------------------------------------------------------------------------- #
def test_attention_passes_the_precomputed_z_through():
    assert feat.attention_z(ctx(walk(), attention_z=2.5)) == 2.5


def test_attention_with_no_data_is_nothing_rather_than_zero():
    """Zero would read as 'normal attention'; None reads as 'we do not know',
    and the difference matters to every average computed downstream."""
    assert feat.attention_z(ctx(walk())) is None


def test_building_attention_reads_as_a_rising_trend():
    rising = [10.0] * 15 + [100.0] * 10
    assert feat.attention_trend(ctx(walk(), attention_recent=rising)) > 0


def test_fading_attention_reads_as_a_falling_trend():
    fading = [100.0] * 15 + [10.0] * 10
    assert feat.attention_trend(ctx(walk(), attention_recent=fading)) < 0


def test_attention_trend_needs_a_baseline():
    assert feat.attention_trend(ctx(walk(), attention_recent=[1.0] * 5)) is None


# --------------------------------------------------------------------------- #
# The controls, which must stay useless
# --------------------------------------------------------------------------- #
def test_the_random_control_is_stable_for_one_symbol_and_day():
    """Deterministic on purpose: a control that changed between runs would make
    a study irreproducible rather than merely negative."""
    a = ctx(walk(), symbol="AAA", date=dt.date(2026, 4, 1))
    assert feat.random_control(a) == feat.random_control(a)


def test_the_random_control_differs_across_symbols_and_days():
    base = ctx(walk(), symbol="AAA", date=dt.date(2026, 4, 1))
    other_symbol = ctx(walk(), symbol="BBB", date=dt.date(2026, 4, 1))
    other_day = ctx(walk(), symbol="AAA", date=dt.date(2026, 4, 2))
    assert feat.random_control(base) != feat.random_control(other_symbol)
    assert feat.random_control(base) != feat.random_control(other_day)


def test_the_random_control_is_centred_on_zero():
    values = [feat.random_control(ctx(walk(10), symbol=f"S{i}")) for i in range(400)]
    assert all(-0.5 <= v <= 0.5 for v in values)
    assert abs(sum(values) / len(values)) < 0.1


def test_the_price_level_control_is_the_log_price():
    assert feat.price_level(ctx([1.0, 100.0])) == pytest.approx(math.log(100.0))


def test_the_price_level_control_survives_a_dead_feed():
    assert feat.price_level(ctx([100.0, 0.0])) is None
