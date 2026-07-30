"""Real-asset screener — equities, indices, forex, crypto spot, commodities.

This is an **informational screener**, built at the user's explicit request. It
shows live prices, recent momentum and volatility, matched reputable news, and a
transparent *confidence* score with a heuristic directional *lean*. Read the
same honesty rules that govern the whole project:

* **The score is not profit odds and the lean is not advice.** Unlike a
  prediction market, there is no independent "fair value" for a stock, so the
  confidence here is purely a notability/activity heuristic (momentum, volatility
  and news coverage) and the lean is the sign of (recent momentum + crude news
  sentiment). It is a computed technical indicator, transparently shown — not a
  recommendation to buy or sell, and nothing here places an order.
* **News is context and untrusted data**, matched by keyword and shown with its
  source so a human can judge it.

Data comes from Yahoo Finance's public chart endpoint (no key). A symbol that
fails to fetch is simply skipped.
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

from . import news

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh) sonar/0.3"}
_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1mo&interval=1d"

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
    ("BTC-USD", "Bitcoin", "Crypto", {"bitcoin", "btc", "crypto"}),
    ("ETH-USD", "Ethereum", "Crypto", {"ethereum", "eth", "crypto"}),
    ("GC=F", "Gold", "Commodity", {"gold", "bullion"}),
    ("CL=F", "WTI Crude", "Commodity", {"oil", "crude"}),
]

_W = {"momentum": .35, "volatility": .20, "news": .45}   # asset confidence weights


@dataclass
class AssetSuggestion:
    symbol: str
    name: str
    cls: str
    price: float
    currency: str
    day_change: float        # fractional 1-day change
    mom_5d: float            # fractional 5-day change
    volatility: float        # daily vol of log returns
    spark: list[float]       # recent closes for a mini chart
    comp: dict = field(default_factory=dict)
    confidence: float = 0.0
    lean: str = "Neutral"    # Bullish / Bearish / Neutral (heuristic, not advice)
    news_sentiment: float = 0.0
    headlines: list[dict] = field(default_factory=list)
    rationale: str = ""


def _get(url: str):
    try:
        req = urllib.request.Request(url, headers=_UA)
        return json.loads(urllib.request.urlopen(req, timeout=8).read())
    except Exception:
        return None


def _fetch(symbol: str):
    d = _get(_CHART.format(sym=urllib.parse.quote(symbol)))
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


def _match_news(headlines, kw: set[str], limit: int = 4):
    """Asset news match — curated keywords are specific, so a single hit counts
    (crypto tokens always count)."""
    scored = []
    for h in headlines:
        overlap = h._tokens & kw
        if overlap:
            scored.append((len(overlap), -h.age_hours, h))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [h for _, _, h in scored[:limit]]


class AssetScanner:
    def __init__(self, ttl: float = 120.0) -> None:
        self.ttl = ttl
        self._at = 0.0
        self._payload: dict = {"status": "starting", "assets": []}

    def payload(self, headlines) -> dict:
        now = time.time()
        if now - self._at > self.ttl or self._payload.get("status") != "live":
            self._refresh(headlines)
            self._at = now
        return self._payload

    def _refresh(self, headlines) -> None:
        out: list[AssetSuggestion] = []
        for symbol, name, cls, kw in WATCHLIST:
            got = _fetch(symbol)
            if got is None:
                continue
            price, currency, closes = got
            prev = closes[-2]                        # yesterday's daily close
            day = price / prev - 1 if prev else 0.0
            mom5 = (price / closes[-6] - 1) if len(closes) >= 6 else day
            vol = _daily_vol(closes)

            comp = {
                "momentum": round(min(1.0, abs(mom5) / 0.10), 3),   # 10%/wk -> 1
                "volatility": round(min(1.0, vol / 0.03), 3),        # 3%/day -> 1
            }
            matched = _match_news(headlines, kw)
            coverage, sentiment = news.news_signal(matched)
            comp["news"] = round(coverage, 3)

            conf = round(100 * sum(_W[k] * comp.get(k, 0.0) for k in _W), 1)
            lean = _lean(mom5, sentiment)
            s = AssetSuggestion(
                symbol=symbol, name=name, cls=cls, price=round(price, 4),
                currency=currency, day_change=round(day, 4), mom_5d=round(mom5, 4),
                volatility=round(vol, 4), spark=[round(c, 4) for c in closes[-20:]],
                comp=comp, confidence=conf, lean=lean,
                news_sentiment=round(sentiment, 3),
                headlines=[{"title": h.title, "source": h.source, "link": h.link,
                            "age_h": round(h.age_hours, 1) if h.dated else None,
                            "cat": h.category} for h in matched],
                rationale=_rationale(name, mom5, sentiment, matched),
            )
            out.append(s)

        out.sort(key=lambda x: x.confidence, reverse=True)
        self._payload = {
            "status": "live" if out else "error",
            "generated": int(time.time()),
            "n": len(out),
            "classes": sorted({s.cls for s in out}),
            "assets": [asdict(s) for s in out],
        }


def _daily_vol(closes: list[float]) -> float:
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
            if closes[i - 1] > 0]
    if len(rets) < 3:
        return 0.0
    mean = sum(rets) / len(rets)
    return math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))


def _lean(mom5: float, sentiment: float) -> str:
    score = 0.5 * (1 if mom5 > 0.005 else -1 if mom5 < -0.005 else 0) + 0.5 * sentiment
    return "Bullish" if score > 0.2 else "Bearish" if score < -0.2 else "Neutral"


def _rationale(name: str, mom5: float, sentiment: float, matched) -> str:
    bits = [f"{name} {mom5*100:+.1f}% over 5d"]
    if matched:
        tone = "positive" if sentiment > .15 else "negative" if sentiment < -.15 else "mixed"
        bits.append(f"{len(matched)} headline(s), tone {tone}")
    else:
        bits.append("no matched news")
    return "; ".join(bits)
