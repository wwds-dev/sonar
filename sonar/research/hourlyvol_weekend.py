"""Weekend / hour-of-week terms for the hourly BTC volatility estimate: a study only.

Implements `docs/specs/hourly-weekend-vol-study.md` (the pre-registration; every
number below is copied from it, none tuned). Nothing here is wired into
`forecast()`, `sonar/model.py` or the running app: this module is imported by
its own tests and its own runner, and by nothing else.

What is measured is **forecast loss (QLIKE) of a volatility estimate on
historical BTC hours**. It is not profit, involves no trading, costs or
slippage (not applicable), and a better-scaled sigma is not a trading
advantage. A DROP is a successful outcome: it means "no improvement detected
here".

Estimators, all causal (every factor is read before the hour is pushed):

* B0  - the shipped `ewma_diurnal` (24 cells, raw r^2, 1440 h window).
* B0L - B0 with a 4368 h window; isolates window length from profile shape.
* V1  - B0 plus a weekend factor g_c on top of the hour-of-day factor f_h.
* V2  - 168 cells (weekday x hour), 4368 h window.

Run: `python3 -m sonar.research.hourlyvol_weekend` (needs network; the owner's
machine). `--print-spec-hash` prints the SHA-256 of the spec file.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sonar.research import hourlyvol as hv
from sonar.research import stats

# --------------------------------------------------------------------------- #
# Frozen pre-registration (spec "Pre-registration (FINAL)")
# --------------------------------------------------------------------------- #
LONG_WINDOW = 4368                 # 26 weeks; also the warm-up before scoring
WARMUP = LONG_WINDOW
BLOCKS = 6
MIN_SCORED = 2000
MIN_CLASS_HOURS = 100              # V1: fewer hours than this in a class -> g = 1
HAC_LAGS = 168
CONTEXT_LAGS = (24, 9)
BOOT_BLOCK = 168
FAMILY = (("V1", "B0"), ("V2", "B0"), ("V2", "B0L"))
SIGNIF_LEVEL = 0.05 / len(FAMILY)         # 0.0167 each
THRESHOLD = 0.01                   # 1.0% pooled improvement; a judgment, not power-derived
KEEP_BLOCKS = 5
C1_SEED = 7
C1_FLOOR = 0.995
C1_SIZE_SEEDS = 200
C1_SIZE_MAX_REJECTS = 10
SYNTH_SIGMA = 0.004
SYNTH_SCORED = 8760
POWER_MULTIPLIERS = (1.05, 1.1, 1.2, 1.3)
POWER_SEEDS = 50
FETCH_DAYS = 730                   # the pull length; also the span check_fresh enforces

#: SHA-256 of the spec file as approved. Left empty until the owner approves
#: (the approving commit hash goes into the spec, then the hash of the file as
#: approved goes here); the runner refuses to run while it is empty or differs.
APPROVED_SPEC_SHA256 = ""
#: Free-text approving commit, recorded in the result block when set (or passed
#: as `--approving-commit <hash>`). Printed, never required: the run does not
#: depend on a version-control tool being present.
APPROVED_SPEC_COMMIT = ""
SPEC_PATH = (Path(__file__).resolve().parents[2]
             / "docs" / "specs" / "hourly-weekend-vol-study.md")

#: What each verdict word means; printed next to every verdict so a bare
#: "KEEP" or "DROP" is not read as a trading instruction.
VERDICT_MEANING = ("Each verdict is a statement about the forecast loss of a "
                   "volatility estimate on historical BTC hours only. KEEP means "
                   "a candidate for a later, separate spec, not a signal and not "
                   "profit; DROP means no improvement was detected here.")

MODELS = ("B0", "B0L", "V1", "V2")
ATTRIBUTION = ("trailing72", "garch")

NOT_EVIDENCE = ("historical, simulated, forecast loss only; not profit, no costs "
                "or slippage (not applicable); a better sigma is a better-scaled "
                "forecast, not a trading advantage; the sample was already seen, "
                "so this is exploratory confirmation, not a clean holdout")


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #
def weekday(t: int) -> int:
    """0 = Monday ... 6 = Sunday, UTC, from a candle open time (unix seconds)."""
    return ((t // 86400) + 3) % 7


def is_weekend(t: int) -> bool:
    """Saturday or Sunday UTC: Sun 23:00 is weekend, Mon 00:00 is not."""
    return weekday(t) >= 5


def hour_of_day(t: int) -> int:
    return (t % 86400) // 3600


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #
class _Cells:
    """A causal variance profile with `ncells` cells over a trailing window of
    hours; same arithmetic and clamp as `hourlyvol._Diurnal`, any cell count."""

    def __init__(self, ncells: int, window: int):
        self.window = window
        self.buf: list[tuple[int, float]] = []
        self.i = 0
        self.per = [0.0] * ncells
        self.n = [0] * ncells
        self.total = 0.0

    def push(self, cell: int, r2: float) -> None:
        if len(self.buf) < self.window:
            self.buf.append((cell, r2))
        else:
            old_c, old_r2 = self.buf[self.i]
            self.per[old_c] -= old_r2
            self.n[old_c] -= 1
            self.total -= old_r2
            self.buf[self.i] = (cell, r2)
            self.i = (self.i + 1) % self.window
        self.per[cell] += r2
        self.n[cell] += 1
        self.total += r2

    def factor(self, cell: int) -> float:
        n = len(self.buf)
        if not n or not self.n[cell] or self.total <= 0:
            return 1.0
        overall = self.total / n
        lo, hi = hv.PROFILE_CLAMP
        return max(lo, min(hi, (self.per[cell] / self.n[cell]) / overall))


class _ClassFactor:
    """V1's weekend / weekday factor: mean(rd2 over the class's hours) over
    mean(rd2 over all hours) in the 1440 h window, clamped; 1 below
    MIN_CLASS_HOURS hours in the class. rd2 = r^2 / f_h as of before that hour."""

    def __init__(self, window: int = hv.DIURNAL_WINDOW):
        self.window = window
        self.buf: list[tuple[bool, float]] = []
        self.i = 0
        self.s = {True: 0.0, False: 0.0}
        self.n = {True: 0, False: 0}

    def push(self, weekend: bool, rd2: float) -> None:
        if len(self.buf) < self.window:
            self.buf.append((weekend, rd2))
        else:
            old_w, old = self.buf[self.i]
            self.s[old_w] -= old
            self.n[old_w] -= 1
            self.buf[self.i] = (weekend, rd2)
            self.i = (self.i + 1) % self.window
        self.s[weekend] += rd2
        self.n[weekend] += 1

    def factor(self, weekend: bool) -> float:
        if self.n[weekend] < MIN_CLASS_HOURS:
            return 1.0
        total_n = self.n[True] + self.n[False]
        all_mean = (self.s[True] + self.s[False]) / total_n
        if all_mean <= 0:
            return 1.0
        lo, hi = hv.PROFILE_CLAMP
        return max(lo, min(hi, (self.s[weekend] / self.n[weekend]) / all_mean))


class _Est:
    """One of B0, B0L, V1, V2: EWMA on r^2 / (factors as of before the hour),
    forecast = EWMA x factors of the target hour. Clamp applies to each factor
    separately; the product is not re-clamped."""

    def __init__(self, kind: str):
        if kind not in MODELS:
            raise ValueError(kind)
        self.kind = kind
        self.cls = None
        if kind in ("B0", "V1"):
            self.prof = hv._Diurnal()
        elif kind == "B0L":
            self.prof = _Cells(24, LONG_WINDOW)
        else:
            self.prof = _Cells(168, LONG_WINDOW)
        if kind == "V1":
            self.cls = _ClassFactor()
        self.ewma: float | None = None

    def _cell(self, t: int) -> int:
        if self.kind == "V2":
            return weekday(t) * 24 + hour_of_day(t)
        return hour_of_day(t)

    def _mult(self, t: int) -> float:
        f = self.prof.factor(self._cell(t))
        if self.cls is None:
            return f
        return f * self.cls.factor(is_weekend(t))

    def var(self, t: int) -> float:
        """Variance forecast for the hour opening at `t`."""
        return self.ewma * self._mult(t)

    def push(self, t: int, r: float) -> None:
        """Let the return of the hour opening at `t` into the state."""
        r2 = r * r
        cell = self._cell(t)
        if self.ewma is None:
            self.ewma = max(r2, hv.MIN_VOL ** 2)
        else:
            self.ewma = (hv.EWMA_LAMBDA * self.ewma
                         + (1 - hv.EWMA_LAMBDA) * (r2 / self._mult(t)))
        if self.cls is not None:
            self.cls.push(is_weekend(t), r2 / self.prof.factor(cell))
        self.prof.push(cell, r2)


# --------------------------------------------------------------------------- #
# Inputs and the one-sided test
# --------------------------------------------------------------------------- #
def check_series(closes: list[float], times: list[int]) -> list[float]:
    """Log returns, after asserting a contiguous hourly series of positive
    prices. A gap or a bad close aborts: it would shift every weekday cell."""
    if len(closes) < 2:
        raise ValueError("need at least two closes")
    if len(closes) != len(times):
        raise ValueError("closes and times differ in length")
    if any(b - a != 3600 for a, b in zip(times, times[1:])):
        raise ValueError("series is not contiguous at 3600 s steps; aborting")
    rets = hv.log_returns(closes)
    if len(rets) != len(closes) - 1:
        raise ValueError("non-positive close in the series; aborting")
    return rets


def one_sided_p(t: float) -> float:
    """p that the variant is better: 0.5*normal_p(t) if t > 0 else 1 - 0.5*normal_p(t).
    (`stats.normal_p` is two-sided.)"""
    p2 = stats.normal_p(t)
    return 0.5 * p2 if t > 0 else 1.0 - 0.5 * p2


def series_hash(times: list[int], closes: list[float]) -> str:
    h = hashlib.sha256()
    for t, c in zip(times, closes):
        h.update(f"{t},{c!r}\n".encode())
    return h.hexdigest()


def compare(base: list[float], variant: list[float], blocks: int = BLOCKS,
            context: bool = False) -> dict:
    """One pre-registered comparison. d = loss_base - loss_variant, so
    positive means the variant is better."""
    n = len(base)
    d = [b - v for b, v in zip(base, variant)]
    pooled_b, pooled_v = sum(base) / n, sum(variant) / n
    width = n // blocks
    won = sum(1 for k in range(blocks)
              if sum(variant[k * width:(k + 1) * width])
              < sum(base[k * width:(k + 1) * width]))
    t, _ = stats.newey_west_t(d, lags=HAC_LAGS)
    out = {"n": n, "improvement": (pooled_b - pooled_v) / pooled_b,
           "blocks_won": won, "blocks": blocks, "t": t, "p": one_sided_p(t),
           "mean_d": sum(d) / n}
    if context:
        for lag in CONTEXT_LAGS:
            tl, _ = stats.newey_west_t(d, lags=lag)
            out[f"t_lag{lag}"], out[f"p_lag{lag}"] = tl, one_sided_p(tl)
        out["boot_ci_mean_d"] = stats.bootstrap_ci(d, block=BOOT_BLOCK)
    return out


def classify(n: int, improvement: float, blocks_won: int, p: float,
             controls_ok: bool = True) -> str:
    """The verdict rules, first match wins (spec "Verdict")."""
    if not controls_ok:
        return "NOT RUN"
    if n < MIN_SCORED:
        return "INSUFFICIENT"
    if improvement >= THRESHOLD and p < SIGNIF_LEVEL:
        return "KEEP" if blocks_won >= KEEP_BLOCKS else "WEAK"
    if 0 < improvement < THRESHOLD and p < SIGNIF_LEVEL:
        return "DETECTED, BELOW THRESHOLD"
    return "DROP"


def v2_label(verdict: str, vs_longer_window: dict) -> str:
    """V2's KEEP also needs I > 0 and p < SIGNIF_LEVEL against B0L; otherwise the win
    is the longer window and the words "weekday effect" are not used."""
    if verdict == "KEEP" and not (vs_longer_window["improvement"] > 0
                                  and vs_longer_window["p"] < SIGNIF_LEVEL):
        return "V2: LONGER WINDOW ONLY"
    return verdict


def pup_shift(sig_base: list[float], sig_var: list[float]) -> float:
    """The threshold in the user's unit: mean absolute change in displayed
    P(up) = Phi(move / sigma) for a move of half the base sigma, over the
    scored hours (one-hour horizon, tau = 1)."""
    def phi(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    return (sum(abs(phi(0.5 * sb / max(sv, hv.MIN_VOL)) - phi(0.5)) for sb, sv in zip(sig_base, sig_var))
            / len(sig_base))


# --------------------------------------------------------------------------- #
# The study
# --------------------------------------------------------------------------- #
def study_weekend(closes: list[float], times: list[int], warmup: int = WARMUP,
                  controls_ok: bool = True, context: bool = False,
                  trace: dict | None = None) -> dict:
    """Walk every hour once; score B0, B0L, V1, V2 (plus trailing72 and garch,
    attribution only) on the same hours after `warmup` hours."""
    if warmup < WARMUP:
        raise ValueError(f"warmup {warmup} is below the {WARMUP} h the 26-week "
                         "models need to fill their window")
    rets = check_series(closes, times)
    if len(rets) < warmup + 1:
        return {"error": f"need more than {warmup} clean hourly returns, "
                         f"got {len(rets)}"}
    ts = times[1:]                       # open time of each return's (scored) hour

    est = {m: _Est(m) for m in MODELS}
    trail = hv._Rolling(hv.TRAILING)
    lr720 = hv._Rolling(720)
    garch_var = None
    loss: dict[str, list[float]] = {m: [] for m in MODELS + ATTRIBUTION}
    sig: dict[str, list[float]] = {m: [] for m in MODELS}
    if trace is not None:
        trace.update({m: [] for m in MODELS})

    for i, (r, t) in enumerate(zip(rets, ts)):
        if i >= warmup:
            a = abs(r)
            for m in MODELS:
                s = math.sqrt(est[m].var(t))
                sig[m].append(s)
                loss[m].append(hv.qlike(s, a))
                if trace is not None:
                    trace[m].append((i, s))
            loss["trailing72"].append(hv.qlike(trail.std(), a))
            loss["garch"].append(hv.qlike(math.sqrt(garch_var), a))
        r2 = r * r
        for m in MODELS:
            est[m].push(t, r)
        trail.push(r)
        lr720.push(r)
        if garch_var is None:
            garch_var = max(r2, hv.MIN_VOL ** 2)
        else:
            long_run = max(lr720.mean_sq(), hv.MIN_VOL ** 2)
            omega = long_run * (1 - hv.GARCH_ALPHA - hv.GARCH_BETA)
            garch_var = omega + hv.GARCH_ALPHA * r2 + hv.GARCH_BETA * garch_var

    n = len(loss["B0"])
    comps = {}
    for v, b in FAMILY:
        c = compare(loss[b], loss[v], context=context)
        c["pup_shift"] = pup_shift(sig[b], sig[v])
        c["verdict"] = classify(n, c["improvement"], c["blocks_won"], c["p"], controls_ok)
        comps[f"{v}_vs_{b}"] = c
    # V2's KEEP needs it to beat the longer-window baseline too.
    c2 = comps["V2_vs_B0"]
    c2["verdict"] = v2_label(c2["verdict"], comps["V2_vs_B0L"])

    if not controls_ok:
        # Failed apparatus: the numbers are not evidence and are not emitted.
        return {"n_scored": n, "controls_ok": False,
                "comparisons": {k: {"verdict": c["verdict"],
                                    "note": "apparatus failed; not evidence"}
                                for k, c in comps.items()},
                "verdict_meaning": VERDICT_MEANING, "scope": NOT_EVIDENCE}

    # B0L vs B0 is attribution only (window length), not a hypothesis.
    attribution = {"B0L_vs_B0": compare(loss["B0"], loss["B0L"], context=context)}
    attribution["B0L_vs_B0"]["note"] = "attribution only; not part of the family"

    return {"n_scored": n, "blocks": BLOCKS, "significance_level": SIGNIF_LEVEL, "threshold": THRESHOLD,
            "pooled_qlike": {m: round(sum(x) / n, 5) for m, x in loss.items()},
            "comparisons": comps, "attribution": attribution,
            "verdict_meaning": VERDICT_MEANING, "scope": NOT_EVIDENCE}


def forecast_sigma(closes: list[float], times: list[int], model: str,
                   target_time: int | None = None) -> float:
    """A `hourlyvol.forecast()`-style path: replay the history, answer for the
    next hour. The study loop above must agree with it step for step."""
    rets = check_series(closes, times)
    e = _Est(model)
    for r, t in zip(rets, times[1:]):
        e.push(t, r)
    if target_time is None:
        target_time = times[-1] + 3600
    return math.sqrt(e.var(target_time))


# --------------------------------------------------------------------------- #
# Synthetic controls (offline, seeded)
# --------------------------------------------------------------------------- #
#: A Monday 00:00 UTC, so weekday structure in the synthetic series is real.
SYNTH_START = 4 * 86400


def synth(sigma_of, scored: int = SYNTH_SCORED, seed: int = 1,
          start_price: float = 20_000.0) -> tuple[list[float], list[int]]:
    """Closes and times for hourly log-returns r ~ N(0, sigma_of(t)), t = the
    open time of the hour the return belongs to."""
    rng = random.Random(seed)
    closes, times = [start_price], [SYNTH_START]
    for _ in range(WARMUP + scored):
        t = times[-1] + 3600
        closes.append(closes[-1] * math.exp(rng.gauss(0.0, sigma_of(t))))
        times.append(t)
    return closes, times


def flat(t: int) -> float:
    return SYNTH_SIGMA


def planted_weekend(t: int, mult: float = 1.5) -> float:
    return SYNTH_SIGMA * (mult if is_weekend(t) else 1.0)


def planted_tuesday(t: int) -> float:
    return SYNTH_SIGMA * (2.0 if weekday(t) == 1 and 13 <= hour_of_day(t) <= 20 else 1.0)


def run_c1(seed: int = C1_SEED) -> dict:
    """Flat volatility: neither variant may beat B0 by >0.5% pooled or KEEP."""
    r = study_weekend(*synth(flat, seed=seed))
    q = r["pooled_qlike"]
    ok = (q["V1"] >= C1_FLOOR * q["B0"] and q["V2"] >= C1_FLOOR * q["B0"]
          and r["comparisons"]["V1_vs_B0"]["verdict"] != "KEEP"
          and r["comparisons"]["V2_vs_B0"]["verdict"] != "KEEP")
    return {"ok": ok, "pooled_qlike": q,
            "verdicts": {k: c["verdict"] for k, c in r["comparisons"].items()}}


def c1_size_check(seeds: int = C1_SIZE_SEEDS, first_seed: int = 1) -> dict:
    """Rejection rate of the one-sided test at SIGNIF_LEVEL on flat series, per variant."""
    rej = {"V1": 0, "V2": 0}
    for s in range(first_seed, first_seed + seeds):
        r = study_weekend(*synth(flat, seed=s))["comparisons"]
        for v in rej:
            c = r[f"{v}_vs_B0"]
            if c["p"] < SIGNIF_LEVEL and c["improvement"] > 0:
                rej[v] += 1
    limit = C1_SIZE_MAX_REJECTS * seeds / C1_SIZE_SEEDS
    return {"rejections": rej, "seeds": seeds, "limit": limit,
            "ok": all(x <= limit for x in rej.values())}


def run_c2() -> dict:
    """Planted weekend 1.5x: V1 must meet rule 3's I > 0, W >= 5, p < SIGNIF_LEVEL."""
    c = study_weekend(*synth(planted_weekend, seed=2))["comparisons"]["V1_vs_B0"]
    return {"ok": c["improvement"] > 0 and c["blocks_won"] >= KEEP_BLOCKS and c["p"] < SIGNIF_LEVEL,
            "comparison": c}


def run_c3() -> dict:
    """Planted Tuesday-only 13-20h UTC at 2x: V2 must KEEP, including vs B0L."""
    comps = study_weekend(*synth(planted_tuesday, seed=3))["comparisons"]
    return {"ok": comps["V2_vs_B0"]["verdict"] == "KEEP"
                  and comps["V2_vs_B0L"]["verdict"] == "KEEP",
            "verdicts": {k: c["verdict"] for k, c in comps.items()}}


def run_c4(seed: int = 4, every: int = 997) -> dict:
    """Equivalence and causality. The study path and the `forecast()`-style
    path give the same V1/V2 (and B0, B0L) sigma at origins across a run, to
    1e-12; B0 equals the shipped study's `ewma_diurnal`; perturbing the return
    at hour i leaves forecasts for hours <= i unchanged."""
    closes, times = synth(lambda t: planted_weekend(t, 1.5) * (2.0 if 13 <= hour_of_day(t) <= 20 else 1.0),
                          scored=1500, seed=seed)
    tr: dict = {}
    study_weekend(closes, times, trace=tr)
    failed: list[str] = []
    for m in MODELS:
        for k in range(0, len(tr[m]), every):
            i, s = tr[m][k]
            f = forecast_sigma(closes[:i + 1], times[:i + 1], m, target_time=times[i + 1])
            if not math.isclose(f, s, rel_tol=1e-12):
                failed.append(f"{m}: replay path differs at return {i}")
    shipped: list = []
    hv.study(closes, times, warmup=WARMUP, trace=shipped)
    if len(shipped) != len(tr["B0"]):
        failed.append("B0: scored-hour count differs from the shipped study")
    if not all(math.isclose(s, v, rel_tol=1e-12)
               for (_, v), (_, s) in zip(shipped, tr["B0"])):
        failed.append("B0: differs from the shipped ewma_diurnal")
    # causality: scale every close after index j, which changes only return j
    j = WARMUP + 700
    bumped = closes[:j + 1] + [c * 1.5 for c in closes[j + 1:]]
    tr2: dict = {}
    study_weekend(bumped, times, trace=tr2)
    for m in MODELS:
        if not all(a == b for (i, a), (_, b) in zip(tr[m], tr2[m]) if i <= j):
            failed.append(f"{m}: a later return changed an earlier forecast")
        if not any(a != b for (i, a), (_, b) in zip(tr[m], tr2[m]) if i > j):
            failed.append(f"{m}: the perturbation did not reach later forecasts")
    return {"ok": not failed, "failed": failed}


def power_simulation(seeds: int = POWER_SEEDS,
                     multipliers: tuple = POWER_MULTIPLIERS) -> dict:
    """Reported, non-gating: share of seeded series with a planted weekend
    sigma multiplier in which V1 beats B0 at SIGNIF_LEVEL (I > 0, p < SIGNIF_LEVEL). The
    study's resolving power, by simulation rather than hand arithmetic."""
    out = {}
    for m in multipliers:
        hits = 0
        for s in range(1, seeds + 1):
            c = study_weekend(*synth(lambda t, m=m: planted_weekend(t, m), seed=s)
                              )["comparisons"]["V1_vs_B0"]
            hits += c["improvement"] > 0 and c["p"] < SIGNIF_LEVEL
        out[m] = hits / seeds
    return {"detection_rate_v1_vs_b0": out, "seeds_each": seeds,
            "series": f"simulated, flat sigma {SYNTH_SIGMA} with a planted weekend "
                      f"multiplier, {WARMUP} + {SYNTH_SCORED} hours each",
            "scope": "simulated detection rates; not a result on real data, "
                     "forecast loss only; non-gating"}


def run_controls(size_check: bool = True) -> dict:
    """C1-C4 and, by default, the 200-seed C1 size check. The size check is
    part of the run gate (about 1.5-2 minutes of CPU); `size_check=False`
    exists for fast unit tests only and the runner never passes it."""
    res = {"C1": run_c1(), "C2": run_c2(), "C3": run_c3(), "C4": run_c4()}
    if size_check:
        res["C1_size"] = c1_size_check()
    else:
        res["C1_size"] = {"ok": False, "skipped": True}
    res["ok"] = all(v["ok"] for v in res.values())
    return res


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def spec_sha256(path: Path = SPEC_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_spec(path: Path = SPEC_PATH, approved: str | None = None) -> str:
    """Refuse to run unless the spec file is the one that was approved."""
    approved = APPROVED_SPEC_SHA256 if approved is None else approved
    approved = approved.strip().lower()
    actual = spec_sha256(path)
    if not approved:
        raise RuntimeError("no approved spec hash recorded; the study is not "
                           f"approved to run (spec sha256 now {actual})")
    if actual != approved:
        raise RuntimeError(f"spec differs from the approved file (approved "
                           f"{approved}, found {actual}); a changed number is a "
                           "new study with a new family")
    return actual


def module_sha256() -> str:
    """SHA-256 of this module's source: pins the code that produced a result
    (the spec hash pins only the pre-registration)."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


_HERE = Path(__file__).resolve().parent
CODE_FILES = (_HERE / "hourlyvol_weekend.py", _HERE / "hourlyvol.py", _HERE / "stats.py")


def code_sha256(paths: tuple | None = None) -> str:
    """SHA-256 over every source file a result depends on: this module,
    `hourlyvol.py` (models, fetch) and `stats.py` (HAC, bootstrap). File names
    are hashed with the bytes, in a fixed order, so a rename or a swap shows."""
    paths = paths or CODE_FILES
    h = hashlib.sha256()
    for p in paths:
        p = Path(p)
        h.update(p.name.encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def check_fresh(times: list[int], now: float, days: int = FETCH_DAYS) -> None:
    """Refuse a stale or short pull. `fetch_hourly` asks for bars from
    now - days*86400 and drops the in-progress hour, so a complete pull ends at
    the open time of the last closed hour (floor(now to the hour) - 3600) and
    starts within one hour after the requested start. Anything else (a cached
    or truncated answer) is not scored."""
    if not times:
        raise ValueError("no bars returned")
    last_closed = int(now) // 3600 * 3600 - 3600
    if times[-1] != last_closed:
        raise ValueError(f"stale history: last bar {iso_utc(times[-1])}, expected "
                         f"the last closed hour {iso_utc(last_closed)}")
    if times[0] > int(now) - days * 86400 + 3600:
        raise ValueError(f"short history: first bar {iso_utc(times[0])} is later "
                         f"than the requested {days}-day span allows")


def iso_utc(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _arg(argv: list[str], flag: str) -> str:
    if flag in argv and argv.index(flag) + 1 < len(argv):
        return argv[argv.index(flag) + 1]
    return ""


def main(argv: list[str] | None = None, now: float | None = None) -> int:
    """Run the study. Cost: the controls including the 200-seed size check take
    about 2-3 minutes of CPU, the power table (skip with `--skip-power`,
    non-gating) about 1.5 more, then one network pull of ~18 requests. Any
    re-run is a new run and should be logged by the owner. `now` (epoch
    seconds) is injectable for tests; it defaults to the clock after the pull."""
    argv = sys.argv[1:] if argv is None else argv
    if "--print-spec-hash" in argv:
        print(spec_sha256())
        return 0
    spec_hash = check_spec()
    print(f"spec sha256 {spec_hash} (matches the approved file)")
    run_id = {"run_at": iso_utc(time.time()), "module_sha256": module_sha256(),
              "code_sha256": code_sha256(),
              "approving_commit": (_arg(argv, "--approving-commit")
                                   or APPROVED_SPEC_COMMIT or "not supplied"),
              "note": "any re-run is a new run and must be logged"}
    print("controls (incl. 200-seed size check, a few minutes)...", flush=True)
    controls = run_controls()
    controls["scope"] = "simulated controls on synthetic series; gate for the run"
    if not controls["ok"]:
        out = {"spec_sha256": spec_hash, "run": run_id, "controls": controls,
               "verdict": "NOT RUN", "verdict_meaning": VERDICT_MEANING}
        print(json.dumps(out, indent=2, default=str))
        return 1
    times, closes = hv.fetch_hourly("BTCUSDT", FETCH_DAYS)
    try:
        check_fresh(times, time.time() if now is None else now, FETCH_DAYS)
        check_series(closes, times)
    except ValueError as exc:
        print(json.dumps({"spec_sha256": spec_hash, "run": run_id,
                          "verdict": "NOT RUN", "reason": str(exc),
                          "verdict_meaning": VERDICT_MEANING}, indent=2))
        return 1
    provenance = {"endpoint": hv._KLINES.split("?")[0], "symbol": "BTCUSDT",
                  "interval": "1h, UTC bar boundaries",
                  "first_bar": times[0], "last_bar": times[-1],
                  "period": f"{iso_utc(times[0])} to {iso_utc(times[-1])}",
                  "bars": len(times), "series_sha256": series_hash(times, closes)}
    result = study_weekend(closes, times, controls_ok=True, context=True)
    out = {"spec_sha256": spec_hash, "run": run_id, "provenance": provenance,
           "controls": controls, "result": result}
    print(json.dumps(out, indent=2, default=str), flush=True)
    if "--skip-power" not in argv:
        extra = {"non_gating": "power simulation; not part of the verdict"}
        try:
            extra["power_v1"] = power_simulation()
        except Exception as exc:          # the core result is already out
            extra["power_v1_error"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(extra, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
