"""Tests for risk/reward and the probability of profit.

The property worth defending is the uncomfortable one: with no edge, expected
value is zero no matter how you arrange the targets and stops. If a refactor
ever makes EV drift positive without a measured edge, the app starts quietly
promising profit — which is the exact failure this project exists to avoid.
"""

import math

import pytest

from sonar import scoring


def test_driftless_probability_is_gamblers_ruin():
    """P(profit) = stop / (target + stop) with no drift."""
    assert scoring.barrier_probability(1.0, 1.0) == pytest.approx(0.5)
    assert scoring.barrier_probability(2.0, 1.0) == pytest.approx(1 / 3)
    assert scoring.barrier_probability(1.0, 2.0) == pytest.approx(2 / 3)
    assert scoring.barrier_probability(3.0, 1.0) == pytest.approx(0.25)


def test_reward_and_probability_are_the_same_trade_off():
    """Doubling the target does not create money, it halves the hit rate."""
    for rr in (0.5, 1.0, 1.5, 2.0, 4.0):
        p = scoring.barrier_probability(rr, 1.0)
        assert p == pytest.approx(1.0 / (1.0 + rr))


def test_expected_value_is_zero_without_an_edge():
    """The load-bearing result: no arrangement of barriers beats a coin flip."""
    for k_t in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0):
        p = scoring.barrier_probability(k_t, 1.0)
        assert scoring.expected_value(p, k_t, 1.0) == pytest.approx(0.0, abs=1e-9)


def test_drift_collapses_to_the_driftless_case():
    """The drifted formula must agree with gambler's ruin as the edge vanishes."""
    for k_t, k_s in ((1.5, 1.0), (2.0, 1.0), (1.0, 1.0)):
        base = scoring.barrier_probability(k_t, k_s, 0.0)
        tiny = scoring.barrier_probability(k_t, k_s, 1e-7)
        assert tiny == pytest.approx(base, abs=1e-4)


def test_positive_edge_raises_the_hit_rate():
    base = scoring.barrier_probability(1.5, 1.0, 0.0)
    better = scoring.barrier_probability(1.5, 1.0, 0.5)
    worse = scoring.barrier_probability(1.5, 1.0, -0.5)
    assert better > base > worse
    assert 0.0 <= worse < better <= 1.0


def test_extreme_edges_stay_in_range():
    """No overflow, no probability outside [0, 1], however silly the input."""
    for m in (-1e6, -50.0, 0.0, 50.0, 1e6):
        p = scoring.barrier_probability(1.5, 1.0, m)
        assert 0.0 <= p <= 1.0


def test_plan_places_barriers_by_volatility():
    """A 2%/day name gets wider barriers than a 0.5%/day name at equal price."""
    calm = scoring.build_plan(100.0, 0.005, 4, "LONG")
    wild = scoring.build_plan(100.0, 0.02, 4, "LONG")
    assert wild.target - wild.entry > calm.target - calm.entry
    assert wild.entry - wild.stop > calm.entry - calm.stop
    # ...but the odds are identical, because only the *shape* sets the odds
    assert calm.p_profit == pytest.approx(wild.p_profit)


def test_short_plan_inverts_the_barriers():
    p = scoring.build_plan(100.0, 0.01, 4, "SHORT")
    assert p.target < p.entry < p.stop
    assert p.direction == "SHORT"
    assert p.rr == pytest.approx(scoring.K_TARGET / scoring.K_STOP)


def test_long_plan_orders_barriers_correctly():
    p = scoring.build_plan(100.0, 0.01, 4, "LONG")
    assert p.stop < p.entry < p.target


def test_uncalibrated_plans_never_claim_an_edge():
    p = scoring.build_plan(100.0, 0.01, 4, "LONG")
    assert p.calibrated is False
    assert p.edge_sigma == 0.0
    assert p.ev_per_unit == pytest.approx(0.0, abs=1e-9)
    assert scoring.grade(p.p_profit, p.rr, p.calibrated) == "unproven"


def test_risk_based_sizing_equalises_the_loss():
    """Two very different instruments must risk the same cash at their stops."""
    calm = scoring.build_plan(100.0, 0.005, 4, "LONG")
    wild = scoring.build_plan(100.0, 0.05, 4, "LONG")
    u1, risk1 = scoring.position_size(10_000, 0.01, calm.entry, calm.stop)
    u2, risk2 = scoring.position_size(10_000, 0.01, wild.entry, wild.stop)
    assert risk1 == pytest.approx(risk2) == pytest.approx(100.0)
    assert u1 > u2                      # calmer name -> bigger position
    assert u1 * abs(calm.entry - calm.stop) == pytest.approx(100.0)
    assert u2 * abs(wild.entry - wild.stop) == pytest.approx(100.0)


def test_sizing_refuses_degenerate_inputs():
    assert scoring.position_size(10_000, 0.01, 100.0, 100.0) == (0.0, 0.0)
    assert scoring.position_size(10_000, 0.01, 0.0, 0.0) == (0.0, 0.0)


def test_horizon_sigma_scales_by_root_time():
    assert scoring.horizon_sigma(0.02, 4) == pytest.approx(0.04)
    assert scoring.horizon_sigma(0.01, 25) == pytest.approx(0.05)


# --------------------------------------------------------------------------- #
# The same odds with a deadline (QA-13, docs/adr/0001)
# --------------------------------------------------------------------------- #
# Barriers at +k_target and −k_stop horizon-sigmas, a window of T horizons.
# The backtest watches each setup for four horizons, so T = 4 is the shipped
# full window; these figures are the spec's, from two independent derivations.
_AT_FOUR = {          # k_target: (P_target, P_stop, q = P_t / (P_t + P_s))
    1.0: (0.4954, 0.4954, 0.5000),
    1.5: (0.3743, 0.5743, 0.3946),
    2.0: (0.2719, 0.6051, 0.3100),
    3.0: (0.1212, 0.6166, 0.1643),
}


@pytest.mark.parametrize("k_target", sorted(_AT_FOUR))
def test_the_four_horizon_window_matches_the_table(k_target):
    """T13-1. At 1.5:1 a setup that resolved in time hit its target 39.46%
    of the time on a driftless walk — not 40%.
    Mutation it catches: a wrong image term (the + image dropped, or the
    series stopped after its first term)."""
    p_t, p_s = scoring.barrier_probabilities_within(k_target, 1.0, 4.0)
    want_t, want_s, want_q = _AT_FOUR[k_target]
    assert p_t == pytest.approx(want_t, abs=1e-4)
    assert p_s == pytest.approx(want_s, abs=1e-4)
    assert scoring.resolved_hit_probability(k_target, 1.0, 4.0) == \
        pytest.approx(want_q, abs=1e-4)


@pytest.mark.parametrize("m", [-1.0, 0.0, 0.3, 2.0])
def test_a_long_enough_window_is_the_untimed_answer(m):
    """T13-1. With all the time in the world the deadline stops mattering,
    and the drifted series must land on the closed form.
    Mutation it catches: the Girsanov tilt e^{m(L−x)} dropped or mis-signed."""
    p_t, p_s = scoring.barrier_probabilities_within(1.5, 1.0, 400.0, m)
    assert p_t == pytest.approx(scoring.barrier_probability(1.5, 1.0, m), abs=1e-12)
    assert p_t + p_s == pytest.approx(1.0, abs=1e-12)
    assert scoring.resolved_hit_probability(1.5, 1.0, math.inf, m) == \
        scoring.barrier_probability(1.5, 1.0, m)


def test_the_timed_odds_behave_like_probabilities():
    """T13-1. Never above one together, never negative even at a 1-bar window
    on a 250-day horizon (T = 0.004, where the eigenfunction series went
    negative), and rising with the window.
    Mutation it catches: a series that is not clamped or not truncated
    sensibly at short windows."""
    for k_t in (1.0, 1.5, 2.0, 3.0, 5.0):
        last_t = last_s = 0.0
        for T in (0.004, 0.05, 0.25, 1.0, 2.0, 4.0, 10.0):
            p_t, p_s = scoring.barrier_probabilities_within(k_t, 1.0, T)
            assert p_t >= 0.0 and p_s >= 0.0
            assert p_t + p_s <= 1.0 + 1e-12
            assert p_t >= last_t - 1e-15 and p_s >= last_s - 1e-15
            last_t, last_s = p_t, p_s
    # degenerate inputs: no barrier, or no time, resolves nothing
    assert scoring.barrier_probabilities_within(0.0, 1.0, 4.0) == (0.0, 0.0)
    assert scoring.barrier_probabilities_within(1.5, 1.0, 0.0) == (0.0, 0.0)


def test_a_far_target_almost_never_resolves_first_in_a_short_window():
    """T13-1. Over a very short window only the nearer barrier can register:
    q → 0 when the target is the further one, → 1 when it is the nearer.
    Mutation it catches: the underflow guard returning the untimed odds."""
    assert scoring.resolved_hit_probability(3.0, 1.0, 0.004) < 1e-6
    assert scoring.resolved_hit_probability(1.0, 3.0, 0.004) > 1 - 1e-6
    assert scoring.resolved_hit_probability(2.0, 2.0, 1e-9) == 0.5
    assert scoring.resolved_hit_probability(3.0, 1.0, 1e-9) == 0.0
    assert scoring.resolved_hit_probability(1.0, 3.0, 1e-9) == 1.0


def _eigen(x: float, width: float, mu: float, T: float) -> float:
    """P(leave through ``width`` before 0, by T), from the eigenfunction
    (Fourier sine) series — the independent derivation of the image series.
    The untimed answer minus the decaying modes, tilted by Girsanov."""
    if abs(mu) < 1e-12:
        p_inf = x / width
    else:
        p_inf = (1 - math.exp(-2 * mu * x)) / (1 - math.exp(-2 * mu * width))
    c = mu * mu / 2
    tail = 0.0
    for n in range(1, 400):
        lam = (n * math.pi / width) ** 2 / 2
        b = 2 * (-1) ** (n + 1) / (n * math.pi)
        tail += (b * math.sin(n * math.pi * x / width) * lam / (lam + c)
                 * math.exp(-(lam + c) * T))
    return p_inf - math.exp(mu * (width - x)) * tail


@pytest.mark.parametrize("k_target", [1.0, 1.5, 2.0, 3.0])
@pytest.mark.parametrize("m", [-0.5, 0.0, 0.5, 2.0])
def test_the_image_series_agrees_with_the_eigenfunction_series(k_target, m):
    """T13-2. Two derivations of the same first-passage odds, agreeing to
    1e-9 over windows of half a horizon to four.
    Mutation it catches: any change to the image series' terms or signs."""
    width = k_target + 1.0
    for T in (0.5, 1.0, 2.0, 4.0):
        p_t, p_s = scoring.barrier_probabilities_within(k_target, 1.0, T, m)
        assert p_t == pytest.approx(_eigen(1.0, width, m, T), abs=1e-9)
        assert p_s == pytest.approx(_eigen(k_target, width, -m, T), abs=1e-9)


def test_the_row_probability_of_profit_is_untouched():
    """Non-goal guard: the P(profit) shown on rows stays 1/(1+R:R) (T1-1);
    only the backtest's comparison baseline knows about the deadline."""
    plan = scoring.build_plan(100.0, 0.02, 5, "LONG")
    assert plan.p_profit == pytest.approx(1 / (1 + plan.rr))
