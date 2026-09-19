"""The hourly volatility study — the Terminal model's σ, put on trial.

`sonar/volatility.py` measured (on daily bars) that clustering models beat an
equally-weighted trailing window at short horizons, and the app duly wired
GARCH into the *asset screener*. The Terminal model — the shortest horizon in
the project and the only place a probability is asserted — kept using a flat
72-hour trailing window (`model.hourly_sigma`), which contradicts the
project's own finding one tab over. σ is also the only quantity the model
disagrees with the market about, so nothing else in `prob_up` is worth
sharpening first.

Two hypotheses, both pre-registered below before the study ran:

1. **Clustering** — EWMA / GARCH beat trailing-72 at a one-hour horizon, the
   same shape the daily study found at three days.
2. **Diurnal seasonality** — BTC hourly volatility has a time-of-day pattern
   (US hours vs the Asian lull), which a flat window smears across the clock:
   it over-forecasts the quiet hours and under-forecasts the busy ones, and a
   causal hour-of-day profile multiplied onto any base forecaster should fix
   exactly that.

The discipline is `volatility.py`'s: QLIKE against the hour that actually
followed, walk-forward with nothing after the decision hour visible, a pooled
verdict that must also hold across contiguous time blocks, and a synthetic
constant-volatility control on which the clustering and seasonal models must
*not* win (`tests/test_hourlyvol.py` runs that control on every build). The
caller owns the fetching, so the study itself is testable offline.

Targets are single non-overlapping hours, so unlike the daily study no step
or HAC correction is needed: each scored hour is its own reading.
"""

from __future__ import annotations

import json
import math
import urllib.request
from dataclasses import dataclass

# Everything here is stdlib-only, like the rest of SONAR.

#: RiskMetrics' published daily decay, standing in at hourly frequency — a
#: published number rather than a fitted one, and named as a stand-in. At one
#: hour it forgets with a half-life of ~11 hours.
EWMA_LAMBDA = 0.94
#: GARCH(1,1) at published-typical daily parameters, the same stand-in
#: `volatility.garch_like` uses. Not fitted here either.
GARCH_ALPHA, GARCH_BETA = 0.09, 0.90

#: The incumbent's window — what `model.hourly_sigma` reads today.
TRAILING = 72
#: Hours of history behind the hour-of-day profile: 60 days, so each of the
#: 24 cells averages ~60 squared returns. 30 days was pre-registered first and
#: rejected on arithmetic alone — 30 fat-tailed observations per cell is a
#: noise generator — before any data was scored.
DIURNAL_WINDOW = 1440
#: A cell ratio outside this range is one news hour wearing a pattern's
#: clothes; the profile is a *seasonal* claim and gets clamped to stay one.
PROFILE_CLAMP = (0.25, 4.0)

MIN_VOL = 1e-6

#: What each model was expected to do, recorded before the study ran, so a
#: negative result cannot be quietly reinterpreted afterwards.
PRE_REGISTERED = {
    "trailing72": "the incumbent (model.hourly_sigma), and the baseline",
    "ewma": "beats trailing72 — clustering, as the daily study found at 3d",
    "garch": "close to EWMA; mean reversion matters less inside one hour",
    "trailing72_diurnal": "beats trailing72 — the profile alone should carry "
                          "information a flat window smears across the clock",
    "ewma_diurnal": "best of all — clustering and seasonality are different "
                    "facts about the same hour",
}

MODELS = ("trailing72", "ewma", "garch", "trailing72_diurnal", "ewma_diurnal")


def qlike(forecast: float, actual: float) -> float:
    """Same loss, same reasons as `volatility.qlike`: robust to the target
    being a noisy proxy (here a single hour's |return|), and it punishes
    under-forecasting harder — the asymmetry a risk number should have."""
    f2 = max(forecast, MIN_VOL) ** 2
    a2 = max(actual, MIN_VOL) ** 2
    return a2 / f2 - math.log(a2 / f2) - 1.0


class _Rolling:
    """Rolling mean/variance over a fixed window, O(1) per step."""

    def __init__(self, window: int):
        self.window = window
        self.buf: list[float] = []
        self.i = 0
        self.s = 0.0
        self.ss = 0.0

    def push(self, x: float) -> None:
        if len(self.buf) < self.window:
            self.buf.append(x)
        else:
            old = self.buf[self.i]
            self.s -= old
            self.ss -= old * old
            self.buf[self.i] = x
            self.i = (self.i + 1) % self.window
        self.s += x
        self.ss += x * x

    @property
    def full(self) -> bool:
        return len(self.buf) >= self.window

    def std(self) -> float:
        n = len(self.buf)
        if n < 3:
            return 0.0
        var = (self.ss - self.s * self.s / n) / (n - 1)
        return math.sqrt(max(var, 0.0))

    def mean_sq(self) -> float:
        n = len(self.buf)
        return self.ss / n if n else 0.0


class _Diurnal:
    """A causal hour-of-day variance profile over the trailing window."""

    def __init__(self, window: int = DIURNAL_WINDOW):
        self.window = window
        self.buf: list[tuple[int, float]] = []
        self.i = 0
        self.per_hod = [0.0] * 24
        self.n_hod = [0] * 24
        self.total = 0.0

    def push(self, hod: int, r2: float) -> None:
        if len(self.buf) < self.window:
            self.buf.append((hod, r2))
        else:
            old_h, old_r2 = self.buf[self.i]
            self.per_hod[old_h] -= old_r2
            self.n_hod[old_h] -= 1
            self.total -= old_r2
            self.buf[self.i] = (hod, r2)
            self.i = (self.i + 1) % self.window
        self.per_hod[hod] += r2
        self.n_hod[hod] += 1
        self.total += r2

    @property
    def full(self) -> bool:
        return len(self.buf) >= self.window

    def factor(self, hod: int) -> float:
        """Variance multiplier for this hour of day; 1.0 = a typical hour."""
        n = len(self.buf)
        if not n or not self.n_hod[hod] or self.total <= 0:
            return 1.0
        overall = self.total / n
        cell = self.per_hod[hod] / self.n_hod[hod]
        lo, hi = PROFILE_CLAMP
        return max(lo, min(hi, cell / overall))


@dataclass(frozen=True)
class Verdict:
    model: str
    qlike: float
    versus_trailing: float       # improvement as a fraction; > 0 is better
    blocks_won: int
    blocks: int
    n: int

    @property
    def verdict(self) -> str:
        """`volatility.Verdict`'s vocabulary and its discipline: beating the
        pooled average is not enough, the win has to hold across time blocks.
        One instrument here (the Terminal prices BTC and nothing else), so
        blocks are the whole consistency axis and the bar is higher for it."""
        if self.n < 2000 or self.blocks < 4:
            return "INSUFFICIENT"
        if self.versus_trailing <= 0:
            return "DROP"
        if self.blocks_won >= self.blocks - 1:
            return "KEEP"
        return "WEAK"

    def as_dict(self) -> dict:
        return {"model": self.model, "qlike": round(self.qlike, 5),
                "vs_trailing_pct": round(self.versus_trailing * 100, 2),
                "blocks_won": f"{self.blocks_won}/{self.blocks}",
                "n": self.n, "verdict": self.verdict}


def hods_from_times(times: list[int]) -> list[int]:
    """UTC hour-of-day per candle open. UTC on purpose: the profile's job is
    to be a stable clock pattern, and DST would smear two hours into one twice
    a year for no benefit a rate this coarse could see."""
    return [(t % 86400) // 3600 for t in times]


def log_returns(closes: list[float]) -> list[float]:
    return [math.log(closes[i] / closes[i - 1])
            for i in range(1, len(closes))
            if closes[i - 1] > 0 and closes[i] > 0]


def study(closes: list[float], times: list[int], blocks: int = 6,
          warmup: int = DIURNAL_WINDOW) -> dict:
    """Walk every hour once, scoring all five models on the hour that followed.

    `times` are the candles' open times (unix seconds), aligned with `closes`;
    return `i` (of hour `times[i+1]`) is forecast from information up to and
    including hour `times[i]`. All model state is updated incrementally, so
    17,000 hours score in well under a second.
    """
    rets = log_returns(closes)
    hods = hods_from_times(times)[1:]           # hod of each *return's* hour
    if len(rets) != len(hods) or len(rets) < warmup + 100:
        return {"error": f"need at least {warmup + 100} clean hourly returns, "
                         f"got {len(rets)}"}

    trail = _Rolling(TRAILING)
    trail_d = _Rolling(TRAILING)                 # over deseasonalised returns
    diurnal = _Diurnal()
    lr720 = _Rolling(720)                        # GARCH's long-run anchor
    ewma_var = ewma_d_var = garch_var = None

    losses: dict[str, list[float]] = {m: [] for m in MODELS}

    for i, (r, hod) in enumerate(zip(rets, hods)):
        # ---- forecast hour i from state built on hours < i ---------------- #
        if i >= warmup:
            fac = diurnal.factor(hod)
            f = {
                "trailing72": trail.std(),
                "ewma": math.sqrt(ewma_var),
                "garch": math.sqrt(garch_var),
                "trailing72_diurnal": trail_d.std() * math.sqrt(fac),
                "ewma_diurnal": math.sqrt(ewma_d_var * fac),
            }
            a = abs(r)
            for m in MODELS:
                losses[m].append(qlike(f[m], a))

        # ---- then let hour i into the state ------------------------------- #
        r2 = r * r
        fac_now = diurnal.factor(hod)            # profile as of before hour i
        rd2 = r2 / fac_now
        trail.push(r)
        trail_d.push(r / math.sqrt(fac_now))
        diurnal.push(hod, r2)
        lr720.push(r)
        if ewma_var is None:
            ewma_var = ewma_d_var = garch_var = max(r2, MIN_VOL ** 2)
        else:
            ewma_var = EWMA_LAMBDA * ewma_var + (1 - EWMA_LAMBDA) * r2
            ewma_d_var = EWMA_LAMBDA * ewma_d_var + (1 - EWMA_LAMBDA) * rd2
            long_run = max(lr720.mean_sq(), MIN_VOL ** 2)
            omega = long_run * (1 - GARCH_ALPHA - GARCH_BETA)
            garch_var = omega + GARCH_ALPHA * r2 + GARCH_BETA * garch_var

    n = len(losses["trailing72"])
    pooled = {m: sum(losses[m]) / n for m in MODELS}

    width = n // blocks
    verdicts = []
    for m in MODELS:
        if m == "trailing72":
            continue
        won = sum(1 for b in range(blocks)
                  if sum(losses[m][b * width:(b + 1) * width])
                  < sum(losses["trailing72"][b * width:(b + 1) * width]))
        verdicts.append(Verdict(
            model=m, qlike=pooled[m],
            versus_trailing=(pooled["trailing72"] - pooled[m])
            / pooled["trailing72"],
            blocks_won=won, blocks=blocks, n=n))

    return {"n_scored": n, "blocks": blocks,
            "pooled_qlike": {m: round(v, 5) for m, v in pooled.items()},
            "verdicts": [v.as_dict() for v in verdicts],
            "pre_registered": PRE_REGISTERED}


# --------------------------------------------------------------------------- #
# What the app actually uses
# --------------------------------------------------------------------------- #
#: The study's result, run 2026-09-19 on 16,078 held-out hours (two years of
#: BTCUSDT, six time blocks). Every candidate beat the incumbent in 6/6
#: blocks; the winner is the one that was pre-registered to win:
#:
#:     model                QLIKE     vs trailing-72
#:     trailing72           1.96318   — (the incumbent, model.hourly_sigma)
#:     ewma                 1.88664   +3.90%   KEEP
#:     garch                1.83963   +6.29%   KEEP
#:     trailing72_diurnal   1.89385   +3.53%   KEEP
#:     ewma_diurnal         1.81567   +7.51%   KEEP  <- shipped
#:
#: Why ewma_diurnal over garch, despite garch's KEEP: EWMA has *less*
#: effective history than the incumbent and the profile finds nothing on the
#: synthetic constant-volatility control (both asserted in
#: tests/test_hourlyvol.py), so ewma_diurnal's win can only be clustering and
#: seasonality — the two effects hypothesised. GARCH's 720-hour anchor means
#: part of its win is effective sample size, the exact artefact the daily
#: study's control caught in `volatility.py`.
STUDY_RESULT_2026_09 = {
    "trailing72": 1.96318, "ewma": 1.88664, "garch": 1.83963,
    "trailing72_diurnal": 1.89385, "ewma_diurnal": 1.81567,
}

#: Fewer returns than this and there is no volatility estimate to give.
MIN_RETURNS = 72


def forecast(closes: list[float], times: list[int],
             target_time: int | None = None) -> float | None:
    """σ for the hour in progress, per the study's winner (EWMA × diurnal).

    Degrades along the measured ladder rather than guessing: with less than a
    full profile window of history the seasonal factor is dropped and plain
    EWMA remains (KEEP on its own, +3.9%); with less than `MIN_RETURNS` the
    answer is None and the caller falls back to `model.hourly_sigma`. The
    profile is only applied in the form the study measured — a full window —
    because a three-day profile is a different, unmeasured estimator.
    """
    rets = log_returns(closes)
    if len(rets) != len(closes) - 1 or len(rets) < MIN_RETURNS:
        return None                              # gappy or too-short series
    hods = hods_from_times(times)[1:]

    ewma_var = None
    diurnal = _Diurnal()
    for r, hod in zip(rets, hods):
        r2 = r * r
        diurnal.push(hod, r2)
        ewma_var = (max(r2, MIN_VOL ** 2) if ewma_var is None
                    else EWMA_LAMBDA * ewma_var + (1 - EWMA_LAMBDA) * r2)

    if target_time is None:
        target_time = times[-1] + 3600
    factor = diurnal.factor((target_time % 86400) // 3600) if diurnal.full else 1.0
    return max(math.sqrt(ewma_var * factor), MIN_VOL)


# --------------------------------------------------------------------------- #
# Fetching, kept apart from the study so the study stays offline-testable
# --------------------------------------------------------------------------- #
_KLINES = ("https://api.binance.com/api/v3/klines"
           "?symbol={sym}&interval=1h&startTime={start}&limit=1000")
_UA = {"User-Agent": "sonar/0.4 (research)"}


def fetch_hourly(symbol: str = "BTCUSDT", days: int = 730
                 ) -> tuple[list[int], list[float]]:
    """Paged hourly closes from Binance — ~18 requests for two years."""
    import time as _time

    start = (int(_time.time()) - days * 86400) * 1000
    times: list[int] = []
    closes: list[float] = []
    while True:
        url = _KLINES.format(sym=symbol, start=start)
        try:
            req = urllib.request.Request(url, headers=_UA)
            rows = json.loads(urllib.request.urlopen(req, timeout=15).read())
        except Exception:
            break
        if not rows:
            break
        for r in rows:
            times.append(int(r[0]) // 1000)
            closes.append(float(r[4]))
        if len(rows) < 1000:
            break
        start = int(rows[-1][0]) + 3_600_000
    if times and closes:
        times.pop(), closes.pop()               # drop the in-progress hour
    return times, closes
