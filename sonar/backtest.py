"""Replay the plan over real history and count what actually happened.

The paper book answers "does the score work" eventually — but at one position
per idea it needs months to say anything. This says it today, by running the
same plan over years of real prices that have already happened.

The method
----------
For each instrument, walk historical days. At each one:

1. Compute momentum and volatility from **prior bars only**. Nothing after the
   decision date is visible — the single rule that separates a backtest from a
   flattering illusion.
2. Take the direction from momentum, exactly as the screener's lean does.
3. Build the same volatility-scaled target and stop as :mod:`sonar.scoring`.
4. Walk forward bar by bar and record which barrier is touched first, using the
   real highs and lows.

Then compare the realised hit rate against the ``1/(1+R:R)`` the barrier maths
predicts. Equal means no edge, and that is the honest null result. Higher means
momentum is doing something. It can also come out lower, which would say the
lean is actively harmful — a result the code is perfectly willing to report.

What this does *not* test
-------------------------
**News and catalysts are absent.** Historical headlines matched to a past date
are not available here, so this exercises the price-based half of the score
only. A real edge could live in the news component and this would never see it;
equally, a flat result here does not clear the news weighting. Said plainly
because a backtest that quietly measures less than it claims is worse than none.

Two more caveats, both deliberately pessimistic:

* **Daily bars hide the path.** If a bar's high reaches the target *and* its low
  reaches the stop, the order is unknowable, so it is scored a **loss**. Real
  intraday data would resolve some of those favourably.
* **No costs.** Spread, slippage and financing are all ignored, and all three
  push results down. Anything that fails to beat the baseline here would fail
  harder in reality.
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from . import scoring

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh) sonar/0.4"}
_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
          "?range={rng}&interval=1d")

# Bars of history needed before the first decision can be made.
MIN_LOOKBACK = 30
# Give a position this many horizons to resolve before calling it a timeout.
MAX_HOLD_MULTIPLE = 4


@dataclass
class Bars:
    """Daily OHLC for one instrument."""

    symbol: str
    time: list[int] = field(default_factory=list)
    open: list[float] = field(default_factory=list)
    high: list[float] = field(default_factory=list)
    low: list[float] = field(default_factory=list)
    close: list[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.close)


def fetch_bars(symbol: str, rng: str = "2y") -> Bars | None:
    """Daily OHLC from Yahoo. Rows with gaps are dropped rather than patched."""
    url = _CHART.format(sym=urllib.parse.quote(symbol), rng=rng)
    try:
        req = urllib.request.Request(url, headers=_UA)
        d = json.loads(urllib.request.urlopen(req, timeout=15).read())
        r = d["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        ts = r["timestamp"]
    except Exception:
        return None
    bars = Bars(symbol=symbol)
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        bars.time.append(t)
        bars.open.append(o)
        bars.high.append(h)
        bars.low.append(l)
        bars.close.append(c)
    return bars if len(bars) > MIN_LOOKBACK else None


def _vol(closes: list[float]) -> float:
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
            if closes[i - 1] > 0]
    if len(rets) < 3:
        return 0.0
    mean = sum(rets) / len(rets)
    return math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))


def _resolve(bars: Bars, start: int, direction: str, target: float,
             stop: float, max_bars: int) -> tuple[str, int]:
    """Walk forward and report which barrier was touched first.

    A bar that spans both barriers is scored ``STOP``: the intraday order is
    unknowable from daily data, so the unfavourable reading is the honest one.
    """
    for i in range(start + 1, min(start + 1 + max_bars, len(bars))):
        hi, lo = bars.high[i], bars.low[i]
        if direction == "LONG":
            hit_stop, hit_target = lo <= stop, hi >= target
        else:
            hit_stop, hit_target = hi >= stop, lo <= target
        if hit_stop:                      # checked first, deliberately
            return "STOP", i - start
        if hit_target:
            return "TARGET", i - start
    return "TIMEOUT", min(max_bars, len(bars) - start - 1)


def run_symbol(bars: Bars, horizon_days: int, step: int = 3,
               k_target: float = scoring.K_TARGET,
               k_stop: float = scoring.K_STOP) -> list[dict]:
    """Every decision point for one instrument."""
    out = []
    max_bars = horizon_days * MAX_HOLD_MULTIPLE
    for i in range(MIN_LOOKBACK, len(bars) - 2, step):
        past = bars.close[:i + 1]                   # inclusive of today only
        vol = _vol(past[-30:])
        if vol <= 0:
            continue
        if len(past) <= horizon_days:
            continue
        mom = past[-1] / past[-(horizon_days + 1)] - 1
        if mom == 0:
            continue
        direction = "LONG" if mom > 0 else "SHORT"
        price = past[-1]
        plan = scoring.build_plan(price, vol, horizon_days, direction,
                                  k_target=k_target, k_stop=k_stop)
        outcome, held = _resolve(bars, i, plan.direction, plan.target,
                                 plan.stop, max_bars)
        if outcome == "TIMEOUT":
            continue                                 # unresolved, not a result
        out.append({"symbol": bars.symbol, "t": bars.time[i],
                    "direction": plan.direction, "momentum": mom,
                    "vol": vol, "outcome": outcome, "bars_held": held,
                    "predicted": plan.p_profit, "rr": plan.rr})
    return out


def summarise(trials: list[dict], rr: float = scoring.K_TARGET / scoring.K_STOP) -> dict:
    """Realised hit rate against what the barrier maths predicted."""
    if not trials:
        return {"n": 0, "verdict": "no resolved trials"}
    wins = sum(1 for t in trials if t["outcome"] == "TARGET")
    n = len(trials)
    hit = wins / n
    predicted = sum(t["predicted"] for t in trials) / n
    # Standard error on a proportion — the honest error bar on the claim.
    se = math.sqrt(max(hit * (1 - hit), 1e-9) / n)
    delta = hit - predicted
    from . import calibration
    edge = calibration.implied_edge(hit, scoring.K_TARGET, scoring.K_STOP)
    significant = abs(delta) > 2 * se
    return {
        "n": n,
        "wins": wins,
        "hit_rate": round(hit, 4),
        "predicted": round(predicted, 4),
        "delta": round(delta, 4),
        "std_error": round(se, 4),
        "significant": significant,
        "implied_edge_sigma": round(edge, 4),
        "expectancy_r": round(hit * rr - (1 - hit), 4),
        "avg_bars_held": round(sum(t["bars_held"] for t in trials) / n, 1),
        "verdict": _verdict(delta, se, significant),
    }


def _verdict(delta: float, se: float, significant: bool) -> str:
    if not significant:
        return (f"Realised hit rate is within {2*se*100:.1f} points of the "
                "barrier model's prediction — no edge detected. This is what "
                "no edge is supposed to look like.")
    if delta > 0:
        return (f"Hit rate beats the prediction by {delta*100:+.1f} points, "
                f"more than two standard errors ({se*100:.1f}). Momentum is "
                "doing something here — before any costs.")
    return (f"Hit rate is {delta*100:.1f} points *below* the prediction, "
            "beyond two standard errors. Taking the lean at face value would "
            "have lost money faster than a coin flip.")


def run(symbols: list[str], horizon_days: int = 5, rng: str = "2y",
        step: int = 3, progress=None) -> dict:
    """Backtest a whole watchlist. Returns the summary plus a per-bucket view."""
    trials: list[dict] = []
    fetched = 0
    for sym in symbols:
        bars = fetch_bars(sym, rng)
        if bars is None:
            continue
        fetched += 1
        trials.extend(run_symbol(bars, horizon_days, step=step))
        if progress:
            progress(sym, len(trials))

    summary = summarise(trials)
    summary["symbols"] = fetched
    summary["horizon_days"] = horizon_days
    summary["range"] = rng
    summary["generated"] = int(time.time())
    summary["buckets"] = _momentum_buckets(trials)
    return summary


def _momentum_buckets(trials: list[dict]) -> list[dict]:
    """Does a *bigger* momentum reading win more often? The screener ranks by
    score, so this is the part of that ranking history can actually test."""
    edges = [(0.0, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 1.0)]
    out = []
    for lo, hi in edges:
        rows = [t for t in trials if lo <= abs(t["momentum"]) < hi]
        if not rows:
            continue
        wins = sum(1 for t in rows if t["outcome"] == "TARGET")
        out.append({"lo": lo, "hi": hi, "n": len(rows),
                    "hit_rate": round(wins / len(rows), 4),
                    "predicted": round(sum(t["predicted"] for t in rows) / len(rows), 4)})
    return out
