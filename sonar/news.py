"""Reputable-source news, used only as *context* on a market — never as a signal.

This module pulls headlines from a small set of well-known financial and
political outlets' public RSS feeds, and offers crude keyword matching and
sentiment so the screener can show "here is what's in the news around this
asset." Two honesty rules are baked in:

* **It is context, not a predictor.** Headline sentiment does not reliably
  forecast direction, and nothing here claims it does — a pre-registered study
  of it across 116,563 asset-days found no edge. The screener folds a small,
  transparent news component into a heuristic score and shows the matched
  headlines so a human can judge them.
* **Scraped text is untrusted data.** Feed contents are treated purely as data
  to display and keyword-match. Instructions that might appear inside a headline
  or article are never followed — this module only ever reads and summarises.

Everything is stdlib (urllib + xml.etree) and cached, so a feed outage degrades
gracefully to "no news" rather than breaking the scan.
"""

from __future__ import annotations

import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

_UA = {"User-Agent": "Mozilla/5.0 (compatible; sonar/0.2; +paper-demo)"}

def _gnews(query: str, lang: str = "en-US", country: str = "US") -> str:
    """A Google News RSS search, used to reach wires with no open feed."""
    return (f"https://news.google.com/rss/search?q=when:24h+{query}"
            f"&hl={lang}&gl={country}&ceid={country}:{lang.split('-')[0]}")


@dataclass(frozen=True)
class Feed:
    """One source, and where it is reading the world from.

    ``origin`` and ``state`` exist because a story's *spread* is information the
    text of any single headline does not carry. An event that Reuters, Al Jazeera
    and Xinhua all lead with is a different event from one that only a
    state-aligned outlet is pushing, and a model that cannot tell those apart is
    reading volume rather than news. See CONFIDENCE.md §7 for where this is
    headed.

    ``state`` marks an outlet that is state-owned or state-directed. Not a
    judgement about truthfulness — state media is genuinely useful as evidence of
    what a government wants said, which is exactly what a geopolitical signal
    wants to measure. It is marked so it can be weighted deliberately rather than
    silently.
    """

    url: str
    category: str          # financial | political | tech | wire
    origin: str            # us | uk | eu | mena | china | russia | india | japan | africa | latam
    state: bool = False


FEEDS: dict[str, Feed] = {
    # --- Western press ---------------------------------------------------- #
    "BBC Business":   Feed("https://feeds.bbci.co.uk/news/business/rss.xml", "financial", "uk"),
    "BBC Politics":   Feed("https://feeds.bbci.co.uk/news/politics/rss.xml", "political", "uk"),
    "MarketWatch":    Feed("http://feeds.marketwatch.com/marketwatch/topstories/", "financial", "us"),
    "Yahoo Finance":  Feed("https://finance.yahoo.com/news/rssindex", "financial", "us"),
    "NPR Business":   Feed("https://feeds.npr.org/1006/rss.xml", "financial", "us"),
    "Ars Technica":   Feed("https://feeds.arstechnica.com/arstechnica/index", "tech", "us"),
    "TechCrunch":     Feed("https://techcrunch.com/feed/", "tech", "us"),
    "The Verge":      Feed("https://www.theverge.com/rss/index.xml", "tech", "us"),
    "CNBC Markets":   Feed("https://www.cnbc.com/id/10000664/device/rss/rss.html", "financial", "us"),
    # --- wire services ---------------------------------------------------- #
    # Reuters' own feed answers 401 and has done for a while; AP, Bloomberg and
    # the FT publish no open full-text RSS either. Google News is used as a
    # *proxy* — it indexes those wires and exposes headline, publisher and link,
    # which is all this app consumes. Worth being plain about: these are
    # second-hand headlines, not a wire subscription.
    #
    # dpa has no usable public feed at all (its Google News channel returns
    # nothing), so German wire coverage is not available here. Handelsblatt
    # stands in for German business news instead.
    "Reuters":        Feed(_gnews("source:Reuters"), "wire", "uk"),
    "AP":             Feed(_gnews("source:Associated+Press"), "wire", "us"),
    "Bloomberg":      Feed(_gnews("source:Bloomberg"), "wire", "us"),
    "Financial Times": Feed(_gnews("source:Financial+Times"), "wire", "uk"),
    "Handelsblatt":   Feed(_gnews("source:Handelsblatt", lang="de", country="DE"), "wire", "eu"),
    # --- outside the Western press ---------------------------------------- #
    # A geopolitical signal built only on Anglo-American outlets measures what
    # one bloc is talking about. These are here for coverage, not endorsement,
    # and the state-aligned ones are marked as such above.
    #
    # RT is deliberately absent. Its feed fails certificate verification from
    # here, and it is prohibited from distribution in the EU under Council
    # Regulation 2022/350 — so it is both broken and legally awkward from
    # Germany. TASS covers the same ground: it is the Russian state wire, which
    # is what the slot was for.
    "Al Jazeera":     Feed("https://www.aljazeera.com/xml/rss/all.xml", "political", "mena"),
    "Anadolu":        Feed("https://www.aa.com.tr/en/rss/default?cat=world", "political", "mena", state=True),
    "Global Times":   Feed("https://www.globaltimes.cn/rss/outbrain.xml", "political", "china", state=True),
    "SCMP":           Feed("https://www.scmp.com/rss/91/feed", "political", "china"),
    "TASS":           Feed("https://tass.com/rss/v2.xml", "political", "russia", state=True),
    "Times of India": Feed("https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "political", "india"),
    "The Hindu":      Feed("https://www.thehindu.com/news/international/feeder/default.rss", "political", "india"),
    "Japan Times":    Feed("https://www.japantimes.co.jp/feed/", "political", "japan"),
    "AllAfrica":      Feed("https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf", "political", "africa"),
    "Folha":          Feed("https://feeds.folha.uol.com.br/mundo/rss091.xml", "political", "latam"),
}

_ATOM = "{http://www.w3.org/2005/Atom}"

# Deliberately tiny, transparent sentiment lexicon. This is a crude heuristic and
# is labelled as such in the UI — not an NLP model.
_POS = {"surge", "surges", "surged", "rally", "rallies", "gain", "gains", "jump",
        "jumps", "beat", "beats", "growth", "optimism", "rebound", "soar", "soars",
        "upgrade", "record", "boost", "boosts", "strong", "strength", "deal",
        "agreement", "ceasefire", "approve", "approved", "wins", "win", "recovery",
        "high", "rises", "rise", "climbs", "bullish"}
_NEG = {"plunge", "plunges", "crash", "crashes", "fall", "falls", "drop", "drops",
        "miss", "misses", "recession", "fear", "fears", "selloff", "downgrade",
        "ban", "bans", "sanction", "sanctions", "war", "conflict", "collapse",
        "bankruptcy", "cut", "cuts", "slump", "weak", "default", "tumble",
        "tumbles", "sinks", "sink", "loss", "losses", "bearish", "warning"}

_WORD = re.compile(r"[A-Za-z][A-Za-z'&-]+")


@dataclass
class Headline:
    title: str
    link: str
    source: str
    category: str          # financial | political
    ts: int                # unix seconds (0 if unknown)
    origin: str = "us"     # which press bloc carried it — see Feed.origin
    state: bool = False    # from a state-owned or state-directed outlet
    _tokens: set[str] = field(default_factory=set, repr=False)

    @property
    def dated(self) -> bool:
        return self.ts > 0

    @property
    def age_hours(self) -> float:
        return (time.time() - self.ts) / 3600 if self.ts else 9999.0

    @property
    def sentiment(self) -> float:
        """Crude polarity in [-1, 1] from the tiny lexicon above."""
        pos = len(self._tokens & _POS)
        neg = len(self._tokens & _NEG)
        return (pos - neg) / (pos + neg) if (pos + neg) else 0.0


# Enough to hide the latency of one slow feed without opening fourteen sockets
# at once against a set of hosts that have no reason to expect it.
FETCH_WORKERS = 8


class NewsCache:
    """Fetches and caches all feeds. News changes slowly, so a long TTL keeps the
    screener light on the network."""

    def __init__(self, ttl: float = 480.0) -> None:
        self.ttl = ttl
        self._at = 0.0
        self._headlines: list[Headline] = []

    def headlines(self) -> list[Headline]:
        now = time.time()
        if now - self._at > self.ttl or not self._headlines:
            self._refresh()
            self._at = now
        return self._headlines

    def _refresh(self) -> None:
        out: list[Headline] = []
        seen: set[str] = set()
        items = list(FEEDS.items())
        # Twenty-odd independent GETs against as many different hosts. Run
        # sequentially this was ~3s of the ~11s the app spent before it could
        # show anything; concurrently it costs about as long as the slowest
        # single feed.
        #
        # map() yields in *input* order regardless of what finished first, so
        # dedup still keeps the first feed in FEEDS order to carry a story
        # rather than whichever host happened to answer fastest. Without that
        # the attributed source would vary run to run.
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            batches = pool.map(lambda kv: self._one(kv[0], kv[1]), items)
            for batch in batches:
                for h in batch:
                    key = h.title.lower().strip()
                    if key in seen:                # drop duplicate headlines
                        continue
                    seen.add(key)
                    out.append(h)
        if out:                                    # keep last good set on total failure
            self._headlines = out

    def _one(self, name: str, feed: Feed) -> list[Headline]:
        try:
            req = urllib.request.Request(feed.url, headers=_UA)
            raw = urllib.request.urlopen(req, timeout=10).read()
            root = ET.fromstring(raw)
        except Exception:
            return []
        nodes = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
        out = []
        for it in nodes[:40]:
            atom = it.tag.endswith("entry")
            title = (it.findtext(f"{_ATOM}title" if atom else "title") or "").strip()
            if not title:
                continue
            if atom:
                le = it.find(f"{_ATOM}link")
                link = (le.get("href") if le is not None else "") or ""
                ts = _parse_date(it.findtext(f"{_ATOM}published")
                                 or it.findtext(f"{_ATOM}updated"))
            else:
                link = (it.findtext("link") or "").strip()
                ts = _parse_date(it.findtext("pubDate"))
            title = _clean_title(title, name)
            toks = {w.lower() for w in _WORD.findall(title)}
            out.append(Headline(title=title, link=link, source=name,
                                category=feed.category, ts=ts, _tokens=toks,
                                origin=feed.origin, state=feed.state))
        return out


def _clean_title(title: str, source: str) -> str:
    """Google News suffixes every headline with " - Publisher".

    The publisher is already carried on the Headline, so the suffix is pure
    noise — and it pollutes the keyword tokens used for matching, which is the
    part that actually matters.
    """
    cut = title.rsplit(" - ", 1)
    if len(cut) == 2 and 0 < len(cut[1]) <= 40:
        return cut[0].strip()
    return title.strip()


def _parse_date(s: str | None) -> int:
    if not s:
        return 0
    try:                                           # RFC-822 (RSS <pubDate>)
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:                                       # ISO-8601 (Atom <published>)
            dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            return 0
    if dt is None:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


_STOP = {"will", "the", "next", "and", "for", "with", "have", "has", "was", "are",
         "who", "what", "when", "how", "why", "any", "all", "not", "yes", "does",
         "before", "after", "than", "this", "that", "over", "under", "into",
         "market", "markets", "price", "reach", "hit", "close", "closes", "day",
         "week", "month", "year", "his", "her", "their", "get", "effective",
         "operation", "outside", "change", "today", "tomorrow", "there", "been"}
_MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"}
_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
_CRYPTO_KW = {"bitcoin", "ethereum", "crypto", "btc", "eth"}


def keywords(question: str) -> set[str]:
    """Salient keywords from a market question, for matching against headlines.
    Drops months, weekdays, pure numbers and stopwords so a shared 'July' can't
    fake a match; keeps specific words (length >= 4) plus crypto aliases."""
    toks = {w.lower() for w in _WORD.findall(question)}
    kw = {t for t in toks if len(t) >= 4 and t not in _STOP
          and t not in _MONTHS and t not in _DAYS and not t.isdigit()}
    ql = question.lower()
    if "bitcoin" in ql or " btc" in ql:
        kw |= {"bitcoin", "btc", "crypto"}
    if "ethereum" in ql or " eth" in ql:
        kw |= {"ethereum", "eth", "crypto"}
    return kw


def match(headlines: list[Headline], kw: set[str], limit: int = 4) -> list[Headline]:
    """Headlines that share a *specific* keyword with the market: at least two
    overlaps including one distinctive token (length >= 6), or a crypto token.
    Most recent first. Deliberately conservative to avoid spurious matches."""
    if not kw:
        return []
    scored = []
    for h in headlines:
        overlap = h._tokens & kw
        if not overlap:
            continue
        strong = overlap & _CRYPTO_KW
        distinctive = any(len(t) >= 6 for t in overlap)
        if strong or (len(overlap) >= 2 and distinctive):
            scored.append((len(overlap), -h.age_hours, h))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [h for _, _, h in scored[:limit]]


def bloc_spread(matched: list[Headline]) -> dict:
    """How far a story has travelled, and who is carrying it.

    Volume alone cannot tell a genuinely global event from one outlet running the
    same line all day. Spread can: an event on the wires in five press blocs is a
    different object from one carried in a single bloc, whatever the headline
    count says. That distinction is the reason the non-Western feeds are here.

    ``state_only`` is the flag worth having. A story only state-directed outlets
    are pushing is still informative — it says a government wants it said — but
    it is evidence about the government rather than corroboration of the event,
    and the two must not be summed into one number.
    """
    if not matched:
        return {"blocs": [], "n_blocs": 0, "state_share": 0.0, "state_only": False}
    blocs = sorted({h.origin for h in matched})
    n_state = sum(1 for h in matched if h.state)
    return {"blocs": blocs, "n_blocs": len(blocs),
            "state_share": round(n_state / len(matched), 3),
            "state_only": n_state == len(matched)}


def news_signal(matched: list[Headline]) -> tuple[float, float]:
    """(coverage, sentiment) for a set of matched headlines.

    coverage in [0,1]: recency-weighted count (fresh news counts more).
    sentiment in [-1,1]: average polarity of the matched headlines.
    Both are crude, transparent heuristics — context, not prediction.
    """
    if not matched:
        return 0.0, 0.0
    cover = 0.0
    for h in matched:
        if not h.dated:
            cover += 0.3                            # unknown recency: mild weight
        else:
            cover += 1.0 if h.age_hours < 6 else 0.5 if h.age_hours < 24 else 0.2
    coverage = min(1.0, cover / 2.0)
    sentiment = sum(h.sentiment for h in matched) / len(matched)
    return coverage, sentiment
