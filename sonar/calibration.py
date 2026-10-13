"""Does a high score actually win more often?

Every other number in SONAR is a claim. This module is the only thing that
checks them, and it is the difference between a screener and a horoscope.

The method is deliberately dull. Every closed paper position carries the
confidence it was opened on and the probability of profit that was advertised
at the time. Bucket them by score, count how many actually won, and compare:

* **hit rate rising across buckets** — the score carries information.
* **flat** — the score is decoration. It ranks things, but not by anything real.
* **inverted** — the score is worse than useless and should be traded against.

It is a report, never an input. It used to invert the barrier maths into a
"drift" and move every row's ``P(profit)`` with it once twenty positions had
closed. Removed (owner decision, 2026-10-10) after an independent validation
(``docs/audit/model-validation.md``, ``docs/specs/t1-1-calibration-gate.md``):
protocol entries take a coin-flip direction, so a pooled hit rate above the
baseline reflects barrier and jump geometry — a driftless walk watched at
discrete marks already lands at 40.6–41.3% — not a drift a LONG plan could
use; and a gate re-checked after every close trips on a book with no edge
23–37% of the time. :func:`implied_edge` inverts the *untimed* barrier
maths and has no production caller left: the backtest's implied drift now
inverts its own time-aware baseline (docs/adr/0001). It stays as the
reference that inversion reproduces for untimed trials.

The gates that matter
---------------------
Below :data:`MIN_SAMPLE` graded trades a bucket reports *nothing*. Twelve
resolved positions cannot distinguish skill from a coin, and the temptation to
read a trend into them is exactly how a paper portfolio starts lying. An empty
calibration table is the honest state for a young install, and it says so.

Twenty is enough to *describe* the book. Saying it beat its odds takes a
hit rate whose interval at three standard errors (:data:`Z_CLAIM`) leaves out
the odds the plans advertised — three, not two, because the question is asked
again after every close, and at two a book with no edge eventually "beats its
odds" a quarter to a third of the time.

Only positions that reached a barrier are graded. ``P(profit)`` is the chance
of touching the target before the stop; a position closed by hand while in
profit never touched its target, and counting it as a win (it used to be, on
the sign of its P&L) graded the score on something it does not claim.

A second grade, beside this one
-------------------------------
Grading closed positions only lets the score decide what gets graded: how long
a position takes to close depends on its score, and the slow ones are still
open. :func:`shadow_time_stop` gives every protocol entry the result it would
have had under a time stop at entry + T, marked to the daily close
(docs/adr/0002). It is a readout like :func:`report` — it writes nothing and
changes no exit, no ``GRADED``, no ``Z_CLAIM`` and no ``P(profit)``. What it
decides is recorded once, by the engine, in a write-once ledger (ADR 0002
Amendment 1); the functions that read, check and extend that record are pure
and live here too.
"""

from __future__ import annotations

import bisect
import copy
import itertools
import json
import math
import time
import uuid
from dataclasses import dataclass

from . import horizon, scoring

# Below this, a bucket reports "insufficient data" rather than a hit rate.
# Not a statistical bound so much as a decency threshold: at n=20 the standard
# error on a coin flip is still ~11 points, and the UI says as much.
MIN_SAMPLE = 20

BUCKETS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
GRADED = ("TARGET", "STOP")      # the outcomes P(profit) is a claim about
Z95 = 1.96
Z_CLAIM = 3.0         # re-checked after every close: see the module docstring


def wilson(hits: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """The Wilson score interval for a hit rate: honest at small n and near
    0 or 1, where the plain ±z·se interval spills outside [0, 1]."""
    if n <= 0:
        return None
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = (z / (1 + z * z / n)) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def graded(closed: list) -> list:
    """Positions that reached a barrier — the only ones P(profit) predicts."""
    return [p for p in closed if p.pnl is not None and p.outcome in GRADED]


@dataclass
class Bucket:
    lo: int
    hi: int
    n: int
    wins: int
    expected: float          # what the barrier maths advertised, averaged
    pnl: float

    @property
    def enough(self) -> bool:
        return self.n >= MIN_SAMPLE

    @property
    def hit_rate(self) -> float | None:
        return self.wins / self.n if self.n else None

    @property
    def surprise(self) -> float | None:
        """Realised minus advertised. Positive means it beat its own odds."""
        hr = self.hit_rate
        return None if hr is None else hr - self.expected

    def as_dict(self) -> dict:
        return {"lo": self.lo, "hi": self.hi, "n": self.n, "wins": self.wins,
                "hit_rate": self.hit_rate, "expected": round(self.expected, 4),
                "surprise": self.surprise, "pnl": round(self.pnl, 2),
                "enough": self.enough}


def implied_edge(hit_rate: float, k_target: float = scoring.K_TARGET,
                 k_stop: float = scoring.K_STOP) -> float:
    """Recover the drift (in horizon-sigmas) implied by a realised hit rate.

    Inverts :func:`scoring.barrier_probability`. There is no closed form, so
    bisect — the function is monotonic in the drift, which makes that exact
    enough and completely robust.
    """
    baseline = k_stop / (k_target + k_stop)
    if hit_rate <= 0.0:
        return -10.0
    if hit_rate >= 1.0:
        return 10.0
    if abs(hit_rate - baseline) < 1e-9:
        return 0.0
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if scoring.barrier_probability(k_target, k_stop, mid) < hit_rate:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def buckets(closed: list) -> list[Bucket]:
    """Bucket resolved positions by the confidence they were opened on."""
    out = []
    done = graded(closed)
    for lo, hi in BUCKETS:
        rows = [p for p in done if lo <= (p.confidence or 0) < hi]
        wins = sum(1 for p in rows if p.outcome == "TARGET")
        expected = (sum(p.p_profit for p in rows) / len(rows)) if rows else 0.0
        out.append(Bucket(lo=lo, hi=hi, n=len(rows), wins=wins,
                          expected=expected,
                          pnl=sum(p.pnl or 0.0 for p in rows)))
    return out


def report(closed: list) -> dict:
    """The whole picture: buckets, whether the score ranks, and the edge earned."""
    bs = buckets(closed)
    settled = graded(closed)
    n_manual = sum(1 for p in closed if p.pnl is not None and p.outcome not in GRADED)

    overall_hits = sum(1 for p in settled if p.outcome == "TARGET")
    overall_rate = overall_hits / len(settled) if settled else None
    advertised = (sum(p.p_profit for p in settled) / len(settled)) if settled else None
    interval = wilson(overall_hits, len(settled))           # shown: the 95% range
    strict = wilson(overall_hits, len(settled), Z_CLAIM)    # what a claim needs

    enough = len(settled) >= MIN_SAMPLE
    beyond_noise = bool(enough and strict and advertised is not None
                        and not strict[0] <= advertised <= strict[1])

    # The ranking question, asked of every position rather than of bucket
    # averages: the rank correlation between the confidence a position was
    # opened on and whether it won. None when every position carried the same
    # score — a real state on a book traded off one setup, not an error.
    ic = None
    if enough:
        from .research import stats as _stats
        ic = _stats.spearman(
            [float(p.confidence or 0.0) for p in settled],
            [1.0 if p.outcome == "TARGET" else 0.0 for p in settled])

    return {
        "n_settled": len(settled),
        "n_manual": n_manual,
        "min_sample": MIN_SAMPLE,
        "enough": enough,
        "hit_rate_ci": None if interval is None else [round(v, 4) for v in interval],
        "buckets": [b.as_dict() for b in bs],
        "overall_hit_rate": overall_rate,
        "advertised_rate": advertised,
        "beyond_noise": beyond_noise,
        "score_ic": None if ic is None else round(ic, 4),
        "verdict": _verdict(enough, overall_rate, advertised, ic,
                            len(settled), interval, beyond_noise),
    }


def _verdict(enough: bool, overall: float | None,
             advertised: float | None, ic: float | None, n: int,
             interval: tuple[float, float] | None = None,
             beyond_noise: bool = False) -> str:
    if not enough:
        return ("Not enough resolved positions yet — no claim either way. "
                f"The score stays unproven until {MIN_SAMPLE} have closed.")
    # The verdict used to demand a strictly rising hit rate across every
    # bucket, which noise almost always breaks even when a real gradient
    # exists — five buckets of twenty each must never wobble once. A rank
    # correlation over the positions themselves asks the same question with
    # all the data and an error bar.
    if ic is not None:
        t = ic * math.sqrt(max(n - 1, 1))
        if t > Z_CLAIM:
            return (f"Higher scores have won more often (rank IC {ic:+.2f}, "
                    f"{t:.1f} sigma) — the score is carrying information.")
        if t < -Z_CLAIM:
            return (f"Hit rate *falls* as the score rises (rank IC {ic:+.2f}, "
                    f"{t:.1f} sigma). The score is worse than useless at "
                    "ranking these setups.")
    if overall is not None and advertised is not None:
        delta = overall - advertised
        if abs(delta) < 0.05:
            return ("Results match the advertised odds almost exactly, which is "
                    "what no edge looks like.")
        if not beyond_noise and interval is not None:
            return (f"Realised hit rate is {delta*100:+.1f} points against its own "
                    f"odds, but the 95% range ({interval[0]*100:.0f}–{interval[1]*100:.0f}%) "
                    f"still includes the {advertised*100:.0f}% promised — within noise.")
        return (f'Realised hit rate is {delta*100:+.1f} points against its own '
                "odds, outside the noise, without the score itself showing "
                "ranking power yet.")
    return "Insufficient data."


# --------------------------------------------------------------------------- #
# The time-stop shadow (docs/adr/0002)
# --------------------------------------------------------------------------- #
# Every protocol entry gets an outcome by a fixed date, so the score cannot
# decide which entries are graded. The rules are ADR 0002 §4, in order:
#
# 1. **Barrier.** Closed at TARGET or STOP before the cut keeps that outcome.
# 2. **Gap.** Otherwise a daily close after entry, up to the T bar, at or
#    beyond a barrier is that barrier (the polls missed it; counted).
# 3. **Time.** Otherwise the T bar's close, once that bar is final.
# 4. **Waiting.** Otherwise not yet.
#
# The *T bar* is the last daily bar stamped at or before t_T = opened_at + T.
# Yahoo stamps a bar at its session's start, and the newest one can still be
# trading, so the T bar counts only once a later bar exists; that later bar's
# stamp is the cut. R is the result in units of the initial risk,
# d·(exit − entry)/|entry − stop|: +R:R at the target, −1 at the stop. With no
# edge its mean is 0 whatever σ̂ got wrong (optional stopping), which is why
# the gate is on R and not on a hit rate.
#
# Pre-registered: T, the looks and the boundary are frozen here and pinned by a
# test. Changing one needs a new ADR and starts new cohorts.

SHADOW_T_HORIZONS = 4             # T = 4 horizons of the entry's preset (ADR 0001's cap)
SHADOW_LOOKS = (45, 101, 201)     # cohorts: the first N protocol entries by opened_at
# Pocock: |z| ≥ this at any look. Nominal 5% (Pocock); measured ~6% at these
# sizes (V-12), accepted by the owner 2026-10-12.
SHADOW_BOUNDARY = 2.315
# Past t_T with no final close an entry waits, and holds its looks, until both
# limits have passed: this many days since t_T, and fetches on SHADOW_PRICE_TRIES
# distinct UTC days, each at least SHADOW_TRY_AFTER_DAYS after t_T, that could
# not decide it. Only then is it left out as "no price" (Amendment 1 §4). The
# days are counted in the ledger, so a holder that was off for weeks cannot
# finalise an entry on the one failed fetch after its restart (validator P2-5).
SHADOW_PRICE_GRACE_DAYS = 28
SHADOW_PRICE_TRIES = 3
SHADOW_TRY_AFTER_DAYS = 7
# A look evaluated with k members left out for want of a result is also scored
# with each of them filled in at its own barriers: at every one of the 2^k
# combinations up to this k, and above it at the two that are the slope's
# exact extremes (validator Q1b).
SHADOW_VERTEX_K_MAX = 12
SHADOW_RULES = 1                  # the rules' version, stored with the ledger's constants
# A series whose last close at or before the entry is more than this many
# *daily* σ from the entry price is not that entry's price history: Yahoo
# split-adjusts old closes after the fact, so a split after the entry rescales
# everything before it (security P2-2, code review P2-1). The plan's stop
# distance is one horizon-σ = daily σ × √momentum_days, so one daily σ is
# |entry − stop| / √momentum_days, the same yardstick on every preset (fix
# loop 2, code review P2-A: in stop distances the bound grew to 31 daily σ on
# the year preset and let 2:1 splits through). The entry is at most a session
# from that close, so 4.5 daily σ (the week preset's old 2 stop distances)
# needs a rare gap to false-alarm, and a false alarm is counted, never
# guessed. It catches a 2:1 split below ~11% daily σ and a 3:2 split below
# ~7%, on any preset; a ratio band such as [0.5, 2] would let 3:2 through.
SHADOW_SPLIT_GUARD = 4.5
SHADOW_CRYPTO = "Crypto"          # the asset class that trades on all seven days
DAY_S = 86_400.0

#: An entry's state in the shadow. The first three are graded; the next two
#: are not yet; the last three are exclusions, counted and shown.
SHADOW_GRADED = ("target", "stop", "time")
SHADOW_PENDING = ("waiting", "wait_price")
SHADOW_EXCLUDED = ("left", "no_price", "no_risk")
#: Exclusions selected by the outcome, filled in at their barriers for the
#: extremes. ``no_risk`` has no R and is decided at fill, so it stays out.
SHADOW_FILLED = ("left", "no_price")
#: Settled for good, and written to the ledger. "No price" is final only
#: relative to a look: closes may still come, and a later look may count it.
SHADOW_FINAL = SHADOW_GRADED + ("left", "no_risk")
#: Where an outcome came from: rule 1 (``book``), rule 2 (``gap``), rule 3
#: (``bar``), a hand close (``hand``) or the fill itself (``fill``, no_risk).
SHADOW_SOURCES = ("book", "gap", "bar", "hand", "fill")


def shadow_t_days(preset: str | None) -> float:
    """T in calendar days: 4 × ``momentum_days`` × 7/5 — 28 on the week
    preset, 5.6 intraday, 112 month, 336 quarter, 1,400 year (ADR §1)."""
    return SHADOW_T_HORIZONS * horizon.get(preset).momentum_days * 7 / 5


def shadow_due(p) -> float:
    """t_T: the moment an entry reaches its fixed date."""
    return p.opened_at + shadow_t_days(p.horizon) * DAY_S


def shadow_reference_horizons(p) -> float:
    """Horizons inside T for the no-edge reference: bars in the window over
    bars per horizon. Weekday instruments see 4; crypto, whose daily bars run
    all week, sees 4 × 7/5 = 5.6 (ADR §1)."""
    if p.asset_class == SHADOW_CRYPTO:
        return SHADOW_T_HORIZONS * 7 / 5
    return float(SHADOW_T_HORIZONS)


def shadow_needs_bars(p, now: float) -> bool:
    """Whether an entry's outcome waits on daily closes: a filled protocol
    entry past t_T that the book did not already settle at or before t_T. The
    engine fetches only for these; a barrier hit before T needs no price, and
    an entry with no stop distance (``no_risk``) needs none at all."""
    if not p.protocol or p.pending or not _shadow_risk(p) > 0:
        return False
    t_due = shadow_due(p)
    if now < t_due:
        return False
    return p.closed_at is None or p.closed_at > t_due


def _shadow_risk(p) -> float:
    """The signed stop distance d·(entry − stop): positive when the stop sits
    on the losing side of the fill. Zero or less means a fill at or beyond the
    stop, where R is undefined or the barriers are inverted (validator P2-4:
    ``abs()`` hid the second case)."""
    d = 1.0 if p.direction == "LONG" else -1.0
    return d * (p.entry - p.stop)


def _utc_day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def hc3_z(x: list[float], y: list[float]) -> float | None:
    """z of the OLS slope of ``y`` on ``x`` with an HC3 (heteroscedasticity-
    robust) standard error — the shadow's gate statistic (ADR §3). The same
    sum as ``hc3_z`` in docs/specs/shadow-time-stop-sims.py; None, never NaN
    or infinity, when the slope or its error is undefined (fewer than three
    points, one score for all, or a perfect fit), because it goes into JSON."""
    n = len(x)
    if n < 3 or len(y) != n:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx <= 0:
        return None
    b = sum((a - mx) * (c - my) for a, c in zip(x, y, strict=True)) / sxx
    a0 = my - b * mx
    v = 0.0
    for xi, yi in zip(x, y, strict=True):
        e = yi - a0 - b * xi
        h = 1 / n + (xi - mx) ** 2 / sxx
        if h >= 1.0:
            return None
        v += (xi - mx) ** 2 * e * e / (1 - h) ** 2
    if not v > 0:
        return None
    z = b / math.sqrt(v / sxx ** 2)
    return z if math.isfinite(z) else None


def _hc3_z_at(x: list[float]):
    """:func:`hc3_z` for one fixed ``x`` and many ``y``: the parts that depend
    on ``x`` alone are worked out once. The same sums in the same order, so
    each value equals ``hc3_z(x, y)`` exactly. Returns a function of ``y``."""
    n = len(x)
    mx = sum(x) / n if n else 0.0
    dx = [a - mx for a in x]
    sxx = sum(d ** 2 for d in dx)
    if n < 3 or sxx <= 0:
        return lambda y: None
    h = [1 / n + d ** 2 / sxx for d in dx]
    if any(v >= 1.0 for v in h):
        return lambda y: None
    dx2 = [d ** 2 for d in dx]
    omh2 = [(1 - v) ** 2 for v in h]

    def z_of(y: list[float]) -> float | None:
        my = sum(y) / n
        b = sum(d * (c - my) for d, c in zip(dx, y, strict=True)) / sxx
        a0 = my - b * mx
        v = 0.0
        for i, (xi, yi) in enumerate(zip(x, y, strict=True)):
            e = yi - a0 - b * xi
            v += dx2[i] * e * e / omh2[i]
        if not v > 0:
            return None
        z = b / math.sqrt(v / sxx ** 2)
        return z if math.isfinite(z) else None
    return z_of


def extreme_z(members: list[dict]) -> tuple[float | None, float | None, str | None]:
    """The z of a look with its outcome-selected exclusions filled in at the
    extremes (Amendment 1 §3): ``(z_lo, z_hi, method)``.

    Each ``left`` or ``no_price`` member is put at its own R at the stop and
    its own R at the target — both known at fill, and −1 and +R:R only when
    the fill was the planned entry (domain P2-2, validator P3-1). With k ≤
    :data:`SHADOW_VERTEX_K_MAX` such members, z is worked out at all 2^k
    combinations (``"vertices"``); above that, at the two that are the
    slope's exact extremes — members scored above the mean confidence of the
    regression's members at the top and the rest at the bottom, then the
    reverse (``"slopes"``). The far ends are extreme cases, not a bound on z:
    a point inside can lie beyond them (validator Q1a). The end that decides
    a crossing is always at a combination, which is what the rule needs.

    ``(None, None, None)`` when nothing is filled in; ``(None, None, method)``
    when a member's barriers are unknown or a combination has no z — never a
    guess, and then no crossing can count as robust."""
    used = [e for e in members if e["state"] in SHADOW_GRADED]
    filled = [e for e in members if e["state"] in SHADOW_FILLED]
    if not filled:
        return None, None, None
    method = "vertices" if len(filled) <= SHADOW_VERTEX_K_MAX else "slopes"
    bounds = []
    for e in filled:
        a, b = e.get("r_stop"), e.get("r_target")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and math.isfinite(v) for v in (a, b)):
            return None, None, method
        bounds.append((min(a, b), max(a, b)))
    xs = [e["confidence"] for e in used] + [e["confidence"] for e in filled]
    base = [e["r"] for e in used]
    z_of = _hc3_z_at(xs)
    if method == "vertices":
        fills = itertools.product(*bounds)
    else:
        mx = sum(xs) / len(xs)
        high = [e["confidence"] > mx for e in filled]
        fills = ([hi if up else lo for (lo, hi), up in zip(bounds, high, strict=True)],
                 [lo if up else hi for (lo, hi), up in zip(bounds, high, strict=True)])
    zs = [z_of(base + list(f)) for f in fills]
    if any(z is None for z in zs):
        return None, None, method
    return min(zs), max(zs), method


def _shadow_newest_is_a_session_start(series: list[tuple[float, float]]) -> bool:
    """Whether the newest bar's stamp has the series' session-start pattern:
    the same time of day as the bar before it. Yahoo stamps a day bar at its
    session's start (ADR §5), but an in-progress bar can carry the fetch time
    (EURCHF=X `11:17`, code review P1-2), and a finished newest bar fetched
    over a weekend is not verified to keep its session start (code review r3
    P2-1): a last-trade or fetch-time stamp breaks the pattern."""
    return len(series) >= 2 and (series[-1][0] - series[-2][0]) % DAY_S == 0


def _shadow_from_bars(p, series: list[tuple[float, float]] | None, t_due: float,
                      booked: str | None) -> tuple | None:
    """Rules 1–3 for an entry past t_T, from its symbol's daily bars. Returns
    ``(state, exit price, gap, source, t_bar, t_cut)`` — the T bar's stamp and
    the cut are kept for the record — or None when the bars cannot decide
    yet: no series, one that does not reach back to the entry, no bar after
    the entry up to t_T, or no later bar to show the T bar is finished.

    The newest bar's close is never used: it may still be trading. Its stamp
    is used — as the cut, the start of the session after the T bar — only
    when it has the session-start pattern
    (:func:`_shadow_newest_is_a_session_start`); then it is exact whatever its
    age. Otherwise the bar is dropped, so a stamp that is a fetch time or a
    last trade can neither pick the T bar nor serve as the cut (code review
    P1-2, r3 P2-1). A DST change or a shifted FX stamp breaks the pattern for
    a day, which costs a day of waiting and nothing else.

    Measured, US-session bars and one fetch a day at 00:01 UTC
    (`test_r2_latency_*`): a T on Monday–Thursday is decided 1.4 days after
    t_T, a Friday T 3.4 days after; a holiday can add up to two days (a
    Thursday T before a Friday holiday: 4.4), and a first pass later than
    00:01 adds its delay (07:00: 4.7). The grace before "no price" is 28 days
    (it was 7, with as little as 2.3 days to spare)."""
    series = list(series or [])
    if series and not _shadow_newest_is_a_session_start(series):
        series.pop()
    if not series:
        return None
    stamps = [t for t, _c in series]
    if stamps[0] > p.opened_at:
        return None                          # too short a range to check for gaps
    before = series[bisect.bisect_right(stamps, p.opened_at) - 1][1]
    daily_sigma = abs(p.entry - p.stop) / math.sqrt(horizon.get(p.horizon).momentum_days)
    if abs(before - p.entry) > SHADOW_SPLIT_GUARD * daily_sigma:
        return None                          # rescaled (a split?) or wrong: not this price
    i = bisect.bisect_right(stamps, t_due) - 1     # the T bar: never the next one
    # A later bar must exist; the newest may be it (its stamp only, never its close).
    if i < 0 or stamps[i] <= p.opened_at or i + 1 >= len(series):
        return None
    t_bar, t_cut = stamps[i], stamps[i + 1]
    if booked is not None and p.closed_at < t_cut:
        if booked in GRADED:
            return (booked.lower(), (p.target if booked == "TARGET" else p.stop), False,
                    "book", t_bar, t_cut)
        return "left", None, False, "hand", t_bar, t_cut
    # A bar's close comes at its session's end. Only bars that *start* after
    # the entry are certainly closed after it: the entry day's own close may
    # predate the entry, and the live polls watched that session anyway.
    for j in range(bisect.bisect_right(stamps, p.opened_at), i + 1):
        hit = p.hit(series[j][1])
        if hit:
            return (hit.lower(), (p.target if hit == "TARGET" else p.stop), True,
                    "gap", t_bar, t_cut)
    return "time", series[i][1], False, "bar", t_bar, t_cut


def shadow_decided(result: dict) -> dict[str, dict]:
    """The entries of a readout whose outcome is settled for good — graded
    (barrier, gap, or TIME on a final T bar), left out by a hand close, or
    left out at fill for want of a stop distance — by position id. The engine
    keeps these in memory and hands them back, so an outcome once decided
    cannot change within the process: not when a fetch fails, and not when
    the provider rewrites old closes (code review P1-1, P2-1). The same
    entries go into the ledger, which carries them across restarts
    (Amendment 1). "No price" is not settled: closes may still come."""
    return {e["id"]: e for e in result.get("entries", ()) if e["state"] in SHADOW_FINAL}


def _shadow_entry(p, series, now: float, tries=(),
                  fetched: bool = False) -> tuple[dict, list[str]]:
    """One protocol entry's shadow outcome, and the UTC days on which a fetch
    for it could not decide it (``tries``, with today's added when
    ``fetched`` says this pass asked for its symbol). Reads the position;
    never writes it."""
    t_due = shadow_due(p)
    booked = p.outcome if p.closed_at is not None else None
    state, exit_price, gap, source, t_bar, t_cut = "waiting", None, False, None, None, None
    # Only days a fetch could count on: at or after t_T + 7 days.
    first = _utc_day(t_due + SHADOW_TRY_AFTER_DAYS * DAY_S)
    tried = sorted({d for d in tries if d >= first})
    risk = _shadow_risk(p)
    if not risk > 0:
        # At or past its stop at fill: no R can be worked out. Known at fill,
        # so final at once, whatever the outcome (Amendment 1 §4).
        state, source = "no_risk", "fill"
    elif booked is not None and p.closed_at <= t_due:
        # Settled by the book before T: final, and needs no price. Graded only
        # from t_T on, like every other entry, so the running figures never
        # lean on the quick resolvers the closed-only grade leans on.
        if booked not in GRADED:
            state, source = "left", "hand"
        elif now >= t_due:
            state, source = booked.lower(), "book"
            exit_price = p.target if booked == "TARGET" else p.stop
    elif now >= t_due:
        got = _shadow_from_bars(p, series, t_due, booked)
        if got is not None:
            state, exit_price, gap, source, t_bar, t_cut = got
        else:
            if fetched and now >= t_due + SHADOW_TRY_AFTER_DAYS * DAY_S:
                tried = sorted(set(tried) | {_utc_day(now)})
            if (now >= t_due + SHADOW_PRICE_GRACE_DAYS * DAY_S
                    and len(tried) >= SHADOW_PRICE_TRIES):
                state = "no_price"
            else:
                state = "wait_price"
    r = r_stop = r_target = None
    if risk > 0:
        d = 1.0 if p.direction == "LONG" else -1.0
        # Each entry's own barriers in R: −1 and +R:R only when the fill was
        # the planned entry (domain P2-2). The extremes use these.
        r_stop = d * (p.stop - p.entry) / risk
        r_target = d * (p.target - p.entry) / risk
        if exit_price is not None:
            r = d * (exit_price - p.entry) / risk
    ref_t, ref_s = scoring.barrier_probabilities_within(
        p.rr, 1.0, shadow_reference_horizons(p))
    entry = {"id": p.id, "symbol": p.symbol, "direction": p.direction,
             "confidence": float(p.confidence or 0.0), "opened_at": p.opened_at,
             "t_due": t_due, "t_days": shadow_t_days(p.horizon), "rr": p.rr,
             "booked": booked, "state": state, "exit": exit_price, "r": r, "gap": gap,
             "ref": [ref_t, ref_s], "source": source, "entry": p.entry, "stop": p.stop,
             "target": p.target, "r_stop": r_stop, "r_target": r_target,
             "closed_at": p.closed_at, "t_bar": t_bar, "t_cut": t_cut}
    return entry, (tried if state in ("wait_price", "no_price") else [])


def _order(entries: list[dict]) -> list[dict]:
    """Entry order: the cohorts are the first N of it."""
    return sorted(entries, key=lambda e: (e["opened_at"], e["id"]))


def _member(e: dict) -> dict:
    """A look member as the ledger records it."""
    return {"id": e["id"], "state": e["state"], "r": e["r"],
            "confidence": e["confidence"], "r_stop": e.get("r_stop"),
            "r_target": e.get("r_target")}


def shadow_looks(entries: list[dict], recorded: dict | None = None) -> list[dict]:
    """The three pre-registered looks (ADR §3, Amendment 1).

    A cohort is the first N entries by ``opened_at`` — membership by entry
    order, never by resolution, so a look cannot re-select quick resolvers.
    A look is evaluated once every member has an outcome or a final exclusion,
    and its value depends on its members alone. |z| ≥ :data:`SHADOW_BOUNDARY`
    crosses — with members left out for want of a result, only when every
    extreme fill (:func:`extreme_z`) is past the line on the same side too.
    The first crossing is the result and closes the design, so no later look
    is evaluated.

    ``recorded`` is the ledger's ``looks``. A look found there is returned as
    recorded — its members, z, extremes and crossing — with ``recorded_at``,
    and a recorded crossing closes the design whatever today's members say.
    A look evaluated here and not recorded yet carries ``recorded: False``
    and its ``members``, for the ledger; it is not a result until recorded
    (S4).
    """
    order = _order(entries)
    recorded = recorded or {}
    out: list[dict] = []
    closed_at_look = None
    for k, n in enumerate(SHADOW_LOOKS, start=1):
        members = order[:n]
        graded = [e for e in members if e["state"] in SHADOW_GRADED]
        excluded = sum(1 for e in members if e["state"] in SHADOW_EXCLUDED)
        entered = len(members)
        final = entered == n and len(graded) + excluded == n
        waiting_price = [e["t_due"] for e in members if e["state"] == "wait_price"]
        look = {
            "k": k, "n": n, "entered": entered, "n_missing": n - entered,
            "due": max(e["t_due"] for e in members) if entered == n else None,
            "used": len(graded), "n_excluded": excluded,
            "n_filled": sum(1 for e in members if e["state"] in SHADOW_FILLED),
            "n_waiting": sum(1 for e in members if e["state"] == "waiting"),
            "n_wait_price": len(waiting_price),
            # The latest date a member waiting for a price can still hold it.
            "price_until": (max(waiting_price) + SHADOW_PRICE_GRACE_DAYS * DAY_S
                            if waiting_price else None),
            "design_closed": closed_at_look is not None,
            "recorded": False, "recorded_at": None,
        }
        rec = recorded.get(str(k))
        if rec is not None:
            z = rec["z"]
            look.update({
                "used": rec["used"], "n_excluded": rec["n_excluded"],
                "n_filled": sum(1 for m in rec["members"] if m["state"] in SHADOW_FILLED),
                "evaluated": True, "z": z, "z_lo": rec["z_lo"], "z_hi": rec["z_hi"],
                "method": rec["method"], "crossed": rec["crossed"],
                "past_line": z is not None and abs(z) >= SHADOW_BOUNDARY,
                "design_closed": rec["design_closed"],
                "recorded": True, "recorded_at": rec["evaluated_at"]})
        else:
            evaluated = final and closed_at_look is None
            z = (hc3_z([e["confidence"] for e in graded], [e["r"] for e in graded])
                 if evaluated else None)
            z_lo, z_hi, method = extreme_z(members) if evaluated else (None, None, None)
            past = bool(evaluated and z is not None and abs(z) >= SHADOW_BOUNDARY)
            # The robust rule (owner, G2 (a)): z and every fill past the line
            # on the same side. With nothing filled in it is z alone, as before.
            robust = past and (look["n_filled"] == 0 or (
                z_lo is not None and z_hi is not None
                and (z_lo >= SHADOW_BOUNDARY if z > 0 else z_hi <= -SHADOW_BOUNDARY)))
            look.update({"evaluated": evaluated, "z": z, "z_lo": z_lo, "z_hi": z_hi,
                         "method": method, "crossed": bool(past and robust),
                         "past_line": past})
            if evaluated:
                look["members"] = [_member(e) for e in members]
        out.append(look)
        if look["crossed"]:
            closed_at_look = k
    return out


def _one(values: list) -> float | None:
    """The value every entry shares, or None when they differ (or none exist)."""
    distinct = set(values)
    return distinct.pop() if len(distinct) == 1 else None


def _ref_split(rows: list[dict]) -> dict | None:
    """What no edge would give: the mean per-entry target / stop / neither
    split by T, from :func:`scoring.barrier_probabilities_within`."""
    if not rows:
        return None
    t = sum(e["ref"][0] for e in rows) / len(rows)
    s = sum(e["ref"][1] for e in rows) / len(rows)
    return {"target": t, "stop": s, "neither": max(0.0, 1.0 - t - s)}


def _split(rows: list[dict]) -> dict:
    return {"target": sum(1 for e in rows if e["state"] == "target"),
            "stop": sum(1 for e in rows if e["state"] == "stop"),
            "time": sum(1 for e in rows if e["state"] == "time")}


def shadow_time_stop(open, closed, bars, now: float,
                     decided: dict[str, dict] | None = None, ledger: dict | None = None,
                     tries: dict[str, list[str]] | None = None,
                     fetched=None) -> dict:
    """The time-stop shadow of the score grade, for every protocol entry.

    ``open`` and ``closed`` are :class:`sonar.portfolio.Position` lists (the
    engine passes copies); ``bars`` maps a symbol to its daily
    ``(timestamp, close)`` pairs as :func:`sonar.assets.fetch_bars` returns
    them. Pure: it reads its inputs and returns a new dict of plain numbers,
    ready for JSON. Pending orders are not positions and are skipped; manual
    entries are counted and never graded. Bars stamped after ``now`` are
    ignored: a future stamp would make an in-progress bar look final.

    ``decided`` is :func:`shadow_decided` of earlier readouts, and ``ledger``
    the parsed record (:func:`ledger_parse`), whose entries join it and win
    over it: an entry found in either keeps that outcome (deep-copied, never
    recomputed). Only an entry still protocol and filled is looked up, so the
    book stays the population; its ``booked`` outcome is refreshed from the
    position, so ``ic_closed`` reads the book as it is now (code review r2
    P3-1). The ledger's recorded looks are honoured (:func:`shadow_looks`)
    and checked (:func:`ledger_check`).

    ``tries`` maps an undecided entry's id to the UTC days a fetch could not
    decide it (the ledger's ``price_tries`` when None); ``fetched`` is the
    set of symbols this pass asked for today. Today counts as a try for an
    entry whose symbol is in it and that the closes still cannot decide; the
    readout's ``price_tries`` carries the days for the ledger.
    """
    from .research import stats as _stats

    series: dict[str, list[tuple[float, float]]] = {}
    for sym, rows in (bars or {}).items():
        clean = []
        for row in rows or ():
            # Row by row: one malformed bar drops that bar, never the readout.
            try:
                t, c = float(row[0]), float(row[1])
            except (TypeError, ValueError, OverflowError, IndexError):
                continue
            if math.isfinite(t) and math.isfinite(c) and c > 0 and t <= now:
                clean.append((t, c))
        series[sym] = sorted(clean)

    known = dict(decided or {})
    if ledger:
        # As the readout had it when decided: the record's own bookkeeping
        # (when, by which build) stays in the file.
        known.update({pid: {"id": pid, **{f: v for f, v in e.items()
                                          if f not in ("decided_at", "build")}}
                      for pid, e in ledger["entries"].items()})
        if tries is None:
            tries = ledger["price_tries"]
    tries = tries or {}
    fetched = set(fetched or ())
    entries: list[dict] = []
    price_tries: dict[str, list[str]] = {}
    n_nonprotocol = 0
    for p in list(open) + list(closed):
        if p.pending:
            continue
        if not p.protocol:
            n_nonprotocol += 1
            continue
        if p.id in known:
            kept = copy.deepcopy(known[p.id])
            kept["booked"] = p.outcome if p.closed_at is not None else None
            entries.append(kept)
            continue
        entry, tried = _shadow_entry(p, series.get(p.symbol), now, tries.get(p.id, ()),
                                     p.symbol in fetched)
        entries.append(entry)
        if tried:
            price_tries[p.id] = tried
    entries.sort(key=lambda e: (e["opened_at"], e["id"]))

    graded = [e for e in entries if e["state"] in SHADOW_GRADED]
    conf = [e["confidence"] for e in graded]
    rs = [e["r"] for e in graded]
    n = len(graded)
    mean_r = sum(rs) / n if n else None
    lo = hi = None
    if n >= 2:
        sd = math.sqrt(sum((v - mean_r) ** 2 for v in rs) / (n - 1))
        lo, hi = mean_r - Z95 * sd / math.sqrt(n), mean_r + Z95 * sd / math.sqrt(n)
    # report()'s statistic on the same entries: of those the book closed at a
    # barrier, confidence against TARGET = 1 / STOP = 0. Descriptive only.
    shut = [e for e in graded if e["booked"] in GRADED]
    ic_closed = _stats.spearman([e["confidence"] for e in shut],
                                [1.0 if e["booked"] == "TARGET" else 0.0 for e in shut])
    waiting = [e["t_due"] for e in entries if e["state"] == "waiting"]
    bands = []
    for b_lo, b_hi in BUCKETS:
        rows = [e for e in graded if b_lo <= e["confidence"] < b_hi]
        if rows:
            bands.append({"lo": b_lo, "hi": b_hi, "n": len(rows), **_split(rows),
                          "ref": _ref_split(rows)})
    split = _split(graded)
    return shadow_with_ledger({
        "n_entered": len(entries),
        "n_reached": n,
        "n_target": split["target"], "n_stop": split["stop"], "n_time": split["time"],
        "n_waiting": len(waiting),
        "next_t": min(waiting) if waiting else None,
        "n_wait_price": sum(1 for e in entries if e["state"] == "wait_price"),
        "n_nonprotocol": n_nonprotocol,
        "n_left": sum(1 for e in entries if e["state"] == "left"),
        "n_no_price": sum(1 for e in entries if e["state"] == "no_price"),
        "n_no_risk": sum(1 for e in entries if e["state"] == "no_risk"),
        "n_gap": sum(1 for e in graded if e["gap"]),
        "z": hc3_z(conf, rs),
        "ic": _stats.spearman(conf, rs),
        "ic_closed": ic_closed,
        "n_closed_same": len(shut),
        "mean_r": mean_r, "mean_r_lo": lo, "mean_r_hi": hi,
        "ref": _ref_split(graded),
        "t_days": _one([e["t_days"] for e in entries]),
        "rr": _one([e["rr"] for e in entries]),
        "boundary": SHADOW_BOUNDARY,
        "bands": bands,
        "entries": entries,
        "price_tries": price_tries,
        "computed_at": now,
        "error": None,
    }, ledger)


def shadow_with_ledger(result: dict, ledger: dict | None) -> dict:
    """A readout's looks, check and errata against ``ledger`` (None: no
    usable record, so no look is recorded). The engine calls it again once a
    write has added to the record, so the published looks are the recorded
    ones."""
    looks = shadow_looks(result["entries"], ledger["looks"] if ledger else None)
    return {**result, "looks": looks,
            "mismatches": ledger_check(ledger, result["entries"]),
            "errata": ledger_errata(ledger),
            "ledger": ({"created_at": ledger["created_at"], "error": None, "reason": None}
                       if ledger else None)}


# --------------------------------------------------------------------------- #
# The look ledger (docs/adr/0002 Amendment 1, docs/specs/shadow-ledger.md)
# --------------------------------------------------------------------------- #
# Each decided outcome and each evaluated look is written once, the first time
# it exists, and never rewritten: so "each look is evaluated once" holds across
# restarts, and a look shown as a result cannot change after it was shown. The
# engine reads and writes the file; these functions are pure. Only
# `price_tries` ever changes. `errata` is written by a person, under a written
# note, and only ever read here: an erratum is shown beside its look and never
# changes `crossed` or `design_closed`.

LEDGER_SCHEMA = 1
#: The fields of a recorded entry. Everything needed to audit its R.
LEDGER_ENTRY_FIELDS = ("state", "source", "r", "exit", "entry", "stop", "target", "r_stop",
                       "r_target", "direction", "symbol", "confidence", "rr", "opened_at",
                       "closed_at", "t_due", "t_days", "t_bar", "t_cut", "gap", "ref",
                       "decided_at", "build")
LEDGER_LOOK_FIELDS = ("k", "n", "evaluated_at", "build", "z", "z_lo", "z_hi", "method",
                      "crossed", "design_closed", "used", "n_excluded", "members")
LEDGER_MEMBER_FIELDS = ("id", "state", "r", "confidence", "r_stop", "r_target")
LEDGER_ERRATUM_FIELDS = ("id", "reason", "r", "date")
LEDGER_TEXT_MAX = 500             # a reason or a build tag; ids and symbols are shorter
LEDGER_ID_MAX = 64                # a position id or a symbol
LEDGER_ERRATA_MAX = 1_000         # far beyond any honest use; bounds every pass's work
LEDGER_METHODS = (None, "vertices", "slopes")


class LedgerFormatError(ValueError):
    """A ledger that is not the shape this build writes. The whole file is
    then unreadable: never read in part, never repaired."""


class LedgerIdError(LedgerFormatError):
    """A ledger that is not this book's: its id is not the one the book's
    marker or sidecar names, or, with neither, it records positions this book
    does not hold (another book's record, or one put back in place of this
    one)."""


class LedgerBehindError(LedgerFormatError):
    """A ledger with fewer recorded looks than the book's marker or the
    sidecar says it had: an older copy, from before a look was recorded.
    Entries are not counted: one lost with a newer copy is decided again
    from the closes then available, and is not part of any recorded look
    (each look keeps its own members); a recorded look cannot be redone."""


class LedgerRetiredError(LedgerIdError):
    """A ledger whose id was retired on purpose: a retired file in the data
    directory holds the same id. A copy of a record set aside is never used
    or written again (a copy left in place of a moved one)."""


def ledger_constants() -> dict:
    """What the record was made under: T per preset, the looks, the line,
    the grace, the split guard, the extremes' method and the rules' version.
    A ledger written under other constants shows a "constants" mismatch."""
    return {"rules": SHADOW_RULES, "t_horizons": SHADOW_T_HORIZONS,
            "t_days": {name: shadow_t_days(name) for name in horizon.HORIZONS},
            "looks": list(SHADOW_LOOKS), "boundary": SHADOW_BOUNDARY,
            "grace_days": SHADOW_PRICE_GRACE_DAYS, "grace_tries": SHADOW_PRICE_TRIES,
            "try_after_days": SHADOW_TRY_AFTER_DAYS, "split_guard": SHADOW_SPLIT_GUARD,
            "vertex_k_max": SHADOW_VERTEX_K_MAX}


def ledger_new(now: float, build: str, ledger_id: str | None = None,
               created_at: float | None = None) -> dict:
    """An empty ledger. ``ledger_id`` and ``created_at`` come from the marker
    when the file is being made for one already in ``portfolio.json``."""
    return {"schema": LEDGER_SCHEMA, "ledger_id": ledger_id or str(uuid.uuid4()),
            "created_at": now if created_at is None else created_at, "created_by": build,
            "constants": ledger_constants(), "entries": {}, "looks": {},
            "price_tries": {}, "errata": []}


def ledger_anchor(ledger: dict) -> dict:
    """What the book's marker and the sidecar say about the record: its id,
    when it began, and how many looks it held at the last write. The count
    only grows, so a file behind it is an older copy. Entries are not
    counted (code review r2 P2-N1): a lost entry is decided again from the
    closes then available, and is not part of any recorded look (each look
    keeps its own members; code review r3 P3-4). Counting them made the
    newest daily backup "behind" on any day that decided one."""
    return {"ledger_id": ledger["ledger_id"], "created_at": ledger["created_at"],
            "looks": len(ledger["looks"])}


def _is_num(v) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:           # an int too large for a float is no timestamp or R
        return False


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_text(v, limit: int = LEDGER_TEXT_MAX) -> bool:
    return isinstance(v, str) and 0 < len(v) <= limit


def _is_day(v) -> bool:
    if not isinstance(v, str) or len(v) != 10:
        return False
    try:
        return time.strftime("%Y-%m-%d", time.strptime(v, "%Y-%m-%d")) == v
    except ValueError:
        return False


def _is_uuid(v) -> bool:
    try:
        return isinstance(v, str) and str(uuid.UUID(v)) == v
    except ValueError:
        return False


def _need(ok: bool, where: str) -> None:
    if not ok:
        raise LedgerFormatError(where)


def _fields(d, names: tuple, where: str) -> None:
    _need(isinstance(d, dict) and set(d) == set(names), where)


def _opt_num(v) -> bool:
    return v is None or _is_num(v)


def _check_entry(pid, e) -> None:
    where = f"entry {pid!r}"
    _need(_is_text(pid, LEDGER_ID_MAX), where)
    _fields(e, LEDGER_ENTRY_FIELDS, where)
    _need(e["state"] in SHADOW_FINAL and e["source"] in SHADOW_SOURCES, where)
    _need(_is_num(e["r"]) if e["state"] in SHADOW_GRADED else e["r"] is None, where)
    _need(all(_is_num(e[f]) for f in ("entry", "stop", "target", "confidence", "rr",
                                       "opened_at", "t_due", "t_days", "decided_at")), where)
    _need(all(_opt_num(e[f]) for f in ("exit", "r_stop", "r_target", "closed_at", "t_bar",
                                        "t_cut")), where)
    _need(e["direction"] in ("LONG", "SHORT") and _is_text(e["symbol"], LEDGER_ID_MAX)
          and _is_text(e["build"]) and isinstance(e["gap"], bool), where)
    _need(isinstance(e["ref"], list) and len(e["ref"]) == 2
          and all(_is_num(v) for v in e["ref"]), where)


def _file_boundary(constants: dict) -> float:
    """The line the file was made under, when it holds a number; else
    today's. The reader and the merge both judge a look by it, so a changed
    module constant is a "constants" mismatch, not a read error (ADR §7)."""
    b = constants.get("boundary")
    return b if _is_num(b) else SHADOW_BOUNDARY


def _file_looks(constants: dict) -> tuple:
    """The look sizes the file was made under, when they are positive
    integers; else today's. See :func:`_file_boundary`."""
    v = constants.get("looks")
    ok = isinstance(v, list) and len(v) > 0 and all(_is_int(n) and n > 0 for n in v)
    return tuple(v) if ok else SHADOW_LOOKS


def _check_look(key, lk, boundary: float | None = None, looks: tuple | None = None) -> None:
    """One recorded look: its shape, and a verdict that follows from its own
    figures (security P3-7) — a cohort of the size its key says, and a
    crossing only past the line and, with members filled in, robust. The
    sizes and the line are the file's own (code review r2 P3-N1); without
    them, today's, read at the call."""
    boundary = SHADOW_BOUNDARY if boundary is None else boundary
    looks = SHADOW_LOOKS if looks is None else looks
    where = f"look {key!r}"
    _fields(lk, LEDGER_LOOK_FIELDS, where)
    _need(_is_int(lk["k"]) and str(lk["k"]) == key and 1 <= lk["k"] <= len(looks)
          and _is_int(lk["n"]) and lk["n"] == looks[lk["k"] - 1]
          and _is_int(lk["used"]) and _is_int(lk["n_excluded"]), where)
    _need(_is_num(lk["evaluated_at"]) and _is_text(lk["build"]), where)
    _need(all(_opt_num(lk[f]) for f in ("z", "z_lo", "z_hi")), where)
    _need(lk["method"] in LEDGER_METHODS and isinstance(lk["crossed"], bool)
          and lk["design_closed"] is False, where)
    _need(isinstance(lk["members"], list) and len(lk["members"]) == lk["n"]
          and lk["used"] + lk["n_excluded"] == lk["n"], where)
    filled = 0
    for m in lk["members"]:
        _fields(m, LEDGER_MEMBER_FIELDS, where)
        _need(_is_text(m["id"], LEDGER_ID_MAX)
              and m["state"] in SHADOW_GRADED + SHADOW_EXCLUDED, where)
        _need(_is_num(m["r"]) if m["state"] in SHADOW_GRADED else m["r"] is None, where)
        _need(_is_num(m["confidence"]) and _opt_num(m["r_stop"]) and _opt_num(m["r_target"]),
              where)
        filled += m["state"] in SHADOW_FILLED
    _need(sum(m["state"] in SHADOW_GRADED for m in lk["members"]) == lk["used"], where)
    if lk["crossed"]:
        z = lk["z"]
        _need(z is not None and abs(z) >= boundary, where)
        if filled:
            _need(lk["z_lo"] is not None and lk["z_hi"] is not None
                  and (lk["z_lo"] >= boundary if z > 0 else lk["z_hi"] <= -boundary), where)


def _check_looks_order(looks: dict) -> None:
    """No look is recorded after one that crossed: the first crossing closes
    the design."""
    crossed = False
    for key in sorted(looks, key=int):
        _need(not crossed, f"look {key!r} after a crossing")
        crossed = looks[key]["crossed"]


def _check_constants(c) -> None:
    """The constants as a typed mapping. Today's key set is not required: a
    key added or removed is a "constants" mismatch (ADR §7), not an
    unreadable file."""
    _need(isinstance(c, dict), "constants")
    for k, v in c.items():
        ok = _is_text(k, LEDGER_ID_MAX) and (
            _is_num(v)
            or (isinstance(v, list) and len(v) <= 100 and all(_is_num(x) for x in v))
            or (isinstance(v, dict) and len(v) <= 100
                and all(_is_text(a, LEDGER_ID_MAX) and _is_num(b) for a, b in v.items())))
        _need(ok, "constants")


def ledger_parse(raw) -> tuple[dict | None, str | None]:
    """The ledger in ``raw`` (the file's text), type-checked field by field:
    ``(ledger, None)``, or ``(None, reason)`` with the exception's class name.
    A wrong type anywhere, a missing or unknown key, or another schema is an
    error for the whole file, never a partial read. It is data only: no
    field is ever evaluated, and the one free text shown on screen (an
    erratum's reason) goes through the window's clamps."""
    try:
        d = json.loads(raw, parse_constant=_no_constant)
        _fields(d, ("schema", "ledger_id", "created_at", "created_by", "constants",
                    "entries", "looks", "price_tries", "errata"), "top level")
        _need(_is_int(d["schema"]) and d["schema"] == LEDGER_SCHEMA, "schema")
        _need(_is_uuid(d["ledger_id"]) and _is_num(d["created_at"])
              and _is_text(d["created_by"]), "header")
        _check_constants(d["constants"])
        boundary, sizes = _file_boundary(d["constants"]), _file_looks(d["constants"])
        _need(isinstance(d["entries"], dict), "entries")
        for pid, e in d["entries"].items():
            _check_entry(pid, e)
        _need(isinstance(d["looks"], dict), "looks")
        for key, lk in d["looks"].items():
            _check_look(key, lk, boundary, sizes)
        _check_looks_order(d["looks"])
        _need(isinstance(d["price_tries"], dict), "price_tries")
        for pid, days in d["price_tries"].items():
            _need(_is_text(pid, LEDGER_ID_MAX) and isinstance(days, list) and len(days) <= 400
                  and all(_is_day(v) for v in days), "price_tries")
        _need(isinstance(d["errata"], list) and len(d["errata"]) <= LEDGER_ERRATA_MAX,
              "errata")
        for er in d["errata"]:
            _fields(er, LEDGER_ERRATUM_FIELDS, "errata")
            _need(_is_text(er["id"], LEDGER_ID_MAX) and _is_text(er["reason"])
                  and _opt_num(er["r"]) and _is_day(er["date"]), "errata")
    except (ValueError, TypeError, RecursionError) as exc:
        return None, type(exc).__name__
    return d, None


def _no_constant(name: str):
    raise LedgerFormatError(f"{name} is not a number")      # NaN, Infinity


def ledger_marker_parse(raw) -> tuple[dict | None, str | None]:
    """The marker in ``portfolio.json``, or the sidecar beside the ledger:
    ``(None, None)`` when there is none, ``(marker, None)``, or
    ``(None, reason)`` when it is there but damaged — which is never the same
    as "no ledger yet". The count of looks is 0 when absent. An ``entries``
    count (fix loop 1 wrote one) is checked and dropped: entries are no
    longer counted (see :func:`ledger_anchor`)."""
    if raw is None:
        return None, None
    if (isinstance(raw, dict) and {"ledger_id", "created_at"} <= set(raw)
            <= {"ledger_id", "created_at", "looks", "entries"}
            and _is_uuid(raw["ledger_id"]) and _is_num(raw["created_at"])
            and all(_is_int(raw.get(k, 0)) and raw.get(k, 0) >= 0
                    for k in ("looks", "entries"))):
        return {"ledger_id": raw["ledger_id"], "created_at": raw["created_at"],
                "looks": raw.get("looks", 0)}, None
    return None, LedgerFormatError.__name__


def ledger_id_of(text) -> str | None:
    """The ``ledger_id`` of a ledger-shaped text — a backup or a retired
    record — or None when the text is not a JSON object naming one. Only the
    id is read, so a copy made under other constants is still attributed
    (code review r2 P2-N2); nothing else in it is trusted or used."""
    try:
        d = json.loads(text, parse_constant=_no_constant)
    except (ValueError, TypeError, RecursionError):
        return None
    lid = d.get("ledger_id") if isinstance(d, dict) else None
    return lid if _is_uuid(lid) else None


def ledger_belongs(ledger: dict, book_ids) -> bool:
    """Whether a ledger found with no marker or sidecar can be this book's:
    empty, or every recorded entry and every recorded look member is a
    protocol position the book holds (code review P1-1)."""
    ids = set(book_ids)
    return (set(ledger["entries"]) <= ids
            and all(m["id"] in ids for lk in ledger["looks"].values() for m in lk["members"]))


def ledger_merge(old: dict, readout: dict, now: float, build: str,
                 refused: list | None = None,
                 refused_looks: list | None = None) -> tuple[dict, int]:
    """``old`` plus what ``readout`` has decided or evaluated for the first
    time: ``(new, added)``. Write-once: an entry is added only when its id is
    absent and its state is final (:data:`SHADOW_FINAL`); a look only when its
    key is absent and it was evaluated here. No existing entry, look,
    constant or erratum is ever changed or removed. Only ``price_tries``
    changes: the days are kept and added to, and an entry's are dropped once
    it is decided. ``old`` is never modified.

    Each new entry and look is checked as :func:`ledger_parse` would read it
    back — a look against the file's own line and sizes — and one that
    fails is left out, so the file never holds what this build could not
    read again (security P2-3, code review r2 P3-N1), and one bad record
    never blocks the rest. A refused entry's id is appended to ``refused``;
    a refused look's ``"look k"`` to ``refused_looks``, or, without it, to
    ``refused``."""
    new = copy.deepcopy(old)
    added = 0
    boundary, sizes = _file_boundary(new["constants"]), _file_looks(new["constants"])
    if refused_looks is None:
        refused_looks = refused
    for e in readout.get("entries", ()):
        if e["id"] in new["entries"] or e["state"] not in SHADOW_FINAL:
            continue
        rec = {f: copy.deepcopy(e.get(f)) for f in LEDGER_ENTRY_FIELDS
               if f not in ("decided_at", "build")}
        rec = {**rec, "decided_at": now, "build": build}
        try:
            _check_entry(e["id"], rec)
            json.dumps(rec, allow_nan=False)
        except (ValueError, TypeError):
            if refused is not None:
                refused.append(e["id"])
            continue
        new["entries"][e["id"]] = rec
        added += 1
    for lk in readout.get("looks", ()):
        key = str(lk["k"])
        if key in new["looks"] or not lk.get("evaluated") or lk.get("recorded"):
            continue
        rec = {"k": lk["k"], "n": lk["n"], "evaluated_at": now, "build": build,
               "z": lk["z"], "z_lo": lk["z_lo"], "z_hi": lk["z_hi"], "method": lk["method"],
               "crossed": lk["crossed"], "design_closed": lk["design_closed"],
               "used": lk["used"], "n_excluded": lk["n_excluded"],
               "members": copy.deepcopy(lk["members"])}
        try:
            _check_look(key, rec, boundary, sizes)
            _check_looks_order({**new["looks"], key: rec})
            json.dumps(rec, allow_nan=False)
        except (ValueError, TypeError, KeyError):
            if refused_looks is not None:
                refused_looks.append(f"look {key}")
            continue
        new["looks"][key] = rec
        added += 1
    tries = new["price_tries"]
    states = {e["id"]: e["state"] for e in readout.get("entries", ())}
    for pid, days in (readout.get("price_tries") or {}).items():
        if not _is_text(pid, LEDGER_ID_MAX):
            continue
        have = tries.get(pid, ())
        if states.get(pid) != "wait_price" and len(have) >= SHADOW_PRICE_TRIES:
            # No longer waiting (final as "no price" for its looks), with its
            # days recorded: no more are needed. Added every failed day, a
            # never-priced entry passed the reader's limit of 400 days about
            # 13 months on, and every later write failed its read-back (QA
            # P2-1). Days are now added only while the entry waits; with its
            # tries it waits no later than 28 days after t_T, so the list
            # stays short.
            continue
        tries[pid] = sorted(set(have) | set(days))
    for pid in [pid for pid in tries if pid in new["entries"]]:
        del tries[pid]
    return new, added


def ledger_check(ledger: dict | None, entries: list[dict]) -> list[dict]:
    """The membership and constants check (validator P2-2) — not a re-grade:
    recorded outcomes are reused, so a wrong close is never found here. For
    each recorded look: the constants it was made under against today's
    (``constants``), the members it would have today against the record
    (``members``), and, with the same members, today's z against the
    recorded one (``z`` — possible only when a member left out for want of a
    price has since been graded). The record is kept whatever this finds."""
    if not ledger:
        return []
    order = _order(entries)
    same = ledger["constants"] == ledger_constants()
    out = []
    for key in sorted(ledger["looks"], key=int):
        rec = ledger["looks"][key]
        why = None
        if not same:
            why = "constants"
        else:
            today = order[:rec["n"]]
            if [e["id"] for e in today] != [m["id"] for m in rec["members"]]:
                why = "members"
            elif [e["state"] for e in today] != [m["state"] for m in rec["members"]]:
                graded = [e for e in today if e["state"] in SHADOW_GRADED]
                z = hc3_z([e["confidence"] for e in graded], [e["r"] for e in graded])
                if (z is None) != (rec["z"] is None) or (
                        z is not None and abs(z - rec["z"]) > 1e-9):
                    why = "z"
        if why:
            out.append({"k": rec["k"], "why": why, "recorded_at": rec["evaluated_at"]})
    return out


def ledger_errata(ledger: dict | None) -> list[dict]:
    """The errata, for display, each with the recorded looks its position is
    a member of. Read-only: nothing here changes a result. The members are
    indexed once, so the cost is errata + members, not their product
    (security P3-1)."""
    if not ledger:
        return []
    where: dict[str, list[int]] = {}
    for key in sorted(ledger["looks"], key=int):
        rec = ledger["looks"][key]
        for pid in {m["id"] for m in rec["members"]}:
            where.setdefault(pid, []).append(rec["k"])
    return [{**er, "looks": list(where.get(er["id"], ()))} for er in ledger["errata"]]
