"""The weekend / hour-of-week study's apparatus (`sonar/research/hourlyvol_weekend.py`),
proven offline on synthetic data with known answers.

Spec: docs/specs/hourly-weekend-vol-study.md. The controls matter more than any
single number: on flat volatility the variants must NOT win (a win would be a
manufactured pattern), and planted effects must be found. Nothing here fetches
data and nothing touches the shipped forecast.
"""

import math
import random

import pytest

from sonar.research import hourlyvol as hv
from sonar.research import hourlyvol_weekend as w
from sonar.research import stats

HOUR = 3600
SUN_23 = 3 * 86400 + 23 * HOUR          # 1970-01-04 23:00 UTC, a Sunday
MON_00 = 4 * 86400


# --------------------------------------------------------------------------- #
# The frozen numbers and the calendar
# --------------------------------------------------------------------------- #
def test_frozen_preregistration_numbers():
    assert (w.LONG_WINDOW, w.WARMUP, w.BLOCKS) == (4368, 4368, 6)
    assert w.HAC_LAGS == 168 and w.CONTEXT_LAGS == (24, 9) and w.BOOT_BLOCK == 168
    assert w.MIN_CLASS_HOURS == 100 and w.MIN_SCORED == 2000
    assert w.THRESHOLD == 0.01 and w.KEEP_BLOCKS == 5
    assert len(w.FAMILY) == 3 and w.SIGNIF_LEVEL == pytest.approx(0.05 / 3)
    assert w.FAMILY == (("V1", "B0"), ("V2", "B0"), ("V2", "B0L"))
    assert hv.PROFILE_CLAMP == (0.25, 4.0) and hv.DIURNAL_WINDOW == 1440


def test_weekday_convention_and_the_weekend_boundary():
    assert w.weekday(0) == 3                                  # 1970-01-01 was a Thursday
    assert w.weekday(MON_00) == 0 and w.weekday(SUN_23) == 6
    assert w.is_weekend(SUN_23), "Sun 23:00 UTC is weekend"
    assert not w.is_weekend(MON_00), "Mon 00:00 UTC is not"
    assert w.is_weekend(2 * 86400) and not w.is_weekend(2 * 86400 - HOUR)   # Sat 00:00 / Fri 23:00
    assert sum(w.is_weekend(MON_00 + h * HOUR) for h in range(168)) == 48


WARM = w.WARMUP


# --------------------------------------------------------------------------- #
# The test statistic
# --------------------------------------------------------------------------- #
def test_one_sided_p_formula():
    assert w.one_sided_p(0.0) == pytest.approx(0.5)
    assert w.one_sided_p(2.0) == pytest.approx(0.5 * stats.normal_p(2.0))
    assert w.one_sided_p(2.0) < 0.05
    assert w.one_sided_p(-2.0) == pytest.approx(1 - 0.5 * stats.normal_p(2.0))
    assert w.one_sided_p(-2.0) > 0.95, "a worse variant must not look significant"


def test_compare_uses_lag_168_and_positive_means_variant_better():
    rng = random.Random(1)
    base = [rng.random() + 1 for _ in range(2400)]
    var = [b - 0.05 + 0.1 * rng.random() for b in base]
    c = w.compare(base, var, context=True)
    d = [b - v for b, v in zip(base, var)]
    assert c["t"] == pytest.approx(stats.newey_west_t(d, lags=168)[0])
    assert c["t_lag24"] == pytest.approx(stats.newey_west_t(d, lags=24)[0])
    assert c["t_lag9"] == pytest.approx(stats.newey_west_t(d, lags=9)[0])
    assert c["t"] != pytest.approx(c["t_lag24"])
    assert c["improvement"] > 0 and c["mean_d"] > 0
    assert len(c["boot_ci_mean_d"]) == 2
    assert w.compare(var, base)["improvement"] < 0


def test_blocks_are_n_floor_6_wide_and_the_remainder_is_dropped():
    base = [1.0] * 61
    var = [1.0] * 61
    # variant better in block 0 only (hours 0..9); the 61st hour is the remainder
    for i in range(10):
        var[i] = 0.5
    var[60] = 0.0                       # in the dropped remainder: must not count
    c = w.compare(base, var)
    assert c["blocks"] == 6 and c["blocks_won"] == 1
    var2 = [1.0] * 61
    var2[60] = 0.0
    assert w.compare(base, var2)["blocks_won"] == 0


@pytest.mark.parametrize("n,imp,won,p,ok,expect", [
    (5000, 0.02, 5, 0.001, True, "KEEP"),
    (5000, 0.02, 6, 0.001, True, "KEEP"),
    (5000, 0.01, 5, 0.001, True, "KEEP"),            # exactly at threshold
    (5000, 0.02, 4, 0.001, True, "WEAK"),
    (5000, 0.02, 5, 0.0167, True, "DROP"),           # p is strict
    (5000, 0.02, 5, 0.02, True, "DROP"),
    (5000, 0.005, 6, 0.001, True, "DETECTED, BELOW THRESHOLD"),
    (5000, 0.0, 6, 0.001, True, "DROP"),
    (5000, -0.02, 6, 0.001, True, "DROP"),
    (1999, 0.02, 6, 0.001, True, "INSUFFICIENT"),
    (2000, 0.02, 6, 0.001, True, "KEEP"),
    (5000, 0.02, 6, 0.001, False, "NOT RUN"),
    (1000, 0.02, 6, 0.001, False, "NOT RUN"),        # NOT RUN comes first
])
def test_verdict_rules_first_match_wins(n, imp, won, p, ok, expect):
    assert w.classify(n, imp, won, p, controls_ok=ok) == expect


def test_pup_shift_is_zero_for_equal_sigma_and_grows_with_the_gap():
    s = [0.004] * 10
    assert w.pup_shift(s, s) == 0.0
    small = w.pup_shift(s, [0.0044] * 10)
    big = w.pup_shift(s, [0.0060] * 10)
    assert 0 < small < big < 0.5


# --------------------------------------------------------------------------- #
# Profiles against a naive reference
# --------------------------------------------------------------------------- #
def test_cells_window_evicts_the_oldest_exactly():
    c = w._Cells(2, window=3)
    for cell, r2 in [(0, 1.0), (1, 1.0), (0, 1.0)]:
        c.push(cell, r2)
    assert c.n == [2, 1]
    c.push(1, 4.0)                       # evicts the first (0, 1.0)
    assert c.n == [1, 2] and c.total == pytest.approx(6.0) and len(c.buf) == 3
    c.push(1, 4.0)                       # evicts (1, 1.0)
    assert c.n == [1, 2] and c.total == pytest.approx(9.0)


def test_cells_factor_matches_diurnal_and_is_clamped_per_factor():
    rng = random.Random(5)
    d, c = hv._Diurnal(window=100), w._Cells(24, window=100)
    for i in range(250):
        r2 = rng.random() ** 3
        d.push(i % 24, r2)
        c.push(i % 24, r2)
    for h in range(24):
        assert c.factor(h) == d.factor(h)
    c2 = w._Cells(24, window=48)
    for i in range(48):
        c2.push(i % 24, 1e-4 if i % 24 else 1.0)
    assert c2.factor(0) == hv.PROFILE_CLAMP[1]
    assert c2.factor(5) >= hv.PROFILE_CLAMP[0]


def test_class_factor_needs_100_hours_and_is_clamped_and_windowed():
    cf = w._ClassFactor(window=2000)
    for _ in range(99):
        cf.push(True, 500.0)             # 99 weekend hours: below the minimum
    for _ in range(1000):
        cf.push(False, 1.0)
    assert cf.factor(True) == 1.0
    cf.push(True, 500.0)                 # the 100th
    assert cf.factor(True) == hv.PROFILE_CLAMP[1], "huge ratio is clamped"
    assert cf.factor(False) == hv.PROFILE_CLAMP[0]
    # window: old weekend hours leave
    cf2 = w._ClassFactor(window=300)
    for _ in range(100):
        cf2.push(True, 2.0)
    for _ in range(200):
        cf2.push(False, 1.0)
    assert cf2.n == {True: 100, False: 200}
    cf2.push(False, 1.0)                 # evicts a weekend hour -> 99 left
    assert cf2.n[True] == 99 and cf2.factor(True) == 1.0


def naive_sigma2(kind, rets, ts, target):
    """From-scratch reference for B0/B0L/V1/V2, written from the spec text."""
    clamp = lambda x: max(0.25, min(4.0, x))
    win = 1440 if kind in ("B0", "V1") else 4368
    cell = (lambda t: w.weekday(t) * 24 + (t % 86400) // 3600) if kind == "V2" \
        else (lambda t: (t % 86400) // 3600)
    hist = []                            # (cell, r2) per past hour
    cls_hist = []                        # (weekend, rd2) per past hour

    def f_of(t):
        h = hist[-win:]
        if not h:
            return 1.0
        tot = sum(r2 for _, r2 in h)
        same = [r2 for c, r2 in h if c == cell(t)]
        if not same or tot <= 0:
            return 1.0
        return clamp((sum(same) / len(same)) / (tot / len(h)))

    def g_of(t):
        if kind != "V1":
            return 1.0
        h = cls_hist[-1440:]
        cl = [x for wk, x in h if wk == w.is_weekend(t)]
        if len(cl) < 100:
            return 1.0
        allm = sum(x for _, x in h) / len(h)
        return clamp((sum(cl) / len(cl)) / allm) if allm > 0 else 1.0

    ewma = None
    for r, t in zip(rets, ts):
        r2 = r * r
        f = f_of(t)
        m = f * g_of(t)
        ewma = max(r2, hv.MIN_VOL ** 2) if ewma is None \
            else 0.94 * ewma + 0.06 * (r2 / m)
        cls_hist.append((w.is_weekend(t), r2 / f))
        hist.append((cell(t), r2))
    return ewma * f_of(target) * g_of(target)


@pytest.mark.parametrize("kind", ["B0", "B0L", "V1", "V2"])
def test_estimators_equal_a_naive_reference(kind):
    """V1/V2 as written in the spec, recomputed from scratch at several
    origins (window not yet full for the long ones; eviction is tested above)."""
    rng = random.Random(9)
    sig = [0.004 * (1.8 if w.is_weekend(w.SYNTH_START + (i + 1) * HOUR) else 1.0)
           * (1.5 if 13 <= (i + 1) % 24 <= 20 else 1.0) for i in range(1700)]
    closes, times = [20000.0], [w.SYNTH_START]
    for i, s in enumerate(sig):
        closes.append(closes[-1] * math.exp(rng.gauss(0, s)))
        times.append(times[-1] + HOUR)
    rets = hv.log_returns(closes)
    for end in (1500, 1600, 1700):
        fast = w.forecast_sigma(closes[:end + 1], times[:end + 1], kind)
        ref = math.sqrt(naive_sigma2(kind, rets[:end], times[1:end + 1],
                                     times[end] + HOUR))
        assert fast == pytest.approx(ref, rel=1e-9), (kind, end)


def test_v1_actually_applies_the_weekend_factor():
    closes, times = w.synth(w.planted_weekend, scored=1500, seed=2)
    sat = next(t for t in range(times[-1] + HOUR, times[-1] + 8 * 86400, HOUR)
               if w.weekday(t) == 5 and t % 86400 == 12 * HOUR)
    mon = sat + 2 * 86400
    v1 = [w.forecast_sigma(closes, times, "V1", t) for t in (sat, mon)]
    b0 = [w.forecast_sigma(closes, times, "B0", t) for t in (sat, mon)]
    assert v1[0] / v1[1] > 1.2 * (b0[0] / b0[1]) > 0


# --------------------------------------------------------------------------- #
# The study path
# --------------------------------------------------------------------------- #
def test_a_gap_aborts_the_study():
    closes, times = w.synth(w.flat, scored=50)
    del closes[100], times[100]
    with pytest.raises(ValueError, match="contiguous"):
        w.study_weekend(closes, times)
    with pytest.raises(ValueError, match="contiguous"):
        w.forecast_sigma(closes, times, "V1")


def test_a_bad_close_aborts_the_study():
    closes, times = w.synth(w.flat, scored=50)
    closes[200] = 0.0
    with pytest.raises(ValueError, match="non-positive"):
        w.study_weekend(closes, times)


def test_too_little_history_is_an_error_not_a_verdict():
    closes, times = w.synth(w.flat, scored=50)
    assert "error" in w.study_weekend(closes[:3000], times[:3000])


def test_scored_hours_start_after_warmup_and_models_share_them():
    closes, times = w.synth(w.flat, scored=2500)
    r = w.study_weekend(closes, times)
    assert r["n_scored"] == 2500
    assert set(r["pooled_qlike"]) == {"B0", "B0L", "V1", "V2", "trailing72", "garch"}
    assert set(r["comparisons"]) == {"V1_vs_B0", "V2_vs_B0", "V2_vs_B0L"}
    assert all(c["n"] == 2500 for c in r["comparisons"].values())
    assert "historical, simulated, forecast loss only" in r["scope"]


def test_controls_failed_means_not_run():
    closes, times = w.synth(w.flat, scored=2500)
    r = w.study_weekend(closes, times, controls_ok=False)
    assert {c["verdict"] for c in r["comparisons"].values()} == {"NOT RUN"}


def test_short_scored_sample_is_insufficient():
    closes, times = w.synth(w.flat, scored=1500)
    r = w.study_weekend(closes, times)
    assert {c["verdict"] for c in r["comparisons"].values()} == {"INSUFFICIENT"}


def test_longer_window_only_label():
    """A V2 that beats B0 but not B0L must not be called a weekday effect."""
    assert w.v2_label("KEEP", {"improvement": 0.002, "p": 0.3}) == "V2: LONGER WINDOW ONLY"
    assert w.v2_label("KEEP", {"improvement": -0.01, "p": 0.001}) == "V2: LONGER WINDOW ONLY"
    assert w.v2_label("KEEP", {"improvement": 0.01, "p": 0.02}) == "V2: LONGER WINDOW ONLY"
    assert w.v2_label("KEEP", {"improvement": 0.01, "p": 0.001}) == "KEEP"
    assert w.v2_label("WEAK", {"improvement": -1.0, "p": 1.0}) == "WEAK"


# --------------------------------------------------------------------------- #
# Synthetic controls (spec C1-C4)
# --------------------------------------------------------------------------- #
def test_c1_flat_volatility_must_not_win():
    c = w.run_c1()
    assert c["ok"], c
    q = c["pooled_qlike"]
    assert q["V1"] >= 0.995 * q["B0"] and q["V2"] >= 0.995 * q["B0"]
    assert "KEEP" not in (c["verdicts"]["V1_vs_B0"], c["verdicts"]["V2_vs_B0"])


def test_c2_planted_weekend_is_found_by_v1():
    c = w.run_c2()
    assert c["ok"], c
    cmp = c["comparison"]
    assert cmp["improvement"] > 0 and cmp["blocks_won"] >= 5 and cmp["p"] < w.SIGNIF_LEVEL


def test_c3_planted_tuesday_window_is_found_by_v2_even_against_b0l():
    c = w.run_c3()
    assert c["ok"], c
    assert c["verdicts"]["V2_vs_B0"] == "KEEP" and c["verdicts"]["V2_vs_B0L"] == "KEEP"


def test_c4_equivalence_causality_and_b0_reproduced():
    assert w.run_c4()["ok"]


def test_run_controls_all_pass():
    r = w.run_controls(size_check=False)
    assert all(r[k]["ok"] for k in ("C1", "C2", "C3", "C4"))
    assert r["ok"] is False, "a skipped size check can never pass the gate"


def test_a_flat_series_with_the_weekend_boundary_shifted_is_not_a_detection():
    """Boundary mutation guard: a weekend planted from Monday 00:00 to Tuesday
    23:00 UTC is the wrong two days, and V1 (Sat/Sun) must not credit it."""
    wrong = lambda t: 0.004 * (1.5 if w.weekday(t) in (0, 1) else 1.0)
    cmp = w.study_weekend(*w.synth(wrong, seed=2))["comparisons"]["V1_vs_B0"]
    assert cmp["verdict"] != "KEEP"


_SIZE_REJECTS = {"V1": 0, "V2": 0}
_SIZE_CHUNKS: list = []


@pytest.mark.slow
@pytest.mark.parametrize("first", [1, 51, 101, 151])
def test_c1_size_check_chunk(first):
    """200 seeds in four chunks (each under the per-test watchdog)."""
    r = w.c1_size_check(seeds=50, first_seed=first)
    _SIZE_CHUNKS.append(first)
    for v, k in r["rejections"].items():
        _SIZE_REJECTS[v] += k


@pytest.mark.slow
def test_c1_size_check_200_seeds_per_variant_rejection_rate():
    assert sorted(_SIZE_CHUNKS) == [1, 51, 101, 151], "run the whole chunk set"
    assert _SIZE_REJECTS["V1"] <= w.C1_SIZE_MAX_REJECTS, _SIZE_REJECTS
    assert _SIZE_REJECTS["V2"] <= w.C1_SIZE_MAX_REJECTS, _SIZE_REJECTS


def test_power_simulation_smoke():
    out = w.power_simulation(seeds=2, multipliers=(1.3,))
    rates = out["detection_rate_v1_vs_b0"]
    assert set(rates) == {1.3} and 0.0 <= rates[1.3] <= 1.0
    assert "simulated" in out["scope"] and "simulated" in out["series"]


# --------------------------------------------------------------------------- #
# The SHA-256 spec check
# --------------------------------------------------------------------------- #
def test_runner_refuses_when_no_approved_hash(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("approved text")
    with pytest.raises(RuntimeError, match="no approved spec hash"):
        w.check_spec(spec, approved="")


def test_runner_refuses_a_changed_spec(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("approved text")
    good = w.spec_sha256(spec)
    assert w.check_spec(spec, approved=good) == good
    spec.write_text("approved text, one number changed")
    with pytest.raises(RuntimeError, match="differs"):
        w.check_spec(spec, approved=good)


def test_main_stops_before_fetching_if_spec_unapproved(monkeypatch):
    monkeypatch.setattr(w, "APPROVED_SPEC_SHA256", "")
    monkeypatch.setattr(hv, "fetch_hourly", lambda *a, **k: pytest.fail("fetched"))
    with pytest.raises(RuntimeError):
        w.main([])


def test_series_hash_is_stable_and_sensitive():
    a = w.series_hash([0, 3600], [1.0, 2.0])
    assert a == w.series_hash([0, 3600], [1.0, 2.0])
    assert a != w.series_hash([0, 3600], [1.0, 2.0000001])


def test_the_live_forecast_is_untouched():
    """The study imports the shipped module and must not change it."""
    closes, times = w.synth(w.flat, scored=200)
    before = hv.forecast(closes, times)
    w.study_weekend(closes, times)
    assert hv.forecast(closes, times) == before


def test_estimators_carry_the_frozen_windows():
    assert w._Est("B0").prof.window == 1440
    assert w._Est("V1").prof.window == 1440 and w._Est("V1").cls.window == 1440
    assert w._Est("B0L").prof.window == 4368 and len(w._Est("B0L").prof.n) == 24
    assert w._Est("V2").prof.window == 4368 and len(w._Est("V2").prof.n) == 168


# --------------------------------------------------------------------------- #
# Review fixes: run identity, size-check gate, warm-up, labels, attribution
# --------------------------------------------------------------------------- #
def test_warmup_below_the_long_window_is_refused():
    closes, times = w.synth(w.flat, scored=300)
    with pytest.raises(ValueError, match="warmup"):
        w.study_weekend(closes, times, warmup=1440)
    assert "n_scored" in w.study_weekend(closes, times, warmup=w.WARMUP)


def test_too_few_closes_has_its_own_message():
    with pytest.raises(ValueError, match="at least two"):
        w.check_series([], [])


def test_pup_shift_survives_a_zero_sigma():
    assert w.pup_shift([0.004], [0.0]) >= 0.0


def test_b0l_vs_b0_attribution_line_is_present_and_outside_the_family():
    closes, times = w.synth(w.flat, scored=2500)
    r = w.study_weekend(closes, times)
    a = r["attribution"]["B0L_vs_B0"]
    assert "attribution only" in a["note"] and "verdict" not in a
    assert set(r["comparisons"]) == {"V1_vs_B0", "V2_vs_B0", "V2_vs_B0L"}
    expect = (r["pooled_qlike"]["B0"] - r["pooled_qlike"]["B0L"]) / r["pooled_qlike"]["B0"]
    assert a["improvement"] == pytest.approx(expect, abs=1e-4)


def test_verdicts_carry_a_gloss_about_forecast_loss_only():
    closes, times = w.synth(w.flat, scored=2500)
    m = w.study_weekend(closes, times)["verdict_meaning"]
    assert "volatility" in m and "historical" in m and "not profit" in m


def test_failed_controls_emit_no_numbers():
    closes, times = w.synth(w.flat, scored=2500)
    r = w.study_weekend(closes, times, controls_ok=False)
    assert "pooled_qlike" not in r
    for c in r["comparisons"].values():
        assert set(c) == {"verdict", "note"} and "not evidence" in c["note"]


def test_c4_names_what_failed(monkeypatch):
    monkeypatch.setattr(w, "forecast_sigma", lambda *a, **k: 1.0)
    r = w.run_c4()
    assert r["ok"] is False and r["failed"] and "replay path" in r["failed"][0]


def test_the_size_check_is_part_of_the_default_gate(monkeypatch):
    called = []
    monkeypatch.setattr(w, "c1_size_check", lambda: called.append(1) or {"ok": True})
    for name in ("run_c1", "run_c2", "run_c3", "run_c4"):
        monkeypatch.setattr(w, name, lambda: {"ok": True})
    assert w.run_controls()["ok"] is True and called
    monkeypatch.setattr(w, "c1_size_check", lambda: {"ok": False})
    assert w.run_controls()["ok"] is False, "a failed size check stops the run"


def test_module_hash_pins_the_source():
    import hashlib
    with open(w.__file__, "rb") as fh:
        assert w.module_sha256() == hashlib.sha256(fh.read()).hexdigest()


def test_uppercase_pasted_hash_is_accepted(tmp_path):
    spec = tmp_path / "s.md"
    spec.write_text("x")
    assert w.check_spec(spec, approved=w.spec_sha256(spec).upper())


def _fake_run(monkeypatch, tmp_path, controls_ok=True):
    spec = tmp_path / "s.md"
    spec.write_text("approved")
    monkeypatch.setattr(w, "SPEC_PATH", spec)
    monkeypatch.setattr(w, "check_spec", lambda: "spechash")
    monkeypatch.setattr(w, "run_controls", lambda: {"ok": controls_ok})
    closes, times = w.synth(w.flat, scored=2500)
    monkeypatch.setattr(hv, "fetch_hourly", lambda *a, **k: (times, closes))
    return times


def test_main_happy_path_records_run_identity(monkeypatch, tmp_path, capsys):
    import json
    times = _fake_run(monkeypatch, tmp_path)
    assert w.main(["--skip-power", "--approving-commit", "abc123"]) == 0
    out = capsys.readouterr().out
    doc = json.loads(out[out.index("{"):])
    assert doc["run"]["module_sha256"] == w.module_sha256()
    assert doc["run"]["approving_commit"] == "abc123"
    assert "re-run" in doc["run"]["note"] and doc["run"]["run_at"].endswith("UTC")
    p = doc["provenance"]
    assert p["bars"] == len(times) and "UTC" in p["period"] and len(p["series_sha256"]) == 64
    assert "power_v1" not in doc and "verdict_meaning" in doc["result"]


def test_main_without_a_commit_says_so_and_runs_power(monkeypatch, tmp_path, capsys):
    import json
    _fake_run(monkeypatch, tmp_path)
    monkeypatch.setattr(w, "power_simulation", lambda: {"scope": "simulated"})
    assert w.main([]) == 0
    out = capsys.readouterr().out
    doc = json.loads(out[out.index("{"):])
    assert doc["run"]["approving_commit"] == "not supplied"
    assert doc["power_v1"]["scope"] == "simulated"


def test_main_stops_as_not_run_when_controls_fail(monkeypatch, tmp_path, capsys):
    _fake_run(monkeypatch, tmp_path, controls_ok=False)
    monkeypatch.setattr(hv, "fetch_hourly", lambda *a, **k: pytest.fail("fetched"))
    assert w.main([]) == 1
    assert "NOT RUN" in capsys.readouterr().out


def test_print_spec_hash(capsys):
    assert w.main(["--print-spec-hash"]) == 0
    assert len(capsys.readouterr().out.strip()) == 64


def test_warmup_one_below_is_refused_too():
    closes, times = w.synth(w.flat, scored=300)
    with pytest.raises(ValueError, match="warmup"):
        w.study_weekend(closes, times, warmup=w.WARMUP - 1)


def test_approving_commit_constant_is_used_when_no_flag(monkeypatch, tmp_path, capsys):
    import json
    _fake_run(monkeypatch, tmp_path)
    monkeypatch.setattr(w, "APPROVED_SPEC_COMMIT", "deadbeef")
    assert w.main(["--skip-power"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out[out.index("{"):])["run"]["approving_commit"] == "deadbeef"
