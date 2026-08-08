"""Point-in-time features: everything knowable on day *t*, and nothing else.

Every function here takes a history that ends at the decision date and returns
one number. That constraint is the whole game — a single feature that peeks one
bar into the future will manufacture an edge out of nothing, and it will look
entirely plausible while doing it.

The families are deliberately broad, because the interesting scientific question
is not "does momentum work" (it does not, we measured it) but "does *anything*
in this space carry information once you test honestly". So: price statistics,
higher moments, long-memory estimates, cross-sectional position, the calendar,
macro regime, and attention.

Each feature is registered with a **pre-registered direction**: the sign the
literature or plain reasoning says it should have. Recording that in advance is
what stops a negative result being quietly reinterpreted as a positive one with
the sign flipped — which is the most common way a backtest lies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

Series = list[float]


@dataclass(frozen=True)
class Feature:
    name: str
    family: str
    fn: Callable
    expected: int          # +1 predicts higher returns, -1 lower, 0 no prior
    rationale: str


REGISTRY: list[Feature] = []


def feature(name: str, family: str, expected: int, rationale: str):
    def wrap(fn):
        REGISTRY.append(Feature(name, family, fn, expected, rationale))
        return fn
    return wrap


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _rets(closes: Series) -> Series:
    return [math.log(closes[i] / closes[i - 1])
            for i in range(1, len(closes)) if closes[i - 1] > 0]


def _mean(xs: Series) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _sd(xs: Series) -> float:
    if len(xs) < 3:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# --------------------------------------------------------------------------- #
# price statistics
# --------------------------------------------------------------------------- #
@feature("mom_5", "price", +1, "Short momentum; the classic continuation effect.")
def mom_5(ctx) -> float | None:
    c = ctx.closes
    return c[-1] / c[-6] - 1 if len(c) > 6 else None


@feature("mom_20", "price", +1,
         "One-month momentum — short enough to still be contaminated by "
         "the reversal effect, which is why the 12-month version skips it.")
def mom_20(ctx) -> float | None:
    c = ctx.closes
    return c[-1] / c[-21] - 1 if len(c) > 21 else None


@feature("mom_60", "price", +1,
         "Quarter momentum: the horizon most of the cross-sectional "
         "momentum literature is built on.")
def mom_60(ctx) -> float | None:
    c = ctx.closes
    return c[-1] / c[-61] - 1 if len(c) > 61 else None


@feature("mom_250_ex1m", "price", +1,
         "Twelve-month momentum skipping the last month, the standard "
         "construction — the skip is what separates it from short reversal.")
def mom_250_ex1m(ctx) -> float | None:
    c = ctx.closes
    return c[-21] / c[-251] - 1 if len(c) > 251 else None


@feature("reversal_1", "price", -1,
         "Yesterday's move; short-horizon reversal says it partly unwinds.")
def reversal_1(ctx) -> float | None:
    c = ctx.closes
    return c[-1] / c[-2] - 1 if len(c) > 2 else None


@feature("reversal_5", "price", -1,
         "One-week reversal — liquidity provision earns a premium for "
         "taking the other side of a short sharp move.")
def reversal_5(ctx) -> float | None:
    c = ctx.closes
    return -(c[-1] / c[-6] - 1) if len(c) > 6 else None


@feature("dist_52w_high", "price", +1,
         "Proximity to the 52-week high; the 'nearness to high' anomaly.")
def dist_52w_high(ctx) -> float | None:
    c = ctx.closes[-250:]
    return c[-1] / max(c) - 1 if len(c) > 60 else None


# --------------------------------------------------------------------------- #
# risk and higher moments
# --------------------------------------------------------------------------- #
@feature("vol_20", "risk", -1,
         "Realised volatility. The low-volatility anomaly says calmer names do "
         "better risk-adjusted, so the prior is negative.")
def vol_20(ctx) -> float | None:
    r = _rets(ctx.closes[-21:])
    return _sd(r) if len(r) > 5 else None


@feature("vol_ratio", "risk", -1,
         "Short vol over long vol: is this name heating up relative to itself?")
def vol_ratio(ctx) -> float | None:
    short, long = _rets(ctx.closes[-11:]), _rets(ctx.closes[-61:])
    if len(short) < 5 or len(long) < 30:
        return None
    sl = _sd(long)
    return _sd(short) / sl if sl > 0 else None


@feature("skew_60", "risk", -1,
         "Return skewness. Lottery-like positive skew is associated with "
         "lower subsequent returns.")
def skew_60(ctx) -> float | None:
    r = _rets(ctx.closes[-61:])
    if len(r) < 30:
        return None
    s = _sd(r)
    if s <= 0:
        return None
    m = _mean(r)
    return sum(((x - m) / s) ** 3 for x in r) / len(r)


@feature("kurt_60", "risk", 0,
         "Tail fatness. Included without a directional prior: it plausibly "
         "matters for risk, but nothing says which way for returns.")
def kurt_60(ctx) -> float | None:
    r = _rets(ctx.closes[-61:])
    if len(r) < 30:
        return None
    s = _sd(r)
    if s <= 0:
        return None
    m = _mean(r)
    return sum(((x - m) / s) ** 4 for x in r) / len(r) - 3.0


@feature("max_dd_60", "risk", +1,
         "Depth of the worst drawdown in the window; a rebound proxy.")
def max_dd_60(ctx) -> float | None:
    c = ctx.closes[-61:]
    if len(c) < 30:
        return None
    peak, worst = c[0], 0.0
    for x in c:
        peak = max(peak, x)
        worst = min(worst, x / peak - 1)
    return worst


# --------------------------------------------------------------------------- #
# long memory and structure
# --------------------------------------------------------------------------- #
@feature("hurst_60", "structure", 0,
         "Rescaled-range Hurst exponent: >0.5 trending, <0.5 mean-reverting. "
         "A regime descriptor rather than a directional signal.")
def hurst_60(ctx) -> float | None:
    r = _rets(ctx.closes[-61:])
    if len(r) < 40:
        return None
    out = []
    for n in (10, 20, 40):
        chunks = [r[i:i + n] for i in range(0, len(r) - n + 1, n)]
        rs = []
        for ch in chunks:
            m = _mean(ch)
            dev, cum = 0.0, []
            for x in ch:
                dev += x - m
                cum.append(dev)
            spread = max(cum) - min(cum)
            s = _sd(ch)
            if s > 0 and spread > 0:
                rs.append(spread / s)
        if rs:
            out.append((math.log(n), math.log(_mean(rs))))
    if len(out) < 2:
        return None
    xs = [p[0] for p in out]
    ys = [p[1] for p in out]
    mx, my = _mean(xs), _mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else None


@feature("autocorr_1", "structure", 0,
         "Lag-1 autocorrelation of returns — direct evidence of trending or "
         "reverting behaviour in this name right now.")
def autocorr_1(ctx) -> float | None:
    r = _rets(ctx.closes[-61:])
    if len(r) < 30:
        return None
    m = _mean(r)
    num = sum((r[i] - m) * (r[i - 1] - m) for i in range(1, len(r)))
    den = sum((x - m) ** 2 for x in r)
    return num / den if den > 0 else None


# --------------------------------------------------------------------------- #
# calendar
# --------------------------------------------------------------------------- #
@feature("turn_of_month", "calendar", +1,
         "Turn-of-month effect: flows cluster around month boundaries.")
def turn_of_month(ctx) -> float | None:
    d = ctx.date.day
    return 1.0 if (d >= 28 or d <= 3) else 0.0


@feature("month_of_year", "calendar", 0,
         "Seasonality, encoded as a raw month number. Included mostly as a "
         "control: if this 'works', the pipeline is overfitting.")
def month_of_year(ctx) -> float | None:
    return float(ctx.date.month)


# --------------------------------------------------------------------------- #
# attention
# --------------------------------------------------------------------------- #
@feature("attention_z", "attention", +1,
         "Wikipedia pageviews against their own trailing baseline — the "
         "attention spike measure. Already found flat on binary outcomes; "
         "re-tested here with far more statistical power.")
def attention_z(ctx) -> float | None:
    return ctx.attention_z


@feature("attention_trend", "attention", +1,
         "Whether attention is building rather than spiking once.")
def attention_trend(ctx) -> float | None:
    a = ctx.attention_recent
    if not a or len(a) < 20:
        return None
    recent, base = _mean(a[-5:]), _mean(a[-20:-5])
    return recent / base - 1 if base > 0 else None


# --------------------------------------------------------------------------- #
# noise controls — these MUST fail
# --------------------------------------------------------------------------- #
@feature("random_control", "control", 0,
         "A deterministic pseudo-random number keyed to symbol and date. It "
         "cannot predict anything. If it ever shows up as significant, the "
         "multiple-testing correction is broken and every other result on the "
         "page is void.")
def random_control(ctx) -> float | None:
    h = hash((ctx.symbol, ctx.date.toordinal())) & 0xFFFFFFFF
    return (h / 0xFFFFFFFF) - 0.5


@feature("price_level", "control", 0,
         "The raw share price. Should carry nothing once returns are the "
         "outcome; a second canary for a leaking pipeline.")
def price_level(ctx) -> float | None:
    return math.log(ctx.closes[-1]) if ctx.closes[-1] > 0 else None


def by_family() -> dict[str, list[Feature]]:
    out: dict[str, list[Feature]] = {}
    for f in REGISTRY:
        out.setdefault(f.family, []).append(f)
    return out
