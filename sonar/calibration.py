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
changes no exit, no ``GRADED``, no ``Z_CLAIM`` and no ``P(profit)``.
"""

from __future__ import annotations

import bisect
import copy
import math
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
SHADOW_PRICE_GRACE_DAYS = 7       # past t_T with no final close: waiting, then left out
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
# The newest bar of a fetch counts as a finished session only when its stamp
# is at least this long before that fetch: no session runs longer than a day,
# and an in-progress bar carries a recent stamp (its session start, or the
# fetch time itself, code review P1-2). Measured against the fetch, never
# against now, so a series kept from a failed day does not turn final.
SHADOW_FINAL_AFTER_S = 86_400.0
SHADOW_CRYPTO = "Crypto"          # the asset class that trades on all seven days
DAY_S = 86_400.0

#: An entry's state in the shadow. The first three are graded; the next two
#: are not yet; the last two are exclusions, counted and shown.
SHADOW_GRADED = ("target", "stop", "time")
SHADOW_PENDING = ("waiting", "wait_price")
SHADOW_EXCLUDED = ("left", "no_price")


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
    engine fetches only for these; a barrier hit before T needs no price."""
    if not p.protocol or p.pending:
        return False
    t_due = shadow_due(p)
    if now < t_due:
        return False
    return p.closed_at is None or p.closed_at > t_due


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


def _shadow_from_bars(p, series: list[tuple[float, float]] | None, t_due: float,
                      booked: str | None,
                      fetched: float | None = None) -> tuple[str, float | None, bool] | None:
    """Rules 1–3 for an entry past t_T, from its symbol's daily bars. Returns
    ``(state, exit price, gap)``, or None when the bars cannot decide yet: no
    series, one that does not reach back to the entry, no bar after the entry
    up to t_T, or no final T bar and cut bar.

    The newest bar is trusted only when it is a finished session: stamped at
    least :data:`SHADOW_FINAL_AFTER_S` before ``fetched``, the time of the
    fetch that returned it (without a fetch time, never). Otherwise it may
    still be trading, and Yahoo may stamp it with the fetch time rather than
    its session's start (EURCHF=X read `11:17` on 2026-10-12, code review
    P1-2): its close is never used, and its stamp neither picks the T bar nor
    serves as the cut. What it still proves is bounded: its session started
    after ``stamp − 24 h`` (no session is longer, and its stamp is its start
    or later). When that bound is already past t_T, the T bar is the last
    trusted bar at or before t_T and is finished, and the cut lies in
    ``(stamp − 24 h, stamp]`` — enough for rule 1 unless a booked close falls
    inside that window, which then waits.

    Measured, US-session bars and one fetch a day at 00:01 UTC (code review
    r2 P2-B; `test_r2_latency_*`): a T on Monday–Thursday is decided 2.4 days
    after t_T, a Friday T 3.4 days after (round 1: Thursday and Friday 4.4), a
    holiday after T adds a day — at least 2.6 days inside the 7-day grace
    before "no price"."""
    series = list(series or [])
    pending = None                           # the newest bar, if not trusted
    if series and (fetched is None or series[-1][0] > fetched - SHADOW_FINAL_AFTER_S):
        pending = series.pop()[0]
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
    if i < 0 or stamps[i] <= p.opened_at:
        return None
    if i + 1 < len(series):
        cut_lo = cut_hi = stamps[i + 1]      # a trusted later bar: the cut is its stamp
    elif pending is not None and pending - SHADOW_FINAL_AFTER_S > t_due:
        cut_lo, cut_hi = pending - SHADOW_FINAL_AFTER_S, pending
    else:
        return None                          # nothing yet shows the T bar is finished
    if booked is not None:                   # rule 1: closed before the cut?
        if cut_lo == cut_hi:
            before_cut = p.closed_at < cut_hi
        elif p.closed_at <= cut_lo or p.closed_at >= cut_hi:
            before_cut = p.closed_at <= cut_lo
        else:
            return None                      # closed inside the window the cut may lie in
        if before_cut:
            if booked in GRADED:
                return booked.lower(), (p.target if booked == "TARGET" else p.stop), False
            return "left", None, False
    # A bar's close comes at its session's end. Only bars that *start* after
    # the entry are certainly closed after it: the entry day's own close may
    # predate the entry, and the live polls watched that session anyway.
    for j in range(bisect.bisect_right(stamps, p.opened_at), i + 1):
        hit = p.hit(series[j][1])
        if hit:
            return hit.lower(), (p.target if hit == "TARGET" else p.stop), True
    return "time", series[i][1], False


def shadow_decided(result: dict) -> dict[str, dict]:
    """The entries of a readout whose outcome is settled for good — graded
    (barrier, gap, or TIME on a final T bar) or left out by a hand close — by
    position id. The engine keeps these in memory and hands them back, so an
    outcome once decided cannot change within the process: not when a fetch
    fails, and not when the provider rewrites old closes (code review P1-1,
    P2-1). "No price" is not settled: closes may still come. Nothing here is
    persisted (ADR 0002 §7)."""
    return {e["id"]: e for e in result.get("entries", ())
            if e["state"] in SHADOW_GRADED or e["state"] == "left"}


def _shadow_entry(p, series, now: float, fetched: float | None = None) -> dict:
    """One protocol entry's shadow outcome. Reads the position; never writes it."""
    t_due = shadow_due(p)
    booked = p.outcome if p.closed_at is not None else None
    state, exit_price, gap = "waiting", None, False
    if booked is not None and p.closed_at <= t_due:
        # Settled by the book before T: final, and needs no price. Graded only
        # from t_T on, like every other entry, so the running figures never
        # lean on the quick resolvers the closed-only grade leans on.
        if booked not in GRADED:
            state = "left"
        elif now >= t_due:
            state = booked.lower()
            exit_price = p.target if booked == "TARGET" else p.stop
    elif now >= t_due:
        got = _shadow_from_bars(p, series, t_due, booked, fetched)
        if got is not None:
            state, exit_price, gap = got
        elif now >= t_due + SHADOW_PRICE_GRACE_DAYS * DAY_S:
            state = "no_price"
        else:
            state = "wait_price"
    risk = abs(p.entry - p.stop)
    r = None
    if exit_price is not None:
        if risk > 0:
            d = 1.0 if p.direction == "LONG" else -1.0
            r = d * (exit_price - p.entry) / risk
        else:                               # no stop distance: no R, never a guess
            state, exit_price, gap = "no_price", None, False
    ref_t, ref_s = scoring.barrier_probabilities_within(
        p.rr, 1.0, shadow_reference_horizons(p))
    return {"id": p.id, "symbol": p.symbol, "direction": p.direction,
            "confidence": float(p.confidence or 0.0), "opened_at": p.opened_at,
            "t_due": t_due, "t_days": shadow_t_days(p.horizon), "rr": p.rr,
            "booked": booked, "state": state, "exit": exit_price, "r": r, "gap": gap,
            "ref": [ref_t, ref_s]}


def shadow_looks(entries: list[dict]) -> list[dict]:
    """The three pre-registered looks (ADR §3).

    A cohort is the first N entries by ``opened_at`` — membership by entry
    order, never by resolution, so a look cannot re-select quick resolvers.
    A look is evaluated once every member has an outcome or a final exclusion,
    and its value depends on its members alone. |z| ≥ :data:`SHADOW_BOUNDARY`
    crosses; the first crossing is the result and closes the design, so no
    later look is evaluated.
    """
    order = sorted(entries, key=lambda e: (e["opened_at"], e["id"]))
    out: list[dict] = []
    closed_at_look = None
    for k, n in enumerate(SHADOW_LOOKS, start=1):
        members = order[:n]
        graded = [e for e in members if e["state"] in SHADOW_GRADED]
        excluded = sum(1 for e in members if e["state"] in SHADOW_EXCLUDED)
        entered = len(members)
        final = entered == n and len(graded) + excluded == n
        evaluated = final and closed_at_look is None
        z = (hc3_z([e["confidence"] for e in graded], [e["r"] for e in graded])
             if evaluated else None)
        crossed = bool(evaluated and z is not None and abs(z) >= SHADOW_BOUNDARY)
        out.append({
            "k": k, "n": n, "entered": entered, "n_missing": n - entered,
            "due": max(e["t_due"] for e in members) if entered == n else None,
            "used": len(graded), "n_excluded": excluded,
            "n_waiting": sum(1 for e in members if e["state"] == "waiting"),
            "n_wait_price": sum(1 for e in members if e["state"] == "wait_price"),
            "evaluated": evaluated, "z": z, "crossed": crossed,
            "design_closed": closed_at_look is not None,
        })
        if crossed:
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
                     decided: dict[str, dict] | None = None,
                     fetched_at: dict[str, float] | None = None) -> dict:
    """The time-stop shadow of the score grade, for every protocol entry.

    ``open`` and ``closed`` are :class:`sonar.portfolio.Position` lists (the
    engine passes copies); ``bars`` maps a symbol to its daily
    ``(timestamp, close)`` pairs as :func:`sonar.assets.fetch_bars` returns
    them. Pure: it reads its inputs and returns a new dict of plain numbers,
    ready for JSON. Pending orders are not positions and are skipped; manual
    entries are counted and never graded. Bars stamped after ``now`` are
    ignored: a future stamp would make an in-progress bar look final.

    ``decided`` is :func:`shadow_decided` of earlier readouts: an entry found
    there keeps that outcome (deep-copied, never recomputed). Only an entry
    still protocol and filled is looked up, so the book stays the population;
    its ``booked`` outcome is refreshed from the position, so ``ic_closed``
    reads the book as it is now (code review r2 P3-1).

    ``fetched_at`` maps a symbol to the time its bars were fetched; with it,
    a newest bar old enough to be a finished session can be used (see
    :func:`_shadow_from_bars`). Without it the newest bar never is.
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

    entries: list[dict] = []
    n_nonprotocol = 0
    for p in list(open) + list(closed):
        if p.pending:
            continue
        if not p.protocol:
            n_nonprotocol += 1
            continue
        if decided and p.id in decided:
            kept = copy.deepcopy(decided[p.id])
            kept["booked"] = p.outcome if p.closed_at is not None else None
            entries.append(kept)
            continue
        entries.append(_shadow_entry(p, series.get(p.symbol), now,
                                     (fetched_at or {}).get(p.symbol)))
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
    return {
        "n_entered": len(entries),
        "n_reached": n,
        "n_target": split["target"], "n_stop": split["stop"], "n_time": split["time"],
        "n_waiting": len(waiting),
        "next_t": min(waiting) if waiting else None,
        "n_wait_price": sum(1 for e in entries if e["state"] == "wait_price"),
        "n_nonprotocol": n_nonprotocol,
        "n_left": sum(1 for e in entries if e["state"] == "left"),
        "n_no_price": sum(1 for e in entries if e["state"] == "no_price"),
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
        "looks": shadow_looks(entries),
        "bands": bands,
        "entries": entries,
        "computed_at": now,
        "error": None,
    }
