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

import datetime as dt
import json
import math
import time
import urllib.error
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

_PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
              "en.wikipedia/all-access/user/{art}/daily/{a}/{b}")
_WIKI_UA = {"User-Agent": "sonar-research/0.4 (personal backtest)"}

# Symbol -> English Wikipedia article, used as the historical attention proxy.
# Anything missing here simply gets no attention data and is skipped by the
# news test rather than guessed at.
WIKI_ARTICLE = {
    "AAPL": "Apple_Inc.", "MSFT": "Microsoft", "NVDA": "Nvidia",
    "TSLA": "Tesla,_Inc.", "AMZN": "Amazon_(company)", "GOOGL": "Alphabet_Inc.",
    "META": "Meta_Platforms",
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "BNB-USD": "Binance",
    "XRP-USD": "XRP_Ledger", "SOL-USD": "Solana_(blockchain_platform)",
    "TRX-USD": "Tron_(cryptocurrency)", "DOGE-USD": "Dogecoin",
    "ADA-USD": "Cardano_(blockchain_platform)",
    "AVAX-USD": "Avalanche_(blockchain_platform)",
    "LINK-USD": "Chainlink_(blockchain_oracle)", "XMR-USD": "Monero",
    "GC=F": "Gold", "CL=F": "West_Texas_Intermediate",
    "^GSPC": "S&P_500", "^IXIC": "Nasdaq_Composite",
    "^DJI": "Dow_Jones_Industrial_Average",
    "EURUSD=X": "Euro", "GBPUSD=X": "Pound_sterling", "USDJPY=X": "Japanese_yen",
}

# Days of trailing pageviews used as the "normal" baseline for a spike.
ATTENTION_WINDOW = 30


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


def fetch_attention(symbol: str, start: str, end: str,
                    articles: dict | None = None) -> dict[str, int] | None:
    """Daily Wikipedia pageviews for ``symbol``, keyed ``YYYYMMDD``.

    A stand-in for "how much is this in the news today". It is a *proxy*, and
    the difference matters: it measures attention, not coverage by the specific
    outlets SONAR reads, and it carries no tone at all. Wikipedia traffic and
    news volume move together — attention spikes are exactly what the live
    ``coverage`` component is built to detect — but this tests the idea, not
    the implementation.
    """
    art = (articles or {}).get(symbol) or WIKI_ARTICLE.get(symbol)
    if not art:
        return None
    url = _PAGEVIEWS.format(art=urllib.parse.quote(art, safe=""), a=start, b=end)
    for attempt in range(3):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=_WIKI_UA)
            d = json.loads(urllib.request.urlopen(req, timeout=25).read())
            return {i["timestamp"][:8]: i["views"] for i in d.get("items", [])}
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                # Backing off matters more than it looks: a swallowed 429 is
                # indistinguishable from "this symbol has no article", which
                # would quietly turn the entire news test into "untested".
                time.sleep(2.0 * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    return None


_last_wiki_call = 0.0
# Wikimedia asks for considerate request rates and enforces it with 429s.
WIKI_MIN_INTERVAL = 0.35


def _throttle() -> None:
    global _last_wiki_call
    wait = WIKI_MIN_INTERVAL - (time.time() - _last_wiki_call)
    if wait > 0:
        time.sleep(wait)
    _last_wiki_call = time.time()


def attention_z(views: dict[str, int], day: str,
                window: int = ATTENTION_WINDOW) -> float | None:
    """How unusual is today's attention, in standard deviations?

    Compared against the *preceding* ``window`` days only — a spike must be
    detectable on the day, not with hindsight.
    """
    days = sorted(views)
    try:
        i = days.index(day)
    except ValueError:
        return None
    if i < window:
        return None
    past = [views[d] for d in days[i - window:i]]
    mean = sum(past) / len(past)
    var = sum((v - mean) ** 2 for v in past) / (len(past) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return None
    return (views[day] - mean) / sd


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
               k_stop: float = scoring.K_STOP,
               attention: dict[str, int] | None = None) -> list[dict]:
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
        row = {"symbol": bars.symbol, "t": bars.time[i],
               "direction": plan.direction, "momentum": mom,
               "vol": vol, "outcome": outcome, "bars_held": held,
               "predicted": plan.p_profit, "rr": plan.rr, "attention": None}
        if attention:
            day = dt.datetime.utcfromtimestamp(bars.time[i]).strftime("%Y%m%d")
            row["attention"] = attention_z(attention, day)
        out.append(row)
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
        step: int = 3, progress=None, with_news: bool = False,
        articles: dict | None = None) -> dict:
    """Backtest a whole watchlist. Returns the summary plus per-bucket views.

    ``with_news`` additionally pulls a historical attention series per symbol,
    so the news component is tested rather than assumed. One extra request per
    instrument.
    """
    trials: list[dict] = []
    fetched = 0
    with_attention = 0
    for sym in symbols:
        bars = fetch_bars(sym, rng)
        if bars is None:
            continue
        fetched += 1
        att = None
        if with_news and bars.time:
            a = dt.datetime.utcfromtimestamp(bars.time[0]).strftime("%Y%m%d")
            b = dt.datetime.utcfromtimestamp(bars.time[-1]).strftime("%Y%m%d")
            att = fetch_attention(sym, a, b, articles)
            if att:
                with_attention += 1
        trials.extend(run_symbol(bars, horizon_days, step=step, attention=att))
        if progress:
            progress(sym, len(trials))

    summary = summarise(trials)
    summary["symbols"] = fetched
    summary["horizon_days"] = horizon_days
    summary["range"] = rng
    summary["generated"] = int(time.time())
    summary["buckets"] = _momentum_buckets(trials)
    summary["attention_symbols"] = with_attention
    summary["attention_buckets"] = _attention_buckets(trials)
    summary["news_verdict"] = _news_verdict(summary["attention_buckets"])
    summary["timing"] = timing(trials)
    return summary


def _attention_buckets(trials: list[dict]) -> list[dict]:
    """Does an attention spike change the odds?

    This is the news component on trial. If a spike carried information the
    high-attention bucket would beat the barrier model's prediction; if it is
    noise, every bucket sits on the same number.
    """
    rows = [t for t in trials if t.get("attention") is not None]
    if not rows:
        return []
    edges = [(-99.0, 0.0, "below normal"), (0.0, 1.0, "normal"),
             (1.0, 2.0, "elevated"), (2.0, 99.0, "spike")]
    out = []
    for lo, hi, name in edges:
        sel = [t for t in rows if lo <= t["attention"] < hi]
        if len(sel) < 30:
            continue
        wins = sum(1 for t in sel if t["outcome"] == "TARGET")
        hit = wins / len(sel)
        pred = sum(t["predicted"] for t in sel) / len(sel)
        se = math.sqrt(max(hit * (1 - hit), 1e-9) / len(sel))
        out.append({"name": name, "lo": lo, "hi": hi, "n": len(sel),
                    "hit_rate": round(hit, 4), "predicted": round(pred, 4),
                    "delta": round(hit - pred, 4), "std_error": round(se, 4),
                    "significant": abs(hit - pred) > 2 * se})
    return out


def _news_verdict(buckets: list[dict]) -> str:
    if not buckets:
        return "No attention data — the news component is untested, not cleared."
    live = [b for b in buckets if b["significant"]]
    spike = next((b for b in buckets if b["name"] == "spike"), None)
    if not live:
        return ("Attention makes no difference: every bucket lands within two "
                "standard errors of the barrier model. A news spike changed "
                "nothing about which barrier got hit first.")
    parts = [f'{b["name"]} {b["delta"]*100:+.1f} pts (n={b["n"]})' for b in live]
    lead = ("A news spike shifts the odds: "
            if spike and spike["significant"] else
            "Some attention levels shift the odds: ")
    return lead + "; ".join(parts) + " — beyond two standard errors."


def timing(trials: list[dict]) -> dict:
    """What history says about *when* — entry weekday and holding time.

    Both questions people most want answered ("which day should I buy",
    "when do I sell") get measured here rather than asserted. The weekday test
    is the one likely to disappoint: if entry day mattered, a hit rate would
    stand out, and a flat table is the honest answer that it does not.

    Holding time is the useful half. The plan's exit is already exact — the
    target and the stop are prices, not dates — so the practical question is
    how long that usually takes, which is a distribution, not a promise.
    """
    if not trials:
        return {}
    dows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    by_dow = []
    for i, name in enumerate(dows):
        sel = [t for t in trials
               if dt.datetime.utcfromtimestamp(t["t"]).weekday() == i]
        if len(sel) < 30:
            continue
        wins = sum(1 for t in sel if t["outcome"] == "TARGET")
        hit = wins / len(sel)
        se = math.sqrt(max(hit * (1 - hit), 1e-9) / len(sel))
        by_dow.append({"day": name, "n": len(sel), "hit_rate": round(hit, 4),
                       "std_error": round(se, 4)})

    held = sorted(t["bars_held"] for t in trials)
    winners = sorted(t["bars_held"] for t in trials if t["outcome"] == "TARGET")
    losers = sorted(t["bars_held"] for t in trials if t["outcome"] == "STOP")

    def pct(xs, q):
        return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None

    spread = ((max(b["hit_rate"] for b in by_dow) -
               min(b["hit_rate"] for b in by_dow)) if by_dow else 0.0)
    worst_se = max((b["std_error"] for b in by_dow), default=0.0)
    # Seven days tested means seven chances to be fooled: at a 2-sigma bar,
    # roughly one run in three throws up a "significant" day from noise alone.
    # The first version of this test duly announced Thursday at 49% — which
    # then reversed in commodities and ranged from 64% to 29% across symbols.
    # So the bar is Bonferroni-style and deliberately hard to clear.
    bonferroni = 4.0
    return {
        "by_weekday": by_dow,
        "weekday_spread": round(spread, 4),
        "weekday_matters": spread > bonferroni * 2 * worst_se,
        "weekday_note": (
            "Entry weekday shows no reliable effect. An apparent Thursday\n"
            "edge did not survive: commodities reversed it and per-symbol\n"
            "hit rates ranged from 64% to 29%. Seven days tested means\n"
            "seven chances at a false positive, and no mechanism explains\n"
            "why a weekday would matter. Treat entry day as irrelevant."),
        "hold_median": pct(held, 0.5),
        "hold_p25": pct(held, 0.25),
        "hold_p75": pct(held, 0.75),
        "hold_median_win": pct(winners, 0.5),
        "hold_median_loss": pct(losers, 0.5),
    }


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
