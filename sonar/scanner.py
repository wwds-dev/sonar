"""The multi-market opportunity scanner.

Takes the scanned Polymarket markets plus reputable-source headlines and turns
each into a *suggestion* with a transparent **confidence score**. Read this part
carefully, because it is where honesty lives:

The confidence score (0-100) is **not** a probability that you will make money.
It is a heuristic "how notable and tradeable does this setup look right now,"
blended from factors that can actually be measured:

    liquidity   how much real money and depth is in the market
    timing      how soon it resolves (shorter scores higher — "quick" ROI)
    momentum    how much the odds have moved recently
    edge        model probability minus market price — ONLY for crypto
                up/down markets, where an independent price model exists
    news        recency-weighted volume of matched reputable headlines

For crypto up/down markets, ``edge`` is a genuine (paper) signal and a side is
suggested. For every other market there is **no independent model**, so no side
is asserted — the scanner only surfaces the market's own odds, its momentum, and
the news around it. Every suggestion exposes its component breakdown so the
number is never a black box, and news sentiment is shown as *context*, never as
a buy/sell instruction.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field

from . import feeds, model, news

# Which measured factors feed the confidence blend, and their weights.
_W_CRYPTO = {"edge": .30, "liquidity": .20, "timing": .15, "momentum": .15, "news": .20}
_W_OTHER = {"liquidity": .32, "timing": .26, "momentum": .22, "news": .20}


@dataclass
class Suggestion:
    id: str
    question: str
    slug: str
    category: str
    url: str
    yes_price: float
    outcomes: list[str]
    hours_left: float
    volume24h: float
    # scored components (each 0..1)
    comp: dict = field(default_factory=dict)
    confidence: float = 0.0
    # direction / context
    side: str | None = None          # "UP"/"DOWN" for crypto paper signals only
    model_up: float | None = None
    edge: float | None = None
    market_lean: str = ""            # non-crypto: the market's own favourite
    news_sentiment: float = 0.0
    headlines: list[dict] = field(default_factory=list)
    rationale: str = ""


_SPORTS = (" vs ", " vs. ", "(bo3)", "(bo5)", "(bo1)", "esports", "counter-strike",
           "lol:", " nba", " nfl", " mlb", " nhl", "premier league", "la liga",
           "champions league", "super bowl", "world cup", "ufc", "grand prix")


def is_sports(q: str) -> bool:
    s = q.lower()
    return any(p in s for p in _SPORTS)


def categorize(q: str, is_crypto: bool) -> str:
    if is_crypto:
        return "Crypto"
    s = q.lower()
    if any(w in s for w in ("bitcoin", "ethereum", " btc", " eth", "crypto",
                            "solana", "dogecoin", "xrp", "binance", "coinbase")):
        return "Crypto"
    if any(w in s for w in ("president", "election", "prime minister", "senate",
                            "parliament", "governor", "congress", "democrat",
                            "republican", "minister", "chancellor", "mayor", "vote",
                            "cabinet", "impeach", "referendum")):
        return "Politics"
    if any(w in s for w in ("fed", "rate", "inflation", "cpi", "gdp", "recession",
                            "unemployment", "jobs", "interest", "tariff", "stock",
                            "nasdaq", "s&p", "earnings", "market cap", "largest company",
                            "nvidia", "apple", "tesla", "microsoft", "dollar", "bond")):
        return "Economy"
    if any(w in s for w in ("war", "ceasefire", "sanction", "nato", "ukraine",
                            "israel", "iran", "russia", "gaza", "nuclear", "cartel",
                            "hostage", "strike on", "invasion", "troops")):
        return "Geopolitics"
    return "Other"


def _liquidity_score(m: feeds.ScanMarket) -> float:
    vol = min(1.0, math.log10(m.volume24h + 1) / 6.5)       # ~$3M/day -> ~1
    liq = min(1.0, m.liquidity / 60_000.0)
    return 0.6 * vol + 0.4 * liq


def _timing_score(hours_left: float) -> float:
    h = max(hours_left, 0.2)
    return max(0.0, min(1.0, 1 - math.log10(h) / math.log10(720)))  # 30d -> 0


def _momentum_score(m: feeds.ScanMarket) -> float:
    mv = max(abs(m.mom_1h) * 3.0, abs(m.mom_1d))
    return min(1.0, mv / 0.15)                                # 15% move -> 1


def _crypto_edge(m: feeds.ScanMarket, cache: dict):
    """Returns (model_up, edge, side) for a crypto up/down market, or None."""
    sym = m.crypto_asset
    if not sym:
        return None
    if sym not in cache:
        candle = feeds.hourly_candle(sym)
        sigma = model.hourly_sigma(feeds.recent_hourly_returns(sym))
        cache[sym] = (candle, sigma)
    candle, sigma = cache[sym]
    if candle is None:
        return None
    tau = max(0.0, min(1.0, (m.end_time - time.time()) / 3600.0))
    p = model.prob_up(candle.price, candle.open, sigma, tau)
    edge = p - m.yes_price
    return p, edge, ("UP" if edge >= 0 else "DOWN")


def build(markets: list[feeds.ScanMarket], headlines: list[news.Headline],
          limit: int = 40) -> list[Suggestion]:
    asset_cache: dict = {}
    out: list[Suggestion] = []

    for m in markets:
        if is_sports(m.question):          # scanner is for financial/political markets
            continue
        sym = m.crypto_asset
        cat = categorize(m.question, sym is not None)
        hours_left = max(0.0, (m.end_time - time.time()) / 3600.0)

        comp = {
            "liquidity": round(_liquidity_score(m), 3),
            "timing": round(_timing_score(hours_left), 3),
            "momentum": round(_momentum_score(m), 3),
        }

        s = Suggestion(
            id=m.id, question=m.question, slug=m.slug, category=cat,
            url=f"https://polymarket.com/event/{m.slug}",
            yes_price=round(m.yes_price, 4), outcomes=m.outcomes,
            hours_left=round(hours_left, 2), volume24h=round(m.volume24h, 2),
        )

        # crypto paper edge (the only place a side is asserted)
        ce = _crypto_edge(m, asset_cache)
        if ce is not None:
            s.model_up, s.edge, s.side = round(ce[0], 4), round(ce[1], 4), ce[2]
            comp["edge"] = round(min(1.0, abs(ce[1]) / 0.15), 3)
        else:
            fav_i = 0 if m.yes_price >= 0.5 else 1
            fav = m.outcomes[fav_i] if fav_i < len(m.outcomes) else "Yes"
            s.market_lean = f"{fav} {round((m.yes_price if fav_i==0 else 1-m.yes_price)*100)}¢"

        # news context
        kw = news.keywords(m.question)
        matched = news.match(headlines, kw)
        coverage, sentiment = news.news_signal(matched)
        comp["news"] = round(coverage, 3)
        s.news_sentiment = round(sentiment, 3)
        s.headlines = [{"title": h.title, "source": h.source, "link": h.link,
                        "age_h": round(h.age_hours, 1) if h.dated else None,
                        "cat": h.category}
                       for h in matched]

        # blend -> confidence
        weights = _W_CRYPTO if ce is not None else _W_OTHER
        s.confidence = round(100 * sum(weights[k] * comp.get(k, 0.0)
                                       for k in weights), 1)
        s.comp = comp
        s.rationale = _rationale(s, comp, weights)
        out.append(s)

    out.sort(key=lambda x: x.confidence, reverse=True)
    return out[:limit]


_LABEL = {"edge": "model edge", "liquidity": "liquidity", "timing": "resolves soon",
          "momentum": "odds moving", "news": "news coverage"}


def _rationale(s: Suggestion, comp: dict, weights: dict) -> str:
    top = sorted(weights, key=lambda k: weights[k] * comp.get(k, 0), reverse=True)
    drivers = [_LABEL[k] for k in top[:2] if comp.get(k, 0) > 0.2]
    bits = []
    if s.side:
        bits.append(f"model leans {s.side} ({(s.edge or 0)*100:+.1f}¢ vs market)")
    elif s.market_lean:
        bits.append(f"market leans {s.market_lean}")
    if drivers:
        bits.append("driven by " + " + ".join(drivers))
    if s.headlines:
        tone = "positive" if s.news_sentiment > .15 else "negative" if s.news_sentiment < -.15 else "mixed"
        bits.append(f"{len(s.headlines)} recent headline(s), tone {tone}")
    return "; ".join(bits) or "notable market"


def suggestions_payload(markets, headlines, limit: int = 40) -> dict:
    sugg = build(markets, headlines, limit)
    cats: dict[str, int] = {}
    for s in sugg:
        cats[s.category] = cats.get(s.category, 0) + 1
    return {
        "generated": int(time.time()),
        "n_scanned": len(markets),
        "n_shown": len(sugg),
        "categories": cats,
        "sources": list(news.FEEDS.keys()),
        "suggestions": [asdict(s) for s in sugg],
    }
