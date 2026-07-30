"""Live market data feeds for SONAR.

Everything here is *real* public data:

* BTC spot price and the current hourly OHLC candle come from Binance
  (``BTCUSDT``), which is the actual resolution source Polymarket uses for its
  hourly "Bitcoin Up or Down" markets. Coinbase (``BTC-USD``) is a fallback if
  Binance is unreachable.
* The current hourly prediction market — implied P(up), best bid/ask and the
  live order book — comes from Polymarket's public Gamma + CLOB APIs.

No API keys, no auth, read-only. Network failures degrade gracefully: a caller
that gets ``None`` back should keep its previous value rather than crash.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
_UA = {"User-Agent": "sonar/0.1 (paper-trading demo)"}

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
BINANCE = "https://api.binance.com/api/v3"
COINBASE = "https://api.coinbase.com/v2"


def _get(url: str, timeout: float = 8.0):
    """GET + parse JSON, returning ``None`` on any network/parse failure."""
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


# --------------------------------------------------------------------------- #
# BTC price + current hourly candle
# --------------------------------------------------------------------------- #
@dataclass
class Candle:
    """The hourly candle currently in progress (the one markets bet on)."""

    open: float
    price: float          # latest trade price (the provisional close)
    high: float
    low: float
    open_time: int        # unix seconds, top of the hour
    source: str

    @property
    def change(self) -> float:
        return self.price - self.open

    @property
    def change_pct(self) -> float:
        return (self.price / self.open - 1.0) * 100.0 if self.open else 0.0

    @property
    def is_up(self) -> bool:
        return self.price >= self.open


def _binance_hour(symbol: str = "BTCUSDT") -> Candle | None:
    rows = _get(f"{BINANCE}/klines?symbol={symbol}&interval=1h&limit=1")
    if not rows:
        return None
    o, h, l, c = (float(rows[0][i]) for i in (1, 2, 3, 4))
    label = symbol.replace("USDT", "/USDT")
    return Candle(open=o, price=c, high=h, low=l,
                  open_time=int(rows[0][0]) // 1000, source=f"Binance {label}")


def _coinbase_hour() -> Candle | None:
    """Reconstruct the current hour from Coinbase 1h candles."""
    rows = _get(f"https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=3600")
    if not rows:
        return None
    now_hr = int(time.time()) // 3600 * 3600
    row = next((r for r in rows if int(r[0]) == now_hr), rows[0])
    # coinbase candle: [time, low, high, open, close, volume]
    return Candle(open=float(row[3]), price=float(row[4]), high=float(row[2]),
                  low=float(row[1]), open_time=int(row[0]), source="Coinbase BTC-USD")


def hourly_candle(symbol: str = "BTCUSDT") -> Candle | None:
    c = _binance_hour(symbol)
    if c is not None:
        return c
    return _coinbase_hour() if symbol == "BTCUSDT" else None


def recent_hourly_returns(symbol: str = "BTCUSDT", limit: int = 72) -> list[float]:
    """Log-returns of the last ``limit`` closed hourly candles — used to
    estimate realised volatility. Falls back to a reasonable default if the
    feed is unavailable."""
    rows = _get(f"{BINANCE}/klines?symbol={symbol}&interval=1h&limit={limit + 1}")
    if not rows or len(rows) < 3:
        return []
    import math
    closes = [float(r[4]) for r in rows]
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
            if closes[i - 1] > 0]


# --------------------------------------------------------------------------- #
# Polymarket hourly market
# --------------------------------------------------------------------------- #
@dataclass
class MarketBook:
    slug: str
    title: str
    implied_up: float                 # market P(up), 0..1 (midpoint of "Up")
    best_bid: float
    best_ask: float
    end_time: int                     # unix seconds
    volume: float
    up_token: str
    bids: list[tuple[float, float]] = field(default_factory=list)  # (price, size)
    asks: list[tuple[float, float]] = field(default_factory=list)


def _hour_slug(dt_et: datetime) -> str:
    hour = dt_et.strftime("%-I%p").lower()          # e.g. "7pm"
    month = dt_et.strftime("%B").lower()
    return f"bitcoin-up-or-down-{month}-{dt_et.day}-{dt_et.year}-{hour}-et"


def current_market() -> MarketBook | None:
    """The Polymarket hourly market whose candle is in progress right now."""
    now_et = datetime.now(ET)
    ev = _get(f"{GAMMA}/events?slug={_hour_slug(now_et)}")
    if not ev:
        # fall back to the soonest-ending open market in the series
        ev = _get(f"{GAMMA}/events?series_slug=btc-up-or-down-hourly"
                  f"&closed=false&limit=1&order=endDate&ascending=true")
    if not ev:
        return None
    event = ev[0]
    markets = event.get("markets") or []
    if not markets:
        return None
    m = markets[0]

    try:
        up_token = json.loads(m["clobTokenIds"])[0]
    except (KeyError, ValueError, IndexError):
        up_token = ""

    implied = _midpoint(up_token, m)
    end_time = _iso_to_unix(m.get("endDate") or event.get("endDate"))
    book = MarketBook(
        slug=event.get("slug", ""),
        title=event.get("title", "Bitcoin Up or Down"),
        implied_up=implied,
        best_bid=_f(m.get("bestBid")),
        best_ask=_f(m.get("bestAsk")),
        end_time=end_time,
        volume=_f(m.get("volumeNum") or event.get("volume")),
        up_token=up_token,
    )
    _fill_book(book)
    return book


def _midpoint(token: str, market: dict) -> float:
    if token:
        mid = _get(f"{CLOB}/midpoint?token_id={token}")
        if mid and "mid" in mid:
            return _f(mid["mid"])
    try:
        return _f(json.loads(market.get("outcomePrices", "[]"))[0])
    except (ValueError, IndexError):
        return 0.5


def _fill_book(book: MarketBook, depth: int = 12) -> None:
    if not book.up_token:
        return
    data = _get(f"{CLOB}/book?token_id={book.up_token}")
    if not data:
        return
    bids = sorted(((_f(b["price"]), _f(b["size"])) for b in data.get("bids", [])),
                  key=lambda x: -x[0])[:depth]
    asks = sorted(((_f(a["price"]), _f(a["size"])) for a in data.get("asks", [])),
                  key=lambda x: x[0])[:depth]
    book.bids, book.asks = bids, asks


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _f(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _iso_to_unix(iso: str | None) -> int:
    if not iso:
        return int(time.time()) // 3600 * 3600 + 3600
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00"))
                   .replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return int(time.time())


def historical_decision_points(hours: int = 36, decision_minute: int = 40,
                               vol_window: int = 24) -> list[dict]:
    """Real per-hour data for the honest fair-odds warm-up backtest.

    For each of the last ``hours`` closed hours we capture the actual price at
    ``decision_minute`` past the top (from 1-minute candles), the hour's real
    open/close, the remaining-time fraction ``tau``, and a *causal* volatility
    estimate (only hours strictly earlier). No fabricated data.
    """
    import math

    span = hours + vol_window + 2
    kl = _get(f"{BINANCE}/klines?symbol=BTCUSDT&interval=1h&limit={span}")
    if not kl or len(kl) < vol_window + 5:
        return []
    hourly = [{"t": int(r[0]) // 1000, "open": float(r[1]), "close": float(r[4])}
              for r in kl[:-1]]                       # drop the in-progress hour

    # minute closes keyed by minute-open unix seconds
    first_ms = hourly[-hours]["t"] * 1000
    minute_close: dict[int, float] = {}
    cursor = first_ms
    for _ in range(6):                                # up to 6k minutes of paging
        rows = _get(f"{BINANCE}/klines?symbol=BTCUSDT&interval=1m"
                    f"&startTime={cursor}&limit=1000")
        if not rows:
            break
        for r in rows:
            minute_close[int(r[0]) // 1000] = float(r[4])
        cursor = int(rows[-1][0]) + 60_000
        if cursor > (hourly[-1]["t"] + 3600) * 1000:
            break

    closes = [h["close"] for h in hourly]
    out = []
    for i in range(len(hourly) - hours, len(hourly)):
        h = hourly[i]
        dec_price = minute_close.get(h["t"] + decision_minute * 60)
        if dec_price is None:
            continue
        prior = closes[max(0, i - vol_window):i]
        rets = [math.log(prior[j] / prior[j - 1]) for j in range(1, len(prior))
                if prior[j - 1] > 0]
        sigma = (math.sqrt(sum((x - sum(rets) / len(rets)) ** 2 for x in rets)
                           / (len(rets) - 1)) if len(rets) > 3 else 0.0045)
        out.append({"open_time": h["t"], "open": h["open"], "close": h["close"],
                    "price": dec_price, "tau": 1 - decision_minute / 60.0,
                    "sigma": sigma, "title": "backtest"})
    return out


@dataclass
class ScanMarket:
    """A lightweight snapshot of one Polymarket market for the scanner."""

    id: str
    question: str
    slug: str
    yes_price: float          # implied prob of the first outcome (0..1)
    best_bid: float
    best_ask: float
    volume24h: float
    liquidity: float
    end_time: int             # unix seconds
    mom_1h: float             # oneHourPriceChange (signed)
    mom_1d: float             # oneDayPriceChange (signed)
    outcomes: list[str]       # e.g. ["Yes","No"] or ["Up","Down"]

    @property
    def crypto_asset(self) -> str | None:
        """'BTCUSDT'/'ETHUSDT' if this is a crypto up-or-down market, else None."""
        s = self.slug.lower()
        if "up-or-down" not in s and "updown" not in s:
            return None
        if "bitcoin" in s or s.startswith("btc"):
            return "BTCUSDT"
        if "ethereum" in s or s.startswith("eth"):
            return "ETHUSDT"
        return None


def scan_markets(top: int = 120, closing: int = 60,
                 min_liquidity: float = 1000.0) -> list[ScanMarket]:
    """Scan many active Polymarket markets across every category.

    Pulls the highest 24h-volume markets and the soonest-resolving ones, merges
    them, and keeps those with genuine two-sided uncertainty (mid not pinned to
    0 or 1) and a liquidity floor. One or two Gamma calls, no per-market fetches.
    """
    seen: dict[str, ScanMarket] = {}
    urls = [
        f"{GAMMA}/markets?active=true&closed=false&archived=false"
        f"&order=volume24hr&ascending=false&limit={top}",
        f"{GAMMA}/markets?active=true&closed=false&archived=false"
        f"&order=endDate&ascending=true&limit={closing}",
    ]
    for url in urls:
        rows = _get(url) or []
        for m in rows:
            sm = _to_scan_market(m)
            if sm is None or sm.id in seen:
                continue
            mid = sm.yes_price
            if not (0.03 <= mid <= 0.97):          # skip already-decided markets
                continue
            if sm.liquidity < min_liquidity and abs(sm.mom_1d) < 0.05:
                continue                            # too thin and not moving
            if sm.end_time <= int(time.time()):
                continue
            seen[sm.id] = sm
    return list(seen.values())


def _to_scan_market(m: dict) -> ScanMarket | None:
    try:
        prices = json.loads(m.get("outcomePrices") or "[]")
        outs = json.loads(m.get("outcomes") or "[]")
    except ValueError:
        return None
    if not prices:
        return None
    if not m.get("enableOrderBook", True):
        return None
    return ScanMarket(
        id=str(m.get("id") or m.get("conditionId") or m.get("slug")),
        question=m.get("question", "") or m.get("groupItemTitle", ""),
        slug=m.get("slug", ""),
        yes_price=_f(prices[0]),
        best_bid=_f(m.get("bestBid")),
        best_ask=_f(m.get("bestAsk")),
        volume24h=_f(m.get("volume24hr")),
        liquidity=_f(m.get("liquidity") or m.get("liquidityNum")),
        end_time=_iso_to_unix(m.get("endDate")),
        mom_1h=_f(m.get("oneHourPriceChange")),
        mom_1d=_f(m.get("oneDayPriceChange")),
        outcomes=[str(o) for o in outs] or ["Yes", "No"],
    )


if __name__ == "__main__":  # quick manual smoke test
    c = hourly_candle()
    print("candle:", c)
    print("vol samples:", len(recent_hourly_returns()))
    print("market:", current_market())
