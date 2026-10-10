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
    assert r["beyond_noise"] is False
    assert r["n_settled"] == 0
    assert "Not enough" in r["verdict"]


def test_a_lucky_streak_is_not_an_edge():
    """Five wins in a row must not be reported as skill."""
    r = calibration.report([pos(90, True) for _ in range(5)])
    assert r["beyond_noise"] is False
    assert r["overall_hit_rate"] == 1.0        # observed...
    assert "Not enough" in r["verdict"]        # ...but not claimed


def test_twenty_trades_describe_the_book_but_do_not_move_p_profit():
    """At the threshold the book is described — and 50% against 40% promised
    is well inside its ±21-point range."""
    r = calibration.report([pos(50, i % 2 == 0)
                            for i in range(calibration.MIN_SAMPLE)])
    assert r["enough"] is True and r["n_settled"] == calibration.MIN_SAMPLE
    assert r["beyond_noise"] is False
    lo, hi = r["hit_rate_ci"]
    assert lo < 0.40 < hi
    assert "within noise" in r["verdict"]


def test_beating_the_odds_is_claimed_only_beyond_three_standard_errors():
    """Asked again after every close: at two standard errors a book with no
    edge eventually 'beats its odds' a quarter to a third of the time."""
    r = calibration.report([pos(50, i < 70) for i in range(100)])   # 70% vs 40%
    assert r["beyond_noise"] is True and "outside the noise" in r["verdict"]
    # 52% of 100: outside a 95% range around 40%, inside a three-sigma one.
    r = calibration.report([pos(50, i < 52) for i in range(100)])
    assert r["hit_rate_ci"][0] > 0.40, "the shown 95% range excludes 40%"
    assert r["beyond_noise"] is False, "but no claim is made at two sigma"


def test_the_report_never_carries_a_drift():
    """The grade is a report, never an input (owner decision 2026-10-10)."""
    r = calibration.report([pos(50, i < 90) for i in range(100)])
    assert "implied_edge_sigma" not in r and "calibrated" not in r


def test_a_manual_close_in_profit_is_not_a_target_hit():
    """The audit's case: 15 hand-closed positions each +$1, 5 stops. Graded on
    the P&L sign that read 75% and switched the drift on for every row."""
    manual = []
    for _ in range(15):
        p = pos(50, True)
        p.outcome, p.pnl = "MANUAL", 1.0
        manual.append(p)
    r = calibration.report(manual + [pos(50, False) for _ in range(5)])
    assert r["n_settled"] == 5 and r["n_manual"] == 15
    assert r["overall_hit_rate"] == 0.0
    assert r["beyond_noise"] is False
    assert all(b["n"] == 0 for b in r["buckets"] if not (40 <= b["lo"] < 60))


def test_the_wilson_interval_behaves_at_the_edges():
    assert calibration.wilson(0, 0) is None
    lo, hi = calibration.wilson(0, 20)
    assert lo == 0.0 and 0.1 < hi < 0.2
    lo, hi = calibration.wilson(10, 20)
    assert lo == pytest.approx(0.299, abs=0.002) and hi == pytest.approx(0.701, abs=0.002)


def test_results_matching_the_odds_read_as_no_edge():
    """40% advertised, 40% realised -> the verdict should say so."""
    trades = [pos(50, i < 40, p_profit=0.4) for i in range(100)]
    r = calibration.report(trades)
    assert r["overall_hit_rate"] == pytest.approx(0.4)
    assert r["beyond_noise"] is False
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


def test_one_wobbling_bucket_does_not_hide_a_real_gradient():
    """The old verdict demanded a strictly rising hit rate across every
    bucket, which one noisy bucket always breaks — so a real gradient read as
    'no clean relationship'. The rank IC over the positions themselves sees
    through the wobble."""
    trades = []
    trades += [pos(10, i < 5) for i in range(25)]     # 20%
    trades += [pos(30, i < 11) for i in range(25)]    # 44%
    trades += [pos(50, i < 9) for i in range(25)]     # 36% — the wobble
    trades += [pos(70, i < 21) for i in range(25)]    # 84%
    r = calibration.report(trades)
    assert r["score_ic"] is not None and r["score_ic"] > 0
    assert "carrying information" in r["verdict"]


def test_a_book_traded_at_one_score_reports_no_ranking_claim():
    """Every position on the same confidence: there is no ranking to grade,
    and the IC must come back None rather than a number."""
    r = calibration.report([pos(50, i % 2 == 0) for i in range(40)])
    assert r["score_ic"] is None


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
