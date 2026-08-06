"""Tests for the feedback loop.

The dangerous failure is a *flattering* one: a calibration report that claims an
edge from a handful of lucky trades. So most of these tests are about the
module's willingness to say "not enough data" and to report a flat result as
flat.
"""

import pytest

from sonar import calibration, scoring
from sonar.portfolio import Position


def pos(confidence, won, p_profit=0.4, rr=1.5):
    return Position(
        id="x", symbol="T", name="T", direction="LONG", units=1.0,
        entry=100.0, target=101.5, stop=99.0, opened_at=0.0, cash_at_risk=100.0,
        confidence=confidence, rr=rr, p_profit=p_profit, horizon="week",
        closed_at=1.0, exit=101.5 if won else 99.0,
        pnl=150.0 if won else -100.0, outcome="TARGET" if won else "STOP")


def test_no_trades_makes_no_claim():
    r = calibration.report([])
    assert r["calibrated"] is False
    assert r["n_settled"] == 0
    assert "Not enough" in r["verdict"]


def test_a_lucky_streak_is_not_an_edge():
    """Five wins in a row must not be reported as skill."""
    r = calibration.report([pos(90, True) for _ in range(5)])
    assert r["calibrated"] is False
    assert r["overall_hit_rate"] == 1.0        # observed...
    assert "Not enough" in r["verdict"]        # ...but not claimed


def test_calibration_starts_at_the_threshold():
    r = calibration.report([pos(50, i % 2 == 0)
                            for i in range(calibration.MIN_SAMPLE)])
    assert r["calibrated"] is True
    assert r["n_settled"] == calibration.MIN_SAMPLE


def test_results_matching_the_odds_read_as_no_edge():
    """40% advertised, 40% realised -> the verdict should say so."""
    trades = [pos(50, i < 40, p_profit=0.4) for i in range(100)]
    r = calibration.report(trades)
    assert r["overall_hit_rate"] == pytest.approx(0.4)
    assert abs(r["implied_edge_sigma"]) < 0.05
    assert "no edge" in r["verdict"].lower()


def test_rising_hit_rate_is_detected():
    trades = []
    trades += [pos(30, i < 5) for i in range(25)]     # 20%
    trades += [pos(50, i < 12) for i in range(25)]    # 48%
    trades += [pos(70, i < 20) for i in range(25)]    # 80%
    r = calibration.report(trades)
    assert "carrying information" in r["verdict"]


def test_inverted_hit_rate_is_called_out():
    trades = []
    trades += [pos(30, i < 20) for i in range(25)]    # 80%
    trades += [pos(50, i < 12) for i in range(25)]    # 48%
    trades += [pos(70, i < 5) for i in range(25)]     # 20%
    r = calibration.report(trades)
    assert "worse than useless" in r["verdict"]


def test_small_buckets_are_flagged_not_reported():
    bs = calibration.buckets([pos(50, True) for _ in range(3)])
    b = next(b for b in bs if b.lo == 40)
    assert b.n == 3 and b.enough is False


def test_implied_edge_inverts_the_barrier_maths():
    """Round-trip: drift -> probability -> drift."""
    for m in (-1.0, -0.3, 0.0, 0.3, 1.0, 2.0):
        p = scoring.barrier_probability(1.5, 1.0, m)
        assert calibration.implied_edge(p) == pytest.approx(m, abs=1e-3)


def test_baseline_hit_rate_implies_zero_edge():
    baseline = scoring.barrier_probability(1.5, 1.0, 0.0)
    assert calibration.implied_edge(baseline) == pytest.approx(0.0, abs=1e-6)


def test_beating_the_baseline_implies_positive_edge():
    baseline = scoring.barrier_probability(1.5, 1.0)
    assert calibration.implied_edge(baseline + 0.15) > 0
    assert calibration.implied_edge(baseline - 0.15) < 0


def test_degenerate_hit_rates_do_not_explode():
    assert calibration.implied_edge(0.0) < 0
    assert calibration.implied_edge(1.0) > 0
