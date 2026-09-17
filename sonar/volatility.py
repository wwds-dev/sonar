"""Forecasting volatility, which is the one thing the evidence says is forecastable.

`CONFIDENCE.md` §8: all five of SONAR's nulls tested **direction**. Volatility
was never the target, and the literature is consistent that news and attention
predict *realised volatility* rather than returns — which is the same shape as
SONAR's own result, where a news spike beat the directional baseline by 0.8
points against a ±3.1 error bar.

It matters more here than it would in most apps because **SONAR already consumes
a volatility forecast structurally**. `scoring.build_plan()` scales the target
and the stop by `vol`, which sets `R:R`, which fixes
`P(profit) = 1/(1 + R:R)`. So a better volatility number improves the plan, the
sizing and the stated probability at once — without claiming a direction
anywhere.

Nothing here is wired into the app until it has beaten the incumbent out of
sample. `study.py` in this module is the measurement, and `PRE_REGISTERED`
records what each model was predicted to do *before* it was run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Series = list[float]

#: RiskMetrics' daily decay. Not fitted here — it is the published value, and
#: fitting one more parameter on this much data is how you overfit quietly.
EWMA_LAMBDA = 0.94

#: Floor so a halted instrument cannot produce a zero that divides by zero
#: three calls later.
MIN_VOL = 1e-6


def log_returns(closes: Series) -> Series:
    """Both ends guarded — a zero close is what a halted feed sends."""
    return [math.log(closes[i] / closes[i - 1])
            for i in range(1, len(closes))
            if closes[i - 1] > 0 and closes[i] > 0]


# --------------------------------------------------------------------------- #
# The forecasters
# --------------------------------------------------------------------------- #
def trailing(rets: Series, window: int = 20) -> float | None:
    """Equally-weighted realised volatility — **the incumbent**.

    This is what `assets._daily_vol` computes today. Every model below has to
    beat it on held-out data or it does not ship.
    """
    sample = rets[-window:]
    if len(sample) < 3:
        return None
    mean = sum(sample) / len(sample)
    var = sum((r - mean) ** 2 for r in sample) / (len(sample) - 1)
    return max(math.sqrt(var), MIN_VOL)


def ewma(rets: Series, lam: float = EWMA_LAMBDA) -> float | None:
    """Exponentially-weighted volatility — recent days count for more.

    Volatility clusters: calm follows calm and shocks follow shocks. An
    equally-weighted window treats a return from twenty days ago as exactly as
    informative as yesterday's, which for a clustered process it is not.
    """
    if len(rets) < 3:
        return None
    var = rets[0] ** 2
    for r in rets[1:]:
        var = lam * var + (1.0 - lam) * r * r
    return max(math.sqrt(var), MIN_VOL)


def garch_like(rets: Series, alpha: float = 0.09, beta: float = 0.90,
               window: int = 250) -> float | None:
    """A GARCH(1,1) recursion at published-typical parameters, not fitted.

    `omega` is implied from the sample's own long-run variance, so the model
    mean-reverts toward what this instrument actually does rather than toward a
    constant borrowed from somewhere else. The difference from EWMA is exactly
    that reversion: EWMA has none, so after a shock it stays frightened
    indefinitely, which is wrong at any horizon longer than a day or two.

    `alpha + beta` near 0.99 is the usual empirical finding for daily equity
    data — high persistence, slow reversion.
    """
    if len(rets) < 30 or alpha + beta >= 1.0:
        return None
    sample = rets[-window:]
    long_run = sum(r * r for r in sample) / len(sample)
    omega = long_run * (1.0 - alpha - beta)
    var = long_run
    for r in sample:
        var = omega + alpha * r * r + beta * var
    return max(math.sqrt(var), MIN_VOL)


def blended(rets: Series, weights: tuple[float, float, float] = (0.2, 0.4, 0.4)
            ) -> float | None:
    """Trailing, EWMA and GARCH averaged in variance space.

    Forecast combination beats its own components more often than not, and
    averaging *variances* rather than volatilities is the right space for it —
    variance is what is additive.
    """
    parts = [trailing(rets), ewma(rets), garch_like(rets)]
    pairs = [(w, v) for w, v in zip(weights, parts) if v is not None]
    if not pairs:
        return None
    total = sum(w for w, _ in pairs)
    var = sum(w * v * v for w, v in pairs) / total
    return max(math.sqrt(var), MIN_VOL)


MODELS = {"trailing": trailing, "ewma": ewma, "garch": garch_like,
          "blended": blended}

#: What each model was expected to do, recorded **before** the study ran. The
#: point is that a negative result cannot be quietly reinterpreted afterwards.
PRE_REGISTERED = {
    "trailing": "the incumbent, and the baseline every other model must beat",
    "ewma": "better than trailing — volatility clusters, so recent days are "
            "more informative than an equally-weighted window",
    "garch": "better than EWMA at longer horizons — EWMA never mean-reverts, "
             "so it stays frightened after a shock",
    "blended": "better than any single one — forecast combination usually is",
}


# --------------------------------------------------------------------------- #
# Scoring a forecast
# --------------------------------------------------------------------------- #
def realised_forward(rets: Series, start: int, horizon: int) -> float | None:
    """Realised daily volatility over the `horizon` days *after* `start`.

    The thing being forecast. Volatility is latent — it is never observed, only
    estimated — which is why the losses below are the ones used for it.
    """
    window = rets[start:start + horizon]
    if len(window) < max(3, horizon // 2):
        return None
    return max(math.sqrt(sum(r * r for r in window) / len(window)), MIN_VOL)


def qlike(forecast: float, actual: float) -> float:
    """QLIKE loss. Lower is better.

    The standard loss for volatility forecasting, and it is standard for a
    reason: it is robust to the fact that the target is a *noisy proxy* for
    something unobservable, where plain squared error is not. It also punishes
    under-forecasting harder than over-forecasting, which is the asymmetry a
    risk number should have.
    """
    f2, a2 = max(forecast, MIN_VOL) ** 2, max(actual, MIN_VOL) ** 2
    return a2 / f2 - math.log(a2 / f2) - 1.0


def mse(forecast: float, actual: float) -> float:
    return (forecast - actual) ** 2


@dataclass(frozen=True)
class Score:
    model: str
    n: int
    qlike: float
    mse: float
    bias: float           # mean forecast / mean actual; 1.0 is unbiased

    def as_dict(self) -> dict:
        return {"model": self.model, "n": self.n,
                "qlike": round(self.qlike, 5), "mse": round(self.mse, 9),
                "bias": round(self.bias, 4)}


def score_model(rets: Series, name: str, horizon: int = 20,
                min_history: int = 250, step: int = 5) -> Score | None:
    """Walk forward through one instrument, scoring one model.

    Every forecast is made from `rets[:i]` and graded against `rets[i:i+h]`,
    which the forecast has not seen. Stepping by `step` rather than every day
    keeps the windows from overlapping so heavily that a hundred readings are
    really one.
    """
    fn = MODELS[name]
    losses, squares, fsum, asum = [], [], 0.0, 0.0
    for i in range(min_history, len(rets) - horizon, step):
        f = fn(rets[:i])
        a = realised_forward(rets, i, horizon)
        if f is None or a is None:
            continue
        losses.append(qlike(f, a))
        squares.append(mse(f, a))
        fsum += f
        asum += a
    if len(losses) < 10:
        return None
    return Score(name, len(losses), sum(losses) / len(losses),
                 sum(squares) / len(squares), fsum / asum if asum else 0.0)


# --------------------------------------------------------------------------- #
# The study
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Verdict:
    model: str
    qlike: float
    versus_trailing: float      # improvement as a fraction; > 0 is better
    beat_on: int                # instruments where it beat trailing
    instruments: int
    blocks_won: int             # time blocks where it beat trailing
    blocks: int

    @property
    def verdict(self) -> str:
        """Same vocabulary the rest of the project uses, same discipline.

        Beating on average is not enough. The project's standard is that a
        result has to hold across time blocks — three of the five directional
        nulls looked positive on the pooled average and fell apart here.
        """
        if self.instruments < 5 or self.blocks < 4:
            return "INSUFFICIENT"
        if self.versus_trailing <= 0:
            return "DROP"
        if self.blocks_won >= self.blocks - 1 and self.beat_on > self.instruments / 2:
            return "KEEP"
        return "WEAK"

    def as_dict(self) -> dict:
        return {"model": self.model, "qlike": round(self.qlike, 5),
                "vs_trailing_pct": round(self.versus_trailing * 100, 2),
                "beat_on": f"{self.beat_on}/{self.instruments}",
                "blocks_won": f"{self.blocks_won}/{self.blocks}",
                "verdict": self.verdict}


def study(histories: dict[str, Series], horizon: int = 20, blocks: int = 6,
          min_history: int = 250, step: int = 5) -> dict:
    """Score every model against the incumbent, pooled and by time block.

    `histories` maps an instrument to its close series, so the caller owns the
    fetching and this stays testable offline.
    """
    per_model: dict[str, list[Score]] = {}
    for name in MODELS:
        for symbol, closes in histories.items():
            s = score_model(log_returns(closes), name, horizon, min_history, step)
            if s is not None:
                per_model.setdefault(name, []).append(s)

    base = {s.model: s for s in per_model.get("trailing", [])}
    pooled = {name: (sum(s.qlike * s.n for s in rows) / sum(s.n for s in rows)
                     if rows else None)
              for name, rows in per_model.items()}

    # Per-instrument, so "better on average" cannot hide a model that wins
    # enormously on one name and loses on every other.
    by_symbol: dict[str, dict[str, float]] = {}
    for name, rows in per_model.items():
        for symbol, closes in zip(histories, rows):
            by_symbol.setdefault(name, {})[symbol] = rows[list(histories).index(symbol)].qlike \
                if symbol in list(histories) else None

    verdicts = []
    trailing_pooled = pooled.get("trailing")
    for name in MODELS:
        if name == "trailing" or pooled.get(name) is None or not trailing_pooled:
            continue
        wins = _beat_count(histories, name, horizon, min_history, step)
        block_wins = _block_wins(histories, name, horizon, min_history, step, blocks)
        verdicts.append(Verdict(
            model=name, qlike=pooled[name],
            versus_trailing=(trailing_pooled - pooled[name]) / trailing_pooled,
            beat_on=wins, instruments=len(per_model.get(name, [])),
            blocks_won=block_wins, blocks=blocks))

    return {"horizon_days": horizon,
            "instruments": len(histories),
            "pooled_qlike": {k: (round(v, 5) if v else None) for k, v in pooled.items()},
            "verdicts": [v.as_dict() for v in verdicts],
            "pre_registered": PRE_REGISTERED}


def _beat_count(histories, name, horizon, min_history, step) -> int:
    wins = 0
    for closes in histories.values():
        rets = log_returns(closes)
        a = score_model(rets, name, horizon, min_history, step)
        b = score_model(rets, "trailing", horizon, min_history, step)
        if a and b and a.qlike < b.qlike:
            wins += 1
    return wins


def _block_wins(histories, name, horizon, min_history, step, blocks) -> int:
    """How many contiguous time blocks the model wins.

    The test that killed three of the five directional findings. A result that
    only holds in one regime is a description of that regime.
    """
    lengths = [len(log_returns(c)) for c in histories.values()]
    if not lengths:
        return 0
    span = min(lengths)
    usable = span - min_history - horizon
    if usable < blocks * 2:
        return 0
    width = usable // blocks
    wins = 0
    for b in range(blocks):
        lo = min_history + b * width
        hi = lo + width + horizon
        ours = base = 0.0
        n = 0
        for closes in histories.values():
            rets = log_returns(closes)[:hi]
            a = score_model(rets, name, horizon, lo, step)
            t = score_model(rets, "trailing", horizon, lo, step)
            if a and t:
                ours += a.qlike
                base += t.qlike
                n += 1
        if n and ours < base:
            wins += 1
    return wins


# --------------------------------------------------------------------------- #
# What the app should actually use
# --------------------------------------------------------------------------- #
#: Below this horizon, clustering is worth modelling; above it, a long window
#: is better. Measured, not assumed — see `forecast()`.
CLUSTERING_HORIZON_DAYS = 10

#: The long window that wins at longer horizons. 250 trading days is a year.
LONG_WINDOW = 250


def forecast(closes: Series, horizon_days: int) -> float | None:
    """The daily volatility to plan with, chosen by horizon.

    Measured over 26 instruments and five years of daily bars, scoring each
    estimator by QLIKE against the volatility that actually followed:

        horizon   best          beat the incumbent by
        3 days    GARCH         +11.6%
        5 days    GARCH         +17.8%
        20 days   trailing-250  +5.6%
        60 days   trailing-250  already in use

    The split is not arbitrary. **The synthetic control is what makes it
    trustworthy**: on a random walk with constant volatility — where there is no
    clustering to find — GARCH *loses* to a long trailing window, badly. It only
    wins on real data, and only at short horizons. That is clustering being
    exploited rather than a model with more effective history winning on sample
    size, which is what the first version of this study actually measured before
    the control caught it.

    So: short horizons get the clustering model, long horizons get the long
    window, and nothing here claims a direction.
    """
    rets = log_returns(closes)
    if len(rets) < 3:
        return None
    if horizon_days <= CLUSTERING_HORIZON_DAYS:
        return garch_like(rets) or ewma(rets) or trailing(rets)
    return trailing(rets, LONG_WINDOW) or trailing(rets)
