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
from . import horizon, news, risk, scoring, volatility

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh) sonar/0.3"}
_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
          "?range={rng}&interval=1d")

# symbol, display, class, matching keywords
WATCHLIST: list[tuple[str, str, str, set[str]]] = [
    # 130 instruments across five classes, every symbol verified to return a
    # year of daily closes before being added. Grown from 26 in Sep 2026: at
    # that size Index, Forex and Commodity held 3, 3 and 2 members, and a
    # cross-sectional statistic over two instruments is not a standardisation —
    # which is what blocked z-scoring within class (SUGGESTIONS #11/#12).
    #
    # MATIC-USD is deliberately absent: it was rebranded and the ticker now
    # returns nothing, which is the failure mode this list is verified against.
    ("AAPL", "Apple", "Equity", {"apple", "iphone"}),
    ("MSFT", "Microsoft", "Equity", {"azure", "copilot", "microsoft"}),
    ("NVDA", "Nvidia", "Equity", {"nvidia"}),
    ("TSLA", "Tesla", "Equity", {"musk", "tesla"}),
    ("AMZN", "Amazon", "Equity", {"amazon"}),
    ("GOOGL", "Alphabet", "Equity", {"alphabet", "google"}),
    ("META", "Meta", "Equity", {"facebook", "instagram", "meta", "zuckerberg"}),
    ("BRK-B", "Berkshire Hathaway", "Equity", {"berkshire", "buffett"}),
    ("JPM", "JPMorgan", "Equity", {"dimon", "jpmorgan"}),
    ("V", "Visa", "Equity", {"visa"}),
    ("UNH", "UnitedHealth", "Equity", {"unitedhealth"}),
    ("XOM", "Exxon Mobil", "Equity", {"exxon"}),
    ("JNJ", "Johnson & Johnson", "Equity", {"johnson & johnson"}),
    ("WMT", "Walmart", "Equity", {"walmart"}),
    ("MA", "Mastercard", "Equity", {"mastercard"}),
    ("PG", "Procter & Gamble", "Equity", {"procter"}),
    ("HD", "Home Depot", "Equity", {"home depot"}),
    ("CVX", "Chevron", "Equity", {"chevron"}),
    ("ABBV", "AbbVie", "Equity", {"abbvie"}),
    ("KO", "Coca-Cola", "Equity", {"coca-cola"}),
    ("PEP", "PepsiCo", "Equity", {"pepsi"}),
    ("BAC", "Bank of America", "Equity", {"bank of america"}),
    ("AVGO", "Broadcom", "Equity", {"broadcom"}),
    ("LLY", "Eli Lilly", "Equity", {"eli lilly", "zepbound"}),
    ("MRK", "Merck", "Equity", {"merck"}),
    ("COST", "Costco", "Equity", {"costco"}),
    ("ADBE", "Adobe", "Equity", {"adobe"}),
    ("CRM", "Salesforce", "Equity", {"salesforce"}),
    ("AMD", "AMD", "Equity", {"amd"}),
    ("NFLX", "Netflix", "Equity", {"netflix"}),
    ("INTC", "Intel", "Equity", {"intel"}),
    ("DIS", "Disney", "Equity", {"disney"}),
    ("CSCO", "Cisco", "Equity", {"cisco"}),
    ("ORCL", "Oracle", "Equity", {"oracle"}),
    ("QCOM", "Qualcomm", "Equity", {"qualcomm"}),
    ("T", "AT&T", "Equity", {"at&t"}),
    ("PFE", "Pfizer", "Equity", {"pfizer"}),
    ("NKE", "Nike", "Equity", {"nike"}),
    ("BA", "Boeing", "Equity", {"boeing"}),
    ("GS", "Goldman Sachs", "Equity", {"goldman"}),
    ("CAT", "Caterpillar", "Equity", {"caterpillar"}),
    ("MCD", "McDonald's", "Equity", {"mcdonald"}),
    ("IBM", "IBM", "Equity", {"ibm"}),
    ("SAP", "SAP", "Equity", {"sap"}),
    ("ASML", "ASML", "Equity", {"asml"}),
    ("TSM", "TSMC", "Equity", {"taiwan semi", "tsmc"}),
    ("BABA", "Alibaba", "Equity", {"alibaba"}),
    ("NVO", "Novo Nordisk", "Equity", {"novo nordisk", "ozempic", "wegovy"}),
    ("SHEL", "Shell", "Equity", {"shell"}),
    ("TM", "Toyota", "Equity", {"toyota"}),
    ("^GSPC", "S&P 500", "Index", {"equities", "s&p", "stocks", "wall street"}),
    ("^IXIC", "Nasdaq", "Index", {"nasdaq"}),
    ("^DJI", "Dow Jones", "Index", {"dow jones"}),
    ("^RUT", "Russell 2000", "Index", {"russell", "small cap"}),
    ("^VIX", "VIX", "Index", {"vix", "volatility index"}),
    ("^FTSE", "FTSE 100", "Index", {"ftse", "london stocks"}),
    ("^GDAXI", "DAX", "Index", {"dax", "german stocks"}),
    ("^FCHI", "CAC 40", "Index", {"cac"}),
    ("^STOXX50E", "Euro Stoxx 50", "Index", {"european stocks", "stoxx"}),
    ("^N225", "Nikkei 225", "Index", {"japanese stocks", "nikkei"}),
    ("^HSI", "Hang Seng", "Index", {"hang seng", "hong kong stocks"}),
    ("^AXJO", "ASX 200", "Index", {"asx", "australian stocks"}),
    ("^GSPTSE", "TSX", "Index", {"canadian stocks", "tsx"}),
    ("^IBEX", "IBEX 35", "Index", {"ibex", "spanish stocks"}),
    ("^SSMI", "SMI", "Index", {"smi", "swiss stocks"}),
    ("^KS11", "KOSPI", "Index", {"korean stocks", "kospi"}),
    ("^BSESN", "Sensex", "Index", {"indian stocks", "sensex"}),
    ("^AEX", "AEX", "Index", {"aex", "dutch stocks"}),
    ("^BVSP", "Bovespa", "Index", {"bovespa", "brazilian stocks"}),
    ("^MXX", "IPC Mexico", "Index", {"bolsa", "mexican stocks"}),
    ("EURUSD=X", "EUR/USD", "Forex", {"ecb", "euro", "eurozone"}),
    ("GBPUSD=X", "GBP/USD", "Forex", {"bank of england", "pound", "sterling"}),
    ("USDJPY=X", "USD/JPY", "Forex", {"bank of japan", "yen"}),
    ("USDCHF=X", "USD/CHF", "Forex", {"snb", "swiss franc"}),
    ("AUDUSD=X", "AUD/USD", "Forex", {"aussie dollar", "rba"}),
    ("USDCAD=X", "USD/CAD", "Forex", {"bank of canada", "loonie"}),
    ("NZDUSD=X", "NZD/USD", "Forex", {"kiwi dollar", "rbnz"}),
    ("EURGBP=X", "EUR/GBP", "Forex", {"euro", "pound"}),
    ("EURJPY=X", "EUR/JPY", "Forex", {"euro", "yen"}),
    ("GBPJPY=X", "GBP/JPY", "Forex", {"pound", "yen"}),
    ("EURCHF=X", "EUR/CHF", "Forex", {"euro", "swiss franc"}),
    ("AUDJPY=X", "AUD/JPY", "Forex", {"aussie dollar", "yen"}),
    ("USDSEK=X", "USD/SEK", "Forex", {"krona", "riksbank"}),
    ("USDNOK=X", "USD/NOK", "Forex", {"norges bank", "norwegian krone"}),
    ("USDMXN=X", "USD/MXN", "Forex", {"banxico", "peso"}),
    ("USDZAR=X", "USD/ZAR", "Forex", {"rand", "south africa"}),
    ("USDTRY=X", "USD/TRY", "Forex", {"lira", "turkey"}),
    ("USDCNY=X", "USD/CNY", "Forex", {"pboc", "renminbi", "yuan"}),
    ("EURSEK=X", "EUR/SEK", "Forex", {"euro", "krona"}),
    ("CHFJPY=X", "CHF/JPY", "Forex", {"swiss franc", "yen"}),
    ("BTC-USD", "Bitcoin", "Crypto", {"bitcoin", "btc"}),
    ("ETH-USD", "Ethereum", "Crypto", {"ether", "ethereum"}),
    ("SOL-USD", "Solana", "Crypto", {"solana"}),
    ("XRP-USD", "XRP", "Crypto", {"ripple", "xrp"}),
    ("ADA-USD", "Cardano", "Crypto", {"cardano"}),
    ("DOGE-USD", "Dogecoin", "Crypto", {"dogecoin"}),
    ("AVAX-USD", "Avalanche", "Crypto", {"avalanche"}),
    ("LINK-USD", "Chainlink", "Crypto", {"chainlink"}),
    ("DOT-USD", "Polkadot", "Crypto", {"polkadot"}),
    ("XMR-USD", "Monero", "Crypto", {"monero"}),
    ("LTC-USD", "Litecoin", "Crypto", {"litecoin"}),
    ("BCH-USD", "Bitcoin Cash", "Crypto", {"bitcoin cash"}),
    ("ATOM-USD", "Cosmos", "Crypto", {"cosmos"}),
    ("UNI7083-USD", "Uniswap", "Crypto", {"uniswap"}),
    ("ETC-USD", "Ethereum Classic", "Crypto", {"ethereum classic"}),
    ("XLM-USD", "Stellar", "Crypto", {"stellar"}),
    ("NEAR-USD", "NEAR", "Crypto", {"near protocol"}),
    ("ALGO-USD", "Algorand", "Crypto", {"algorand"}),
    ("FIL-USD", "Filecoin", "Crypto", {"filecoin"}),
    ("AAVE-USD", "Aave", "Crypto", {"aave"}),
    ("TRX-USD", "TRON", "Crypto", {"tron"}),
    ("GC=F", "Gold", "Commodity", {"gold"}),
    ("SI=F", "Silver", "Commodity", {"silver"}),
    ("CL=F", "WTI Crude", "Commodity", {"crude", "oil", "opec", "wti"}),
    ("BZ=F", "Brent Crude", "Commodity", {"brent", "oil", "opec"}),
    ("NG=F", "Natural Gas", "Commodity", {"natural gas"}),
    ("HG=F", "Copper", "Commodity", {"copper"}),
    ("PL=F", "Platinum", "Commodity", {"platinum"}),
    ("PA=F", "Palladium", "Commodity", {"palladium"}),
    ("ZW=F", "Wheat", "Commodity", {"grain", "wheat"}),
    ("ZC=F", "Corn", "Commodity", {"corn", "grain"}),
    ("ZS=F", "Soybeans", "Commodity", {"grain", "soybean"}),
    ("KC=F", "Coffee", "Commodity", {"coffee"}),
    ("SB=F", "Sugar", "Commodity", {"sugar"}),
    ("CT=F", "Cotton", "Commodity", {"cotton"}),
    ("ZL=F", "Soybean Oil", "Commodity", {"soybean oil"}),
    ("LE=F", "Live Cattle", "Commodity", {"beef", "cattle"}),
    ("HE=F", "Lean Hogs", "Commodity", {"hogs", "pork"}),
    ("OJ=F", "Orange Juice", "Commodity", {"orange juice"}),
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
    #: Seconds since this row's bars were fetched. Rows refresh in rotation, so
    #: ages differ across the screen — reporting it is what keeps that visible
    #: instead of letting a stale row look exactly like a fresh one.
    data_age_s: float = 0.0


# Yahoo tolerates this comfortably. Kept modest anyway: the point is to stop
# paying 26 round trips end to end, not to hammer a free undocumented endpoint.
FETCH_WORKERS = 8
#: How many rows a single cycle refetches once the cache is warm. Sized to hold
#: the request rate near where it was at 26 instruments (~13/minute) rather than
#: the ~64/minute that refetching all 129 would imply.
ROLL_BATCH = 26


def _get(url: str):
    try:
        req = urllib.request.Request(url, headers=_UA)
        return json.loads(urllib.request.urlopen(req, timeout=8).read())
    except Exception:
        return None


#: A year of daily closes. One month — the old default — was 23 bars, which is
#: fewer than the Quarter horizon's 60-day momentum window and far fewer than
#: the Year's 250, so two of the five horizons could not compute the number they
#: displayed. It also left volatility estimated on 22 observations. The longer
#: range is the *same single request*: 0.15s against 0.17s, measured.
SCAN_RANGE = "1y"


def _fetch(symbol: str, rng: str = SCAN_RANGE):
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
        # Per-symbol bar cache, so a scan does not refetch everything. See
        # `_due_for_refresh` for why that matters at this watchlist size.
        self._bars: dict[tuple[str, str], tuple[float, object]] = {}
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

    def _due_for_refresh(self, hz) -> list[tuple]:
        """Which rows to actually fetch this cycle.

        The watchlist went from 26 instruments to 129, and refetching all of
        them every TTL takes the request rate from ~13 a minute to ~64. That is
        not a theoretical limit: fetching the list a few times in quick
        succession got this machine throttled by the source, and a throttled
        scan does not error — it returns fewer rows and the screen quietly
        shrinks.

        So the size of the watchlist is decoupled from the request rate. A cold
        cache is filled in one pass, because a half-empty screen at launch is
        worse than one burst; after that only the `ROLL_BATCH` stalest rows are
        refetched each cycle and everything else is scored from cache. Every row
        carries its own age, so staleness is visible rather than hidden.
        """
        cold = [w for w in WATCHLIST if (w[0], hz.chart_range) not in self._bars]
        if cold:
            return list(WATCHLIST)
        now = time.time()
        by_age = sorted(WATCHLIST,
                        key=lambda w: self._bars[(w[0], hz.chart_range)][0])
        return by_age[:ROLL_BATCH]

    def _refresh(self, headlines, hz, profile) -> None:
        out: list[AssetSuggestion] = []
        days = hz.momentum_days
        scale = _MOM_SCALE.get(days, 0.10)
        # Only the fetch is parallel — the scoring below still runs in WATCHLIST
        # order, because map() yields in input order, so the screen is identical
        # to the sequential version and just sooner.
        due = self._due_for_refresh(hz)
        if due:
            with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
                for (symbol, *_), got in zip(due, pool.map(
                        lambda w: _fetch(w[0], hz.chart_range), due)):
                    if got is not None:
                        self._bars[(symbol, hz.chart_range)] = (time.time(), got)

        now = time.time()
        for symbol, name, cls, kw in WATCHLIST:
            entry = self._bars.get((symbol, hz.chart_range))
            if entry is None:
                continue
            fetched_at, got = entry
            age = now - fetched_at
            price, currency, closes = got
            prev = closes[-2]                        # yesterday's daily close
            day = price / prev - 1 if prev else 0.0
            # Momentum over the horizon's window. `hz.chart_range` is sized to
            # the horizon (1mo/3mo/1y/2y), so the series always covers `days`
            # and the fallbacks below are for a truncated feed, not normal use.
            if len(closes) > days:
                mom = price / closes[-(days + 1)] - 1
            elif len(closes) > 2:
                mom = price / closes[0] - 1     # the longest window we do have
            else:
                mom = day
            # Volatility chosen by horizon: a clustering model at short ones,
            # a long trailing window at long ones. Both measured against the
            # volatility that actually followed — see `sonar/volatility.py`.
            # Falls back to the plain estimate if the series is too short.
            vol = volatility.forecast(closes, days) or _daily_vol(closes)

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
                data_age_s=round(age, 1),
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
