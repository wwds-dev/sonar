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
