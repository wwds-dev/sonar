"""Assemble the panel: one row per (date, instrument), features and the future.

The rule the whole study rests on is that a row's features are computed from
bars **up to and including** its date, and its label is the return **after** it.
Nothing else touches the row. Every lookahead bug hides in the gap between
saying that and actually doing it, so the slicing here is deliberately explicit
and slightly tedious rather than clever.

Labels are forward returns standardised by trailing volatility. Raw returns
would let the most volatile instrument dominate every cross-section; dividing by
the volatility *known at the time* puts a quiet utility and a meme coin on the
same axis without using anything from the future to do it.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from .. import backtest
from . import features as feat


@dataclass
class Ctx:
    """What a feature is allowed to see: history ending at ``date``."""

    symbol: str
    date: dt.date
    closes: list[float]
    highs: list[float]
    lows: list[float]
    attention_z: float | None = None
    attention_recent: list[float] = field(default_factory=list)


@dataclass
class Row:
    date: dt.date
    symbol: str
    values: dict[str, float]
    fwd: float                  # volatility-standardised forward return
    fwd_raw: float
    # Same row, labelled at several horizons. A real signal decays smoothly as
    # the horizon lengthens; noise jumps around. Computing them together costs
    # one pass instead of four and keeps the rows identical across horizons,
    # so the comparison is like-for-like.
    fwd_h: dict[int, float] = field(default_factory=dict)
    cls: str = ""


def _sd(xs):
    if len(xs) < 3:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def build(symbols: list[str], horizon: int = 20, rng: str = "5y",
          articles: dict | None = None, min_history: int = 260,
          progress=None, horizons: list[int] | None = None,
          classes: dict | None = None) -> list[Row]:
    """Build the panel for ``symbols``.

    ``horizon`` is the forward window in trading days. Rows are emitted for
    every date with enough history behind it and enough future ahead of it —
    the overlap that creates is real and is handled in the statistics, not by
    quietly thinning the sample here.
    """
    horizons = sorted(set((horizons or [horizon]) + [horizon]))
    longest = max(horizons)
    rows: list[Row] = []
    for n, sym in enumerate(symbols, 1):
        bars = backtest.fetch_bars(sym, rng)
        if bars is None or len(bars) < min_history + longest + 5:
            continue
        att = None
        if articles and sym in articles:
            a = dt.datetime.utcfromtimestamp(bars.time[0]).strftime("%Y%m%d")
            b = dt.datetime.utcfromtimestamp(bars.time[-1]).strftime("%Y%m%d")
            att = backtest.fetch_attention(sym, a, b, articles)

        for i in range(min_history, len(bars) - longest):
            date = dt.datetime.utcfromtimestamp(bars.time[i]).date()
            # Everything up to and including i. Nothing past it, ever.
            closes = bars.close[:i + 1]
            ctx = Ctx(symbol=sym, date=date, closes=closes,
                      highs=bars.high[:i + 1], lows=bars.low[:i + 1])
            if att:
                key = date.strftime("%Y%m%d")
                ctx.attention_z = backtest.attention_z(att, key)
                days = sorted(k for k in att if k <= key)[-25:]
                ctx.attention_recent = [att[d] for d in days]

            vals = {}
            for f in feat.REGISTRY:
                try:
                    v = f.fn(ctx)
                except Exception:
                    v = None
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    vals[f.name] = float(v)
            if not vals:
                continue

            fwd_raw = bars.close[i + horizon] / bars.close[i] - 1
            trail = [math.log(closes[k] / closes[k - 1])
                     for k in range(max(1, len(closes) - 60), len(closes))
                     if closes[k - 1] > 0]
            vol = _sd(trail) * math.sqrt(horizon)
            if vol <= 0:
                continue
            per_h = {}
            for h in horizons:
                hv = _sd(trail) * math.sqrt(h)
                if hv > 0:
                    per_h[h] = (bars.close[i + h] / bars.close[i] - 1) / hv
            rows.append(Row(date=date, symbol=sym, values=vals,
                            fwd=fwd_raw / vol, fwd_raw=fwd_raw,
                            fwd_h=per_h,
                            cls=(classes or {}).get(sym, "Equity")))
        if progress:
            progress(sym, n, len(rows))
    return rows


def by_date(rows: list[Row]) -> dict[dt.date, list[Row]]:
    out: dict[dt.date, list[Row]] = {}
    for r in rows:
        out.setdefault(r.date, []).append(r)
    return out


def cross_sections(rows: list[Row], name: str, min_names: int = 8):
    """Yield ``(date, feature values, forward returns)`` per date.

    Judging a feature *within* a date is what makes this cross-sectional: the
    whole market moving on a day cancels out, and the question becomes only
    whether the feature ranked that day's names correctly. A day with too few
    instruments cannot rank anything and is skipped.
    """
    for date, group in sorted(by_date(rows).items()):
        xs, ys = [], []
        for r in group:
            v = r.values.get(name)
            if v is not None:
                xs.append(v)
                ys.append(r.fwd)
        if len(xs) >= min_names:
            yield date, xs, ys
