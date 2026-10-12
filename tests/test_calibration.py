"""Tests for the feedback loop.

The dangerous failure is a *flattering* one: a calibration report that claims an
edge from a handful of lucky trades. So most of these tests are about the
module's willingness to say "not enough data" and to report a flat result as
flat.
"""

import bisect as _bisect
import copy
import functools
import importlib.util
import json
import math
import random
from itertools import accumulate
from pathlib import Path

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


# =========================================================================== #
# The time-stop shadow (docs/specs/shadow-time-stop.md, docs/adr/0002)
# =========================================================================== #
# Synthetic books only. The shadow is pre-registered: nothing here reads the
# live book or any copy of it, and conftest keeps every test out of the real
# data directory.

DAY = 86_400.0
OPEN_H = 15 * 3600.0           # entries open mid-session...
STAMP_H = 13.5 * 3600.0        # ...and Yahoo stamps a US bar at the session start


def sp(i="a", conf=50.0, day=0.0, direction="LONG", **kw) -> Position:
    """A protocol entry at 100 with its stop 2 away and its target 3 away
    (R:R 1.5), opened mid-session on ``day``."""
    long_ = direction == "LONG"
    base = dict(id=str(i), symbol="AAA", name="Alpha", direction=direction, units=1.0,
                entry=100.0, target=103.0 if long_ else 97.0, stop=98.0 if long_ else 102.0,
                opened_at=day * DAY + OPEN_H, cash_at_risk=2.0, confidence=conf, rr=1.5,
                p_profit=0.4, horizon="week", asset_class="Equity", protocol=True)
    base.update(kw)
    return Position(**base)


def closed_as(p: Position, outcome: str, at: float) -> Position:
    exit_ = {"TARGET": p.target, "STOP": p.stop}.get(outcome, 100.5)
    p.closed_at, p.exit, p.outcome = at, exit_, outcome
    p.pnl = (1 if p.direction == "LONG" else -1) * (exit_ - p.entry) * p.units
    return p


def daily(first: int, last: int, close=lambda d: 100.0, skip=()) -> list:
    """One bar a day, stamped at the session start: ``(ts, close)``."""
    return [(d * DAY + STAMP_H, float(close(d))) for d in range(first, last + 1)
            if d not in skip]


T_DUE = sp().opened_at + 28 * DAY                    # day 28, 15:00
T_CUT = 29 * DAY + STAMP_H                           # the bar after the T bar
LATER = 40 * DAY


def one(p, bars=None, now=LATER):
    r = calibration.shadow_time_stop([p] if p.is_open else [],
                                     [] if p.is_open else [p],
                                     {"AAA": daily(-5, 40) if bars is None else bars}, now)
    return r, r["entries"][0] if r["entries"] else None


def test_v1_a_barrier_hit_before_t_keeps_its_outcome():
    """V-1. Kills: grading a barrier close as TIME (that would read R off the
    T-bar close, 100.0 here, and give 0)."""
    r, e = one(closed_as(sp(), "TARGET", 10 * DAY))
    assert e["state"] == "target" and e["r"] == pytest.approx(1.5)
    r, e = one(closed_as(sp(), "STOP", 10 * DAY))
    assert e["state"] == "stop" and e["r"] == pytest.approx(-1.0)
    assert r["n_stop"] == 1 and r["n_reached"] == 1


def test_v1_a_barrier_hit_before_t_needs_no_price():
    """ADR §4 rule 1: no price is needed when closed_at ≤ t_T. Kills: sending
    an entry the book already settled to the price check."""
    r, e = one(closed_as(sp(), "TARGET", 10 * DAY), bars=[])
    assert e["state"] == "target"
    assert not calibration.shadow_needs_bars(closed_as(sp(), "TARGET", 10 * DAY), LATER)


def test_v2_a_barrier_hit_after_the_cut_is_graded_at_t():
    """V-2. Kills: ignoring closed_at against T (the book's TARGET at day 30
    is after the T bar and its cut, so the fixed-date result is the T-bar
    close: 101.0 → R = +0.5)."""
    bars = daily(-5, 40, close=lambda d: 101.0 if d == 28 else 100.0)
    r, e = one(closed_as(sp(), "TARGET", 30 * DAY), bars)
    assert e["state"] == "time" and e["exit"] == 101.0
    assert e["r"] == pytest.approx(0.5)


def test_v3_the_cut_is_the_next_bars_stamp_exclusive():
    """V-3. Kills: a `<` / `<=` swap at the cut."""
    bars = daily(-5, 40, close=lambda d: 101.0 if d == 28 else 100.0)
    _r, e = one(closed_as(sp(), "TARGET", T_CUT - 1), bars)
    assert e["state"] == "target"
    _r, e = one(closed_as(sp(), "TARGET", T_CUT), bars)
    assert e["state"] == "time" and e["r"] == pytest.approx(0.5)


def test_v4_the_direction_signs_r():
    """V-4. Kills: dropping the direction sign."""
    bars = daily(-5, 40, close=lambda d: 101.0 if d == 28 else 100.0)
    _r, long_ = one(sp(direction="LONG"), bars)
    _r, short = one(sp(direction="SHORT"), bars)
    assert long_["r"] == pytest.approx(0.5) and short["r"] == pytest.approx(-0.5)


def test_v5_r_is_in_units_of_the_stop_distance():
    """V-5. Kills: dividing by the target distance (that gives +0.5)."""
    bars = daily(-5, 40, close=lambda d: 101.5 if d == 28 else 100.0)
    _r, e = one(sp(), bars)
    assert e["r"] == pytest.approx(0.75)


def test_v6_a_t_bar_still_trading_is_not_a_result():
    """V-6. Kills: using a non-final close. The T bar is the newest bar, so it
    may still be trading: the entry waits for a closing price."""
    r, e = one(sp(), daily(-5, 28), now=T_DUE + 3600)
    assert e["state"] == "wait_price" and e["r"] is None
    assert r["n_reached"] == 0 and r["n_wait_price"] == 1


def test_v7_a_holiday_takes_the_session_before_never_the_one_after():
    """V-7. Kills: look-ahead to the next bar."""
    bars = daily(-5, 40, close=lambda d: {27: 100.7, 29: 101.9}.get(d, 100.0), skip={28})
    _r, e = one(sp(), bars)
    assert e["state"] == "time" and e["exit"] == 100.7


def test_v8_a_daily_close_through_the_stop_is_a_stop_the_polls_missed():
    """V-8. Kills: skipping the gap check. Graded at the stop (R = −1), not at
    the close beyond it, as the book would have filled it."""
    bars = daily(-5, 40, close=lambda d: 97.5 if d == 12 else 100.0)
    r, e = one(sp(), bars)
    assert e["state"] == "stop" and e["gap"] is True and e["r"] == pytest.approx(-1.0)
    assert r["n_gap"] == 1 and r["n_stop"] == 1


def test_v8_the_entry_days_own_close_is_not_a_gap():
    """Build note: only bars that *start* after the entry are certainly closed
    after it. The entry day's close (stamped before the entry) through the
    stop is not graded as a stop."""
    bars = daily(-5, 40, close=lambda d: 97.5 if d == 0 else 100.0)
    _r, e = one(sp(), bars)
    assert e["state"] == "time" and e["gap"] is False


def test_v8_the_first_barrier_crossed_is_the_one_graded():
    bars = daily(-5, 40, close=lambda d: {5: 103.5, 9: 97.0}.get(d, 100.0))
    _r, e = one(sp(), bars)
    assert e["state"] == "target" and e["r"] == pytest.approx(1.5)


def test_v9_manual_entries_and_hand_closes_are_left_out_and_counted():
    """V-9. Kills: grading MANUAL by the sign of its P&L."""
    mine = sp("m", protocol=False)
    hand = closed_as(sp("h"), "MANUAL", 5 * DAY)            # in profit, by hand
    r = calibration.shadow_time_stop([mine], [hand], {"AAA": daily(-5, 40)}, LATER)
    assert r["n_nonprotocol"] == 1 and r["n_left"] == 1
    assert r["n_entered"] == 1 and r["n_reached"] == 0
    assert r["n_target"] == r["n_stop"] == r["n_time"] == 0


def test_v9_a_hand_close_after_the_cut_is_graded_at_t():
    bars = daily(-5, 40, close=lambda d: 101.0 if d == 28 else 100.0)
    _r, e = one(closed_as(sp(), "MANUAL", 35 * DAY), bars)
    assert e["state"] == "time" and e["r"] == pytest.approx(0.5)


def test_v9_a_hand_close_between_t_and_the_cut_is_left_out():
    """A hand close after t_T but inside the T bar's session is still before
    the cut: excluded, like one before T."""
    _r, e = one(closed_as(sp(), "MANUAL", T_DUE + 3600))
    assert e["state"] == "left" and e["r"] is None


def test_a_broken_bar_is_dropped_not_used():
    bars = daily(-5, 40, close=lambda d: 101.0 if d == 28 else 100.0)
    bars[33] = (bars[33][0], float("nan"))                  # the T bar
    _r, e = one(sp(), bars)
    assert e["state"] == "time" and e["exit"] == 100.0       # the session before


def test_a_plan_with_no_stop_distance_has_no_r():
    _r, e = one(sp(stop=100.0))
    assert e["state"] == "no_price" and e["r"] is None


def test_v10_no_price_waits_a_week_then_is_left_out_never_zero():
    """V-10. Kills: treating a missing price as R = 0."""
    r, e = one(sp(), bars=[], now=T_DUE + 3 * DAY)
    assert e["state"] == "wait_price" and r["n_wait_price"] == 1
    r, e = one(sp(), bars=[], now=T_DUE + 8 * DAY)
    assert e["state"] == "no_price" and e["r"] is None
    assert r["n_no_price"] == 1 and r["n_reached"] == 0 and r["mean_r"] is None


def test_a_series_that_does_not_reach_back_to_the_entry_cannot_decide():
    """The gap check needs every close since entry: a range too short to
    cover it is no price, not a clean record."""
    _r, e = one(sp(), daily(5, 40), now=T_DUE + 3 * DAY)
    assert e["state"] == "wait_price"


def test_pending_orders_are_not_positions():
    pend = sp("p", status="PENDING")
    r = calibration.shadow_time_stop([pend], [], {"AAA": daily(-5, 40)}, LATER)
    assert r["n_entered"] == 0 and r["n_nonprotocol"] == 0


def test_an_entry_is_graded_only_from_its_fixed_date():
    """Build note: a barrier hit on day 10 is final, but it is graded from
    t_T on like every other entry, so the running figures never lean on the
    quick resolvers the closed-only grade leans on. Kills: grading early
    barrier hits before T."""
    r, e = one(closed_as(sp(), "TARGET", 10 * DAY), now=20 * DAY)
    assert e["state"] == "waiting" and r["n_reached"] == 0
    assert r["next_t"] == pytest.approx(T_DUE)


def _book_for_readonly():
    rng = random.Random(3)
    held, done = [], []
    for i in range(30):
        p = sp(f"e{i:02d}", conf=rng.uniform(0, 80), day=i * 0.5,
               direction=rng.choice(("LONG", "SHORT")))
        k = i % 4
        if k == 0:
            done.append(closed_as(p, "TARGET", p.opened_at + 3 * DAY))
        elif k == 1:
            done.append(closed_as(p, "STOP", p.opened_at + 40 * DAY))
        elif k == 2:
            done.append(closed_as(p, "MANUAL", p.opened_at + 2 * DAY))
        else:
            held.append(p)
    held.append(sp("mine", protocol=False))
    return held, done


def test_v11_the_shadow_reads_and_changes_nothing():
    """V-11. Kills: writing pos.outcome or pos.exit, or touching the grade."""
    held, done = _book_for_readonly()
    before_held, before_done = copy.deepcopy(held), copy.deepcopy(done)
    before = calibration.report(done)
    bars = {"AAA": daily(-5, 80, close=lambda d: 100.0 + (d % 5) * 0.4)}
    bars_before = copy.deepcopy(bars)
    calibration.shadow_time_stop(held, done, bars, 80 * DAY)
    assert held == before_held and done == before_done and bars == bars_before
    assert calibration.report(done) == before
    assert calibration.GRADED == ("TARGET", "STOP")
    assert calibration.Z_CLAIM == 3.0 and calibration.MIN_SAMPLE == 20
    # Row P(profit) stays the untimed 1/(1+R:R).
    assert scoring.barrier_probability(1.5, 1.0) == pytest.approx(0.4)
    assert scoring.build_plan(100.0, 0.02, 5, "LONG").p_profit == pytest.approx(0.4)


@pytest.mark.parametrize("hits,n,scores", [(0, 0, (50,)), (8, 19, (50,)), (8, 20, (50,)),
                                           (70, 100, (50,)), (52, 100, (50,)),
                                           (30, 60, (10, 50, 90))])
def test_v11_every_verdict_is_the_same_with_the_shadow_computed(hits, n, scores):
    """V-11: each verdict branch, before and after a shadow pass over the
    same positions."""
    closed = [closed_as(sp(f"v{i}", conf=scores[i % len(scores)]),
                        "TARGET" if i < hits else "STOP", DAY) for i in range(n)]
    before = calibration.report(closed)
    calibration.shadow_time_stop([], closed, {"AAA": daily(-5, 40)}, LATER)
    assert calibration.report(closed) == before


def _cohort(n, now_day, extra=()):
    """``n`` week entries opened a day apart, each closed at the target or
    stop on its third day — final, and graded once its T has passed."""
    rng = random.Random(9)
    out = []
    for i in range(n):
        p = sp(f"c{i:03d}", conf=rng.uniform(0, 80), day=float(i))
        out.append(closed_as(p, rng.choice(("TARGET", "STOP")), p.opened_at + 3 * DAY))
    return out + list(extra)


def test_v13_a_cohort_is_the_first_n_by_entry_and_is_fixed_once_evaluated():
    """V-13. Kills: cohort = the first N to *resolve*. An intraday entry made
    after the 45th reaches its T (5.6 days) long before the slow members do;
    picked by resolution it would join look 1 and evaluate it early."""
    fast = closed_as(sp("late-fast", conf=79.0, day=50.0, horizon="intraday"),
                     "TARGET", 50 * DAY + OPEN_H + DAY)
    book = _cohort(45, 0, [fast])
    r = calibration.shadow_time_stop([], book, {}, 60 * DAY)
    look = r["looks"][0]
    assert look["evaluated"] is False and look["entered"] == 45
    assert look["due"] == pytest.approx(44 * DAY + OPEN_H + 28 * DAY)
    r1 = calibration.shadow_time_stop([], book, {}, 75 * DAY)
    look = r1["looks"][0]
    assert look["evaluated"] is True and look["used"] == 45
    members = [e for e in r1["entries"] if e["id"] != "late-fast"]
    assert look["z"] == pytest.approx(calibration.hc3_z(
        [e["confidence"] for e in members], [e["r"] for e in members]))
    # A later entry resolving differently does not move the look.
    flipped = closed_as(sp("late-fast", conf=79.0, day=50.0, horizon="intraday"),
                        "STOP", 50 * DAY + OPEN_H + DAY)
    r2 = calibration.shadow_time_stop([], book[:-1] + [flipped], {}, 75 * DAY)
    assert r2["looks"][0]["z"] == look["z"]


def test_v13_a_look_waits_for_every_member():
    book = _cohort(45, 0)
    held = sp("c044-open", conf=10.0, day=44.0)
    r = calibration.shadow_time_stop([held], book[:44], {"AAA": daily(-5, 72)}, 75 * DAY)
    look = r["looks"][0]
    assert look["evaluated"] is False and look["n_wait_price"] == 1


def test_looks_cross_at_the_boundary_inclusive_and_the_first_crossing_closes(monkeypatch):
    """Kills: `>` for `≥` at the line; one-sided crossing; evaluating a look
    after the design closed."""
    entries = [{"id": f"{i:03d}", "opened_at": float(i), "t_due": float(i),
                "confidence": float(i), "state": "time", "r": 0.0} for i in range(201)]
    zs = iter([-2.315, 9.9, 9.9])
    monkeypatch.setattr(calibration, "hc3_z", lambda x, y: next(zs))
    looks = calibration.shadow_looks(entries)
    assert [lk["evaluated"] for lk in looks] == [True, False, False]
    assert looks[0]["crossed"] is True
    assert [lk["design_closed"] for lk in looks] == [False, True, True]
    zs = iter([2.3149, 2.0, 2.3151])
    looks = calibration.shadow_looks(entries)
    assert [lk["crossed"] for lk in looks] == [False, False, True]


def test_a_look_counts_its_exclusions():
    entries = [{"id": f"{i:03d}", "opened_at": float(i), "t_due": float(i),
                "confidence": float(i % 7), "state": "time", "r": (i % 3) - 1.0}
               for i in range(45)]
    for e in entries[:5]:
        e["state"], e["r"] = "left", None
    look = calibration.shadow_looks(entries)[0]
    assert look["evaluated"] is True and look["n_excluded"] == 5 and look["used"] == 40


def test_v14_t_the_looks_and_the_line_are_pre_registered():
    """V-14. Kills: silently changing T, a look or the boundary. Changing any
    of these needs a new ADR (0002 §1, §3)."""
    assert [calibration.shadow_t_days(h) for h in
            ("intraday", "week", "month", "quarter", "year")] == \
        pytest.approx([5.6, 28.0, 112.0, 336.0, 1400.0])
    assert calibration.SHADOW_T_HORIZONS == 4
    assert calibration.SHADOW_LOOKS == (45, 101, 201)
    assert calibration.SHADOW_BOUNDARY == 2.315
    assert calibration.SHADOW_PRICE_GRACE_DAYS == 7


def test_v16_the_reference_is_the_timed_no_edge_split_per_entry():
    """V-16. Kills: the untimed 40/60 split, or one horizon count for all."""
    eq = sp("e", day=0.0)
    coin = sp("c", day=0.0, symbol="TRX-USD", asset_class="Crypto")
    bars = {"AAA": daily(-5, 40), "TRX-USD": daily(-5, 40)}
    r = calibration.shadow_time_stop([eq, coin], [], bars, LATER)
    by = {e["id"]: e["ref"] for e in r["entries"]}
    assert by["e"] == pytest.approx(list(scoring.barrier_probabilities_within(1.5, 1, 4.0)))
    assert by["c"] == pytest.approx(list(scoring.barrier_probabilities_within(1.5, 1, 5.6)))
    assert by["e"][0] == pytest.approx(0.374, abs=1e-3)
    assert by["e"][1] == pytest.approx(0.574, abs=1e-3)
    want = [(by["e"][0] + by["c"][0]) / 2, (by["e"][1] + by["c"][1]) / 2]
    assert [r["ref"]["target"], r["ref"]["stop"]] == pytest.approx(want)
    assert r["ref"]["neither"] == pytest.approx(1 - sum(want))


def _sims():
    path = Path(__file__).resolve().parent.parent / "docs" / "specs" / "shadow-time-stop-sims.py"
    spec = importlib.util.spec_from_file_location("shadow_sims", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_gate_is_the_hc3_slope_of_the_evidence_script():
    """Kills: the rank IC as the gate, and a naive (homoscedastic) standard
    error. On a heteroscedastic sample the three differ; the gate must be the
    sims' HC3 figure."""
    rng = random.Random(4)
    x = [rng.uniform(0, 80) for _ in range(60)]
    y = [0.01 * c + rng.gauss(0, 0.2 + c / 40) for c in x]
    z = calibration.hc3_z(x, y)
    assert z == pytest.approx(_sims().hc3_z(x, y), rel=1e-12)
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y, strict=True)) / sxx
    s2 = sum((c - my - b * (a - mx)) ** 2 for a, c in zip(x, y, strict=True)) / (n - 2)
    assert abs(z - b / math.sqrt(s2 / sxx)) > 0.05            # not the naive SE
    from sonar.research import stats
    assert abs(z - stats.spearman(x, y) * math.sqrt(n - 1)) > 0.05   # not the rank IC
    entries = [{"id": f"{i:03d}", "opened_at": float(i), "t_due": float(i),
                "confidence": a, "state": "time", "r": c}
               for i, (a, c) in enumerate(zip(x[:45], y[:45], strict=True))]
    assert calibration.shadow_looks(entries)[0]["z"] == pytest.approx(
        calibration.hc3_z(x[:45], y[:45]))


@pytest.mark.parametrize("x,y", [([], []), ([1.0, 2.0], [0.0, 1.0]),
                                 ([5.0] * 6, [1, 2, 3, 4, 5, 6]),
                                 ([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0]),
                                 ([0.0, 0.0, 0.0, 1.0], [1.0, 2.0, 3.0, 4.0])])
def test_an_undefined_gate_is_none_never_nan(x, y):
    """Too few points, one score for all, a perfect fit, or a point with
    leverage 1 (HC3 divides by 1 − h): no slope test, and no NaN."""
    assert calibration.hc3_z(x, y) is None


def test_the_readout_is_plain_json_even_when_degenerate():
    """Every entry at one score: no slope, no rank IC. The dict still goes
    into /api/book as strict JSON."""
    book = [closed_as(sp(f"d{i}", conf=50.0, day=float(i)), "STOP", (i + 1) * DAY)
            for i in range(25)]
    r = calibration.shadow_time_stop([], book, {}, 80 * DAY)
    assert r["z"] is None and r["ic"] is None and r["n_reached"] == 25
    json.dumps(r, allow_nan=False)


def test_the_running_figures_and_counts():
    bars = daily(-5, 70, close=lambda d: 101.0)
    held = [sp(f"o{i}", conf=10.0 * i, day=float(i)) for i in range(3)]
    young = sp("young", day=60.0)
    r = calibration.shadow_time_stop(held + [young], [], {"AAA": bars}, 45 * DAY)
    assert r["n_entered"] == 4 and r["n_time"] == 3 and r["n_waiting"] == 1
    assert r["mean_r"] == pytest.approx(0.5)
    assert r["mean_r_lo"] == pytest.approx(0.5) and r["mean_r_hi"] == pytest.approx(0.5)
    assert r["next_t"] == pytest.approx(young.opened_at + 28 * DAY)
    assert r["t_days"] == 28.0 and r["rr"] == 1.5
    assert r["error"] is None and r["computed_at"] == 45 * DAY
    assert [b["lo"] for b in r["bands"]] == [0, 20]
    mixed = calibration.shadow_time_stop([held[0], sp("m", horizon="month")], [],
                                         {"AAA": bars}, 45 * DAY)
    assert mixed["t_days"] is None


def test_ic_closed_is_reports_statistic_on_the_same_entries():
    """The comparison row: of the graded entries, those the book closed at a
    barrier, ranked as report() ranks them (TARGET 1, STOP 0)."""
    book = []
    for i in range(12):
        p = sp(f"k{i}", conf=float(i * 5), day=float(i))
        book.append(closed_as(p, "TARGET" if i % 3 else "STOP", p.opened_at + DAY))
    r = calibration.shadow_time_stop([], book, {}, 80 * DAY)
    from sonar.research import stats
    assert r["ic_closed"] == pytest.approx(stats.spearman(
        [p.confidence for p in book], [1.0 if p.outcome == "TARGET" else 0.0 for p in book]))
    assert r["n_closed_same"] == 12


# --------------------------------------------------------------------------- #
# V-12: the null size of the whole design, and its power
# --------------------------------------------------------------------------- #
# The walk model of docs/specs/shadow-time-stop-sims.py: driftless, in σ̂ units,
# 20 marks per horizon for SHADOW_T_HORIZONS horizons, target +1.5, stop −1,
# exact fills, R at the path value at T; realised vol / σ̂ = s(score), falling
# 1.3 → 0.5 across scores (the steep gradient), no edge anywhere.
#
# Fast because of scale invariance: a walk of vol s against (1.5, −1) is a
# unit walk against (1.5/s, −1/s). So one library of unit paths, each stored as
# its running-maximum and running-minimum records, answers any s with two
# bisections. The library is drawn once; entries sample paths from it.
V12_STEPS = 20
V12_IC = 0.2                    # the design calculation's power: 0.73 (ADR 0002 §3)
V12_POWER = 0.73
# Always on: a quick run that still separates the design from its mutants.
V12_QUICK_LIBRARY = (20_000, 11)
V12_QUICK_BOOKS = (1_000, 500)  # null, power
# Marked slow: the spec's ≥ 2,000 seeded books, and a 20,000-book precision run.
V12_LIBRARY = (50_000, 12)
V12_BOOKS = 2_000
V12_NULL_SEED = 20_261_012
V12_POWER_SEED = 20_261_013


def _steep(c: float) -> float:
    return 1.3 - 0.8 * c / 80


@functools.lru_cache(maxsize=2)
def _walk_library(m: int, seed: int) -> tuple:
    rng = random.Random(seed)
    sd = math.sqrt(1.0 / V12_STEPS)
    steps = V12_STEPS * calibration.SHADOW_T_HORIZONS
    lib = []
    for _ in range(m):
        ys = list(accumulate(rng.gauss(0.0, sd) for _ in range(steps)))
        hi_v, hi_i, lo_v, lo_i = [], [], [], []
        hi, lo = -math.inf, math.inf
        for i, y in enumerate(ys):
            if y > hi:
                hi = y
                hi_v.append(y)
                hi_i.append(i)
            if y < lo:
                lo = y
                lo_v.append(-y)
                lo_i.append(i)
        lib.append((hi_v, hi_i, lo_v, lo_i, ys))
    return tuple(lib)


def _resolve(path, s: float):
    """(outcome, R, time in horizons) of one path at vol ``s``."""
    hi_v, hi_i, lo_v, lo_i, ys = path
    j = _bisect.bisect_left(hi_v, 1.5 / s)
    up = hi_i[j] if j < len(hi_v) else None
    j = _bisect.bisect_left(lo_v, 1.0 / s)
    down = lo_i[j] if j < len(lo_v) else None
    if up is None and down is None:
        return "time", s * ys[-1], float(calibration.SHADOW_T_HORIZONS)
    if down is None or (up is not None and up < down):
        return "target", 1.5, (up + 1) / V12_STEPS
    return "stop", -1.0, (down + 1) / V12_STEPS


def test_v12_the_fast_walk_library_is_the_sims_walk():
    """The scale trick against a direct step-by-step walk over the same
    increments, at several vols."""
    lib = _walk_library(*V12_QUICK_LIBRARY)
    for path in lib[:200]:
        ys = path[4]
        incs = [ys[0]] + [b - a for a, b in zip(ys, ys[1:], strict=False)]
        for s in (0.5, 0.9, 1.3):
            x, want = 0.0, None
            for i, dy in enumerate(incs):
                x += s * dy
                if x >= 1.5:
                    want = ("target", 1.5, (i + 1) / V12_STEPS)
                    break
                if x <= -1.0:
                    want = ("stop", -1.0, (i + 1) / V12_STEPS)
                    break
            want = want or ("time", x, 4.0)
            got = _resolve(path, s)
            assert got[0] == want[0] and got[1] == pytest.approx(want[1])
            assert got[2] == pytest.approx(want[2])


class _Shut:
    """What report() reads from a closed position."""

    def __init__(self, confidence: float, won: bool):
        self.confidence, self.p_profit = confidence, 0.4
        self.pnl = 1.0 if won else -1.0
        self.outcome = "TARGET" if won else "STOP"


def _v12_null(books: int, seed: int, lib: tuple, closed_only: bool = True):
    """Design rejections; and report()'s closed-only rank IC at 2σ on the same
    books, each 400 entries seen at a random age in [0, T) (n ≈ 200 closed)."""
    rng = random.Random(seed)
    n_design, n_book = calibration.SHADOW_LOOKS[-1], 400
    design = shut = shut_books = shut_n = 0
    for _ in range(books):
        conf = [rng.uniform(0, 80) for _ in range(n_book)]
        res = [_resolve(lib[rng.randrange(len(lib))], _steep(c)) for c in conf]
        entries = [{"id": f"{i:04d}", "opened_at": float(i), "t_due": float(i),
                    "confidence": conf[i], "state": res[i][0], "r": res[i][1]}
                   for i in range(n_design)]
        design += any(lk["crossed"] for lk in calibration.shadow_looks(entries))
        if not closed_only:
            continue
        ages = [rng.uniform(0, calibration.SHADOW_T_HORIZONS) for _ in range(n_book)]
        seen = [_Shut(conf[i], res[i][0] == "target") for i in range(n_book)
                if res[i][0] != "time" and res[i][2] <= ages[i]]
        ic = calibration.report(seen)["score_ic"]
        if ic is not None:
            shut_books += 1
            shut_n += len(seen)
            shut += abs(ic * math.sqrt(len(seen) - 1)) > 2
    return design / books, shut / max(shut_books, 1), shut_n / max(shut_books, 1)


def _v12_power(books: int, seed: int, lib: tuple) -> float:
    """The design's power with R shifted in proportion to score, sized so the
    correlation of score with R is V12_IC."""
    rng = random.Random(seed)
    draws = [_resolve(lib[rng.randrange(len(lib))], _steep(rng.uniform(0, 80)))[1]
             for _ in range(100_000)]
    m = sum(draws) / len(draws)
    var_r = sum((v - m) ** 2 for v in draws) / len(draws)
    beta = V12_IC / math.sqrt(1 - V12_IC ** 2) * math.sqrt(var_r) / (80 / math.sqrt(12))
    hit = 0
    n_design = calibration.SHADOW_LOOKS[-1]
    for _ in range(books):
        conf = [rng.uniform(0, 80) for _ in range(n_design)]
        entries = []
        for i, c in enumerate(conf):
            state, r, _t = _resolve(lib[rng.randrange(len(lib))], _steep(c))
            entries.append({"id": f"{i:04d}", "opened_at": float(i), "t_due": float(i),
                            "confidence": c, "state": state, "r": r + beta * (c - 40.0)})
        hit += any(lk["crossed"] for lk in calibration.shadow_looks(entries))
    return hit / books


def test_v12_quick_the_design_holds_its_size():
    """V-12, always on, null. 1,000 seeded books with no edge and realised vol
    falling with score: the whole three-look design, run through the
    production `shadow_looks`, rejects near 5%. Kills: a boundary of 1.96 per
    look (≈ 10.7%, outside the band). The ±1.5 pt test at 2,000+ books, and
    the closed-only comparison on the same books, are the slow ones below."""
    lib = _walk_library(*V12_QUICK_LIBRARY)
    design = _v12_null(V12_QUICK_BOOKS[0], V12_NULL_SEED, lib, closed_only=False)[0]
    assert 0.025 <= design <= 0.08, design


def test_v12_quick_the_design_has_its_planned_power():
    """V-12, always on, power: R shifted in proportion to score (correlation
    0.2), 500 books, within three Monte-Carlo standard errors of 0.73. Kills:
    a gate that has lost its power (e.g. a boundary of 3σ: 0.46)."""
    lib = _walk_library(*V12_QUICK_LIBRARY)
    books = V12_QUICK_BOOKS[1]
    power = _v12_power(books, V12_POWER_SEED, lib)
    assert abs(power - V12_POWER) <= 3 * math.sqrt(V12_POWER * (1 - V12_POWER) / books), power


@pytest.mark.slow
def test_v12_the_design_holds_its_size_where_the_closed_only_grade_does_not():
    """V-12 as the spec states it: 2,000 seeded books. The design rejects 5% ±
    1.5 pt; the closed-only snapshot statistic on the same books (n ≈ 200)
    rejects measurably more; with a planted correlation of 0.2 the power is
    0.73 within Monte-Carlo error. Run with ``./run-tests.sh tests/ -m slow``."""
    lib = _walk_library(*V12_LIBRARY)
    design, shut, shut_n = _v12_null(V12_BOOKS, V12_NULL_SEED, lib)
    assert 0.035 <= design <= 0.065, design
    se = math.sqrt(design * (1 - design) / V12_BOOKS + shut * (1 - shut) / V12_BOOKS)
    assert shut - design > 3 * se, (shut, design)
    assert 150 <= shut_n <= 250, shut_n
    power = _v12_power(V12_BOOKS, V12_POWER_SEED, lib)
    assert abs(power - V12_POWER) <= 3 * math.sqrt(V12_POWER * (1 - V12_POWER) / V12_BOOKS)


@pytest.mark.slow
def test_v12_slow_the_design_size_to_a_fifth_of_a_point():
    """V-12 at precision: 20,000 null books over ten independent libraries (MC
    standard error 0.17 pt). Measured at build, 2026-10-12: 6.2% here, 5.9%
    with 50,000-path libraries and 5.8% with fresh walks — inside 5 ± 1.5, and
    above 5 because the HC3 z has slightly heavy tails at n = 45: look 1 alone
    rejects 2.7% against Pocock's 2.1% (docs/audit/shadow-time-stop-engineer.md)."""
    rates = [_v12_null(V12_BOOKS, 2_000 + k, _walk_library(V12_QUICK_LIBRARY[0], 100 + k),
                       closed_only=False)[0] for k in range(10)]
    size = sum(rates) / len(rates)
    assert 0.035 <= size <= 0.065, size


@pytest.mark.slow
def test_v12_slow_the_design_power_to_two_points():
    """10,000 power books over five libraries (MC standard error 0.004).
    Measured at build: 0.739."""
    powers = [_v12_power(V12_BOOKS, 3_000 + k, _walk_library(V12_QUICK_LIBRARY[0], 200 + k))
              for k in range(5)]
    power = sum(powers) / len(powers)
    assert abs(power - V12_POWER) <= 0.02, power
