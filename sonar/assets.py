"""Real-asset screener — equities, indices, forex, crypto spot, commodities.

This is an **informational screener**, built at the user's explicit request. It
shows live prices, recent momentum and volatility, matched reputable news, and a
transparent *confidence* score. Read the same honesty rules that govern the
whole project:

* **The score is not profit odds, and no direction is asserted.** There is no
  independent "fair value" for a stock, so confidence is purely a notability
  heuristic (momentum, volatility, news coverage, scheduled catalysts).
* **The directional lean was removed, on evidence.** It used to be the sign of
  (momentum + word-list sentiment). ``sonar.backtest`` replayed it over 25,504
  independent historical setups across 113 instruments: momentum hit
  39.5 / 39.7 / 39.8 / 38.7% across its buckets against a 40.0% baseline — flat.
  A news spike came in at 40.8%, i.e. +0.8 points with a ±3.1 error bar.
  Neither carries a usable edge, so no direction is asserted and the news level
  is shown only as *notability*: something is happening here, worth a look.
  (An earlier 26-instrument run put the spike at +4.9 points. It did not
  survive the larger sample — that was noise, and it is recorded rather than
  quietly forgotten.)
* **News is context and untrusted data**, matched by keyword and shown with its
  source so a human can judge it.

Data comes from Yahoo Finance's public chart endpoint (no key). A symbol that
fails to fetch is simply skipped.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
import math
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

from . import events as events_mod
from . import horizon, news, risk, scoring

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh) sonar/0.3"}
_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
          "?range={rng}&interval=1d")

# symbol, display, class, matching keywords
WATCHLIST: list[tuple[str, str, str, set[str]]] = [
    ("AAPL", "Apple", "Equity", {"apple", "iphone"}),
    ("MSFT", "Microsoft", "Equity", {"microsoft", "copilot"}),
    ("NVDA", "Nvidia", "Equity", {"nvidia"}),
    ("TSLA", "Tesla", "Equity", {"tesla", "musk"}),
    ("AMZN", "Amazon", "Equity", {"amazon"}),
    ("GOOGL", "Alphabet", "Equity", {"google", "alphabet"}),
    ("META", "Meta", "Equity", {"meta", "facebook", "instagram", "zuckerberg"}),
    ("^GSPC", "S&P 500", "Index", {"stocks", "equities", "wall"}),
    ("^IXIC", "Nasdaq", "Index", {"nasdaq"}),
    ("^DJI", "Dow Jones", "Index", {"dow"}),
    ("EURUSD=X", "EUR/USD", "Forex", {"euro", "eurozone"}),
    ("GBPUSD=X", "GBP/USD", "Forex", {"pound", "sterling"}),
    ("USDJPY=X", "USD/JPY", "Forex", {"yen", "japan"}),
    # The ten largest non-stablecoin coins. Stablecoins are deliberately absent:
    # a screener ranking things by momentum and volatility has nothing to say
    # about an asset whose entire purpose is not to move.
    # Only BTC and ETH keep the generic "crypto" token: a story about "crypto"
    # is usually about them. Leaving it on every coin meant one broad article
    # counted as fresh coverage for nine different assets at once and pushed
    # them all into the suggestions list on nothing.
    ("BTC-USD", "Bitcoin", "Crypto", {"bitcoin", "btc", "crypto"}),
    ("ETH-USD", "Ethereum", "Crypto", {"ethereum", "eth"}),
    ("BNB-USD", "BNB", "Crypto", {"binance", "bnb"}),
    ("XRP-USD", "XRP", "Crypto", {"ripple", "xrp"}),
    ("SOL-USD", "Solana", "Crypto", {"solana"}),
    ("TRX-USD", "TRON", "Crypto", {"tron", "trx"}),
    ("DOGE-USD", "Dogecoin", "Crypto", {"dogecoin", "doge"}),
    ("ADA-USD", "Cardano", "Crypto", {"cardano", "ada"}),
    ("AVAX-USD", "Avalanche", "Crypto", {"avalanche", "avax"}),
    ("LINK-USD", "Chainlink", "Crypto", {"chainlink"}),
    # Monero trades fine and Yahoo/CoinGecko agree on its price, but Binance
    # delisted it in Feb 2024 — so it is deliberately absent from
    # CRYPTO_BINANCE below and gets no hourly up/down model.
    ("XMR-USD", "Monero", "Crypto", {"monero", "xmr"}),
    ("GC=F", "Gold", "Commodity", {"gold", "bullion"}),
    ("CL=F", "WTI Crude", "Commodity", {"oil", "crude"}),
]

# Coins whose hourly candle Binance serves directly, for the barrier model.
# Yahoo covers the screener; Binance is what the hourly up/down engine needs.
#
# Monero is absent on purpose. Binance delisted XMR in February 2024, but the
# API still answers /klines for it — with the final candle from the day it was
# delisted, frozen ever since. A delisted pair does not error, it lies quietly,
# which is worse. feeds.hourly_candle() now rejects stale candles outright so
# this cannot recur for the next coin that gets delisted.
CRYPTO_BINANCE = {
    "BTC-USD": "BTCUSDT", "ETH-USD": "ETHUSDT", "BNB-USD": "BNBUSDT",
    "XRP-USD": "XRPUSDT", "SOL-USD": "SOLUSDT", "TRX-USD": "TRXUSDT",
    "DOGE-USD": "DOGEUSDT", "ADA-USD": "ADAUSDT", "AVAX-USD": "AVAXUSDT",
    "LINK-USD": "LINKUSDT",
}

# Confidence weights. News dominates because "what is happening right now" is
# the honest thing to surface for a short hold; the catalyst term rewards a
# *scheduled* repricing inside the horizon.
_W = {"momentum": .30, "volatility": .15, "news": .35, "catalyst": .20}

# Momentum scale per lookback window: the move that saturates the score at 1.0.
# Longer windows accumulate more move, so a flat 10% would make the 1-day score
# useless and the 250-day score permanently maxed.
_MOM_SCALE = {1: 0.03, 5: 0.10, 20: 0.20, 60: 0.35, 250: 0.60}


@dataclass
class AssetSuggestion:
    symbol: str
    name: str
    cls: str
    price: float
    currency: str
    day_change: float        # fractional 1-day change
    momentum: float          # fractional change over the horizon's window
    momentum_days: int       # which window that was (1 / 5 / 20)
    volatility: float        # daily vol of log returns
    spark: list[float]       # recent closes for a mini chart
    comp: dict = field(default_factory=dict)
    confidence: float = 0.0
    lean: str = "Quiet"      # news level: Quiet/Normal/Elevated/Spike.
                             # NOT a direction — see news_level().
    news_sentiment: float = 0.0
    headlines: list[dict] = field(default_factory=list)
    rationale: str = ""
    # the tradeable plan: what you'd risk, what you'd make, and how often that
    # actually pays out. See sonar/scoring.py — with no proven edge, p_profit is
    # 1/(1+rr) and expected value is zero by construction.
    plan: dict = field(default_factory=dict)
    catalyst: dict = field(default_factory=dict)


# Yahoo tolerates this comfortably. Kept modest anyway: the point is to stop
# paying 26 round trips end to end, not to hammer a free undocumented endpoint.
FETCH_WORKERS = 8


def _get(url: str):
    try:
        req = urllib.request.Request(url, headers=_UA)
        return json.loads(urllib.request.urlopen(req, timeout=8).read())
    except Exception:
        return None


def _fetch(symbol: str, rng: str = "1mo"):
    d = _get(_CHART.format(sym=urllib.parse.quote(symbol), rng=rng))
    try:
        r = d["chart"]["result"][0]
        meta = r["meta"]
        closes = [c for c in r["indicators"]["quote"][0]["close"] if c is not None]
    except (TypeError, KeyError, IndexError):
        return None
    price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
    if price is None or len(closes) < 3:
        return None
    return price, meta.get("currency", ""), closes


# Words that name an asset but are also ordinary English. Matching on these
# alone produced real nonsense: XRP "matched" a story about diesel prices
# because it contained the phrase *ripple effect*. They now only count when the
# headline also carries a crypto-context word.
_AMBIGUOUS = {"ripple", "ada", "avalanche", "tron", "link", "solana", "doge"}
_CRYPTO_CONTEXT = {"crypto", "cryptocurrency", "blockchain", "token", "coin",
                   "bitcoin", "ethereum", "altcoin", "defi", "stablecoin",
                   "exchange", "wallet"}


def _match_news(headlines, kw: set[str], limit: int = 4):
    """Match headlines to an asset by keyword, conservatively.

    A single specific hit counts — "Nvidia" in a headline is about Nvidia. But
    an ambiguous word has to bring a chaperone: without that rule the screener
    confidently reported that XRP was in the news because someone wrote "ripple
    effect" about fuel prices.
    """
    scored = []
    for h in headlines:
        overlap = h._tokens & kw
        if not overlap:
            continue
        if overlap <= _AMBIGUOUS and not (h._tokens & _CRYPTO_CONTEXT):
            continue
        scored.append((len(overlap), -h.age_hours, h))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [h for _, _, h in scored[:limit]]


class AssetScanner:
    def __init__(self, ttl: float = 120.0, events=None) -> None:
        self.ttl = ttl
        # Shared with core.Live so the calendar is fetched once, not per scan.
        self.events = events
        # Drift, in horizon-sigmas, measured by sonar.calibration from closed
        # positions. Zero until enough have resolved — never a guess.
        self.edge_sigma = 0.0
        self.calibrated = False
        self._at = 0.0
        self._key: tuple = ()
        self._payload: dict = {"status": "starting", "assets": []}

    def payload(self, headlines, hz=None, profile=None) -> dict:
        """Cached screen. Refreshes on TTL, or immediately when the horizon or
        risk profile changes (a cached screen for a different horizon would be
        showing the wrong momentum window)."""
        hz = hz or horizon.DEFAULT
        profile = profile or risk.DEFAULT
        now = time.time()
        key = (hz.name, profile.name)
        if (now - self._at > self.ttl or key != self._key
                or self._payload.get("status") != "live"):
            self._refresh(headlines, hz, profile)
            self._at = now
            self._key = key
        return self._payload

    def _refresh(self, headlines, hz, profile) -> None:
        out: list[AssetSuggestion] = []
        days = hz.momentum_days
        scale = _MOM_SCALE.get(days, 0.10)
        # Twenty-six independent chart fetches, and the slowest part of start-up
        # by a distance: ~6s sequentially against ~1s concurrently. Only the
        # fetch is parallel — the scoring below is unchanged and still runs in
        # WATCHLIST order, because map() yields in input order. The screen is
        # therefore identical to the sequential version, just sooner.
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            fetched = list(pool.map(lambda w: _fetch(w[0], hz.chart_range),
                                    WATCHLIST))
        for (symbol, name, cls, kw), got in zip(WATCHLIST, fetched):
            if got is None:
                continue
            price, currency, closes = got
            prev = closes[-2]                        # yesterday's daily close
            day = price / prev - 1 if prev else 0.0
            # Momentum over the horizon's window, falling back to the longest
            # window the series actually supports.
            if len(closes) > days:
                mom = price / closes[-(days + 1)] - 1
            else:
                mom = day
            vol = _daily_vol(closes)

            # Risk filter: hide instruments too volatile for this appetite. A
            # visibility rule — it never changes what the score would have been.
            if vol > profile.max_daily_vol:
                continue

            comp = {
                "momentum": round(min(1.0, abs(mom) / scale), 3),
                "volatility": round(min(1.0, vol / 0.03), 3),        # 3%/day -> 1
            }
            matched = _match_news(headlines, kw)
            coverage, sentiment = news.news_signal(matched)
            comp["news"] = round(coverage, 3)

            # A scheduled event inside the horizon makes an instrument more
            # notable — never more bullish. Direction stays with momentum+news.
            cat_info: dict = {}
            earn = self.events.earnings_for(symbol) if self.events else None
            if earn is not None:
                comp["catalyst"] = round(
                    events_mod.catalyst_score(earn.days_away, days), 3)
                cat_info = {"kind": "earnings", "label": earn.label,
                            "date": earn.date, "days_away": earn.days_away,
                            "when": earn.when}

            conf = round(100 * sum(_W[k] * comp.get(k, 0.0) for k in _W), 1)
            level = news_level(matched)

            # Direction is the user's. R:R and P(profit) are identical for a
            # long and a short with symmetric barriers, so the row can show the
            # setup honestly without asserting a side — the buy and short
            # buttons build the actual plan.
            plan = scoring.build_plan(
                price, vol, days, "LONG",
                edge_sigma=self.edge_sigma, calibrated=self.calibrated)
            s = AssetSuggestion(
                symbol=symbol, name=name, cls=cls, price=round(price, 4),
                currency=currency, day_change=round(day, 4),
                momentum=round(mom, 4), momentum_days=days,
                volatility=round(vol, 4),
                # a longer window deserves a longer sparkline
                spark=[round(c, 4) for c in closes[-(60 if hz.long_horizon else 20):]],
                comp=comp, confidence=conf, lean=level,
                news_sentiment=round(sentiment, 3),
                headlines=[{"title": h.title, "source": h.source, "link": h.link,
                            "age_h": round(h.age_hours, 1) if h.dated else None,
                            "cat": h.category} for h in matched],
                rationale=_rationale(name, mom, days, sentiment, matched,
                                     cat_info),
                plan={"direction": plan.direction,
                      "entry": round(plan.entry, 4),
                      "target": round(plan.target, 4),
                      "stop": round(plan.stop, 4),
                      "rr": round(plan.rr, 2),
                      "p_profit": round(plan.p_profit, 4),
                      "ev": round(plan.ev_per_unit, 4),
                      "reward_pct": round(plan.reward_pct, 4),
                      "risk_pct": round(plan.risk_pct, 4),
                      "calibrated": plan.calibrated,
                      "grade": scoring.grade(plan.p_profit, plan.rr,
                                             plan.calibrated)},
                catalyst=cat_info,
            )
            out.append(s)

        out.sort(key=lambda x: x.confidence, reverse=True)
        self._payload = {
            "status": "live" if out else "error",
            "generated": int(time.time()),
            "n": len(out),
            "classes": sorted({s.cls for s in out}),
            "horizon": hz.as_dict(),
            "risk": profile.as_dict(),
            "assets": [asdict(s) for s in out],
        }


def _daily_vol(closes: list[float]) -> float:
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
            if closes[i - 1] > 0]
    if len(rets) < 3:
        return 0.0
    mean = sum(rets) / len(rets)
    return math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))


def news_level(matched: list) -> str:
    """How unusual today's coverage is, from the matched headlines themselves.

    Deliberately *not* derived from the ``coverage`` score: that saturates at
    two fresh headlines, so a well-followed name like Apple sat at 1.0 almost
    permanently and two-thirds of the board read "Spike". A label that fires on
    everything is worse than no label — it looks like information and is not.

    Counting instead, with recency doing the work: a spike means several
    genuinely fresh stories, not merely that the company exists.
    """
    fresh = sum(1 for h in matched if h.dated and h.age_hours < 6)
    day = sum(1 for h in matched if h.dated and h.age_hours < 24)
    if fresh >= 3:
        return "Spike"
    if fresh >= 1 or day >= 3:
        return "Elevated"
    if matched:
        return "Normal"
    return "Quiet"




def _rationale(name: str, mom: float, days: int, sentiment: float, matched,
               catalyst: dict | None = None) -> str:
    bits = [f"{name} {mom*100:+.1f}% over {days}d"]
    if matched:
        tone = "positive" if sentiment > .15 else "negative" if sentiment < -.15 else "mixed"
        bits.append(f"{len(matched)} headline(s), tone {tone}")
    else:
        bits.append("no matched news")
    if catalyst:
        bits.append(catalyst["label"])
    return "; ".join(bits)
