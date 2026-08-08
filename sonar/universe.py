"""The tradeable universe, and how to look each name up.

The hand-written watchlist was 26 instruments — enough to demonstrate the app,
far too few to settle a statistical question. The attention edge sits at roughly
+5 points on the hit rate with an error bar of the same size, and the only cure
for that is more independent observations. More symbols is the cheapest source
of them.

Two pieces:

* :func:`fetch_universe` pulls the listed US equities from Nasdaq's screener and
  filters them down to things worth testing — real common stock with a genuine
  market capitalisation, not rights, warrants, units or empty shells.
* :func:`wiki_article` resolves a company name to its Wikipedia article, so the
  historical attention proxy can be built for a symbol nobody hand-mapped.

Both cache to disk. The universe changes on the timescale of listings, and the
symbol→article mapping essentially never does, so re-fetching either on every
run would be rude to the services and slow for no reason.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import paths

_NASDAQ = ("https://api.nasdaq.com/api/screener/stocks"
           "?tableonly=true&limit=8000&offset=0&download=true")
_NASDAQ_UA = {"User-Agent": "Mozilla/5.0 (Macintosh) sonar/0.4",
              "Accept": "application/json"}
_WIKI_SEARCH = ("https://en.wikipedia.org/w/api.php?action=opensearch&limit=1"
                "&namespace=0&format=json&search={q}")
_WIKI_UA = {"User-Agent": "sonar-research/0.4 (personal backtest)"}

# Only ordinary shares. The screener is full of instruments whose price series
# would quietly poison a backtest: warrants expire, rights vanish, and a
# pre-deal SPAC sits pinned at $10 with no volatility to speak of.
# "depositary" is deliberately absent: American Depositary Shares are how most
# large foreign companies list here, and excluding the word threw all of them
# out. Preferred stock dressed as depositary shares is caught by "preferred".
_EXCLUDE = re.compile(
    r"\b(warrant|rights?|units?|preferred|notes?|debenture)\b", re.I)
_COMMON = re.compile(r"common stock|ordinary shares|american depositary shares", re.I)
# Tickers with punctuation are share classes and non-standard listings that
# Yahoo and Wikipedia disagree about; not worth the ambiguity.
_CLEAN_TICKER = re.compile(r"^[A-Z]{1,5}$")

CACHE_TTL = 7 * 86400.0


def _cache(name: str):
    return paths.cache_dir() / name


def _load_cache(name: str, ttl: float = CACHE_TTL):
    p = _cache(name)
    try:
        if time.time() - p.stat().st_mtime > ttl:
            return None
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _save_cache(name: str, data) -> None:
    p = _cache(name)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))
    except OSError:
        pass


def _money(raw) -> float:
    try:
        return float(str(raw).replace("$", "").replace(",", "") or 0.0)
    except ValueError:
        return 0.0


def clean_name(raw: str) -> str:
    """Turn a screener name into something Wikipedia can find.

    "Apple Inc. Common Stock" is not an article title; "Apple Inc." is.
    """
    name = re.sub(r"\s+(common stock|ordinary shares|american depositary shares"
                  r"|class [a-z]).*$", "", raw, flags=re.I)
    return name.strip(" ,.")


def fetch_universe(min_market_cap: float = 5e9, limit: int = 250,
                   refresh: bool = False) -> list[dict]:
    """Listed US common stock above ``min_market_cap``, largest first.

    The cap floor is doing real work: it keeps the sample to names with
    continuous quotes, tight-ish spreads and enough press coverage for the
    attention proxy to mean anything. A micro-cap with three headlines a year
    tells you nothing about whether news moves prices.
    """
    cached = None if refresh else _load_cache("universe.json")
    if cached is not None:
        return cached[:limit]
    try:
        req = urllib.request.Request(_NASDAQ, headers=_NASDAQ_UA)
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        rows = d["data"]["rows"]
    except Exception:
        return []

    out = []
    for r in rows:
        sym = (r.get("symbol") or "").strip().upper()
        name = (r.get("name") or "").strip()
        if not _CLEAN_TICKER.match(sym):
            continue
        if _EXCLUDE.search(name) or not _COMMON.search(name):
            continue
        cap = _money(r.get("marketCap"))
        if cap < min_market_cap:
            continue
        out.append({"symbol": sym, "name": clean_name(name), "market_cap": cap,
                    "sector": (r.get("sector") or "").strip(),
                    "country": (r.get("country") or "").strip()})
    out.sort(key=lambda x: -x["market_cap"])
    _save_cache("universe.json", out)
    return out[:limit]


_last_wiki = 0.0
WIKI_MIN_INTERVAL = 0.35


def _throttle() -> None:
    global _last_wiki
    wait = WIKI_MIN_INTERVAL - (time.time() - _last_wiki)
    if wait > 0:
        time.sleep(wait)
    _last_wiki = time.time()


def _wiki_get(url: str, tries: int = 3):
    """GET against Wikimedia with backoff. They rate-limit, and a swallowed 429
    would look exactly like "no such article"."""
    for attempt in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=_WIKI_UA)
            return json.loads(urllib.request.urlopen(req, timeout=20).read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    return None


def canonical_title(title: str) -> str | None:
    """Follow redirects to the article that actually holds the pageviews.

    This is not a nicety. Pageviews are counted per *article*, and a redirect
    has its own — near zero. "Amazon.com Inc" reports 0 views a day while
    "Amazon (company)" reports 6,670. Feeding the redirect into the attention
    proxy would produce a flat, empty series and a confident wrong answer about
    whether news moves prices.
    """
    url = ("https://en.wikipedia.org/w/api.php?action=query&redirects=1"
           f"&format=json&titles={urllib.parse.quote(title)}")
    d = _wiki_get(url)
    try:
        pages = d["query"]["pages"]
    except (TypeError, KeyError):
        return None
    for pid, page in pages.items():
        if pid == "-1" or "missing" in page:
            return None
        return (page.get("title") or "").replace(" ", "_") or None
    return None


def wiki_article(company: str) -> str | None:
    """Resolve a company name to the canonical Wikipedia article, or ``None``.

    Deliberately strict. A loose match would map a ticker onto an unrelated
    article and then report its pageviews as that company's news coverage — a
    silent, plausible-looking wrong answer, which is the failure mode this
    project spends most of its effort avoiding.
    """
    d = _wiki_get(_WIKI_SEARCH.format(q=urllib.parse.quote(company)))
    titles = d[1] if d and len(d) > 1 else []
    if not titles:
        return None
    # The first significant word of the company name must survive into the
    # article title, otherwise the search has wandered off.
    head = re.split(r"[\s,]", company.strip())[0].lower()
    if len(head) >= 3 and head not in titles[0].lower():
        return None
    return canonical_title(titles[0])


def article_map(symbols: list[tuple[str, str]], refresh: bool = False) -> dict:
    """``[(symbol, company)] -> {symbol: article}``, cached on disk."""
    cached = {} if refresh else (_load_cache("wiki_map.json", ttl=90 * 86400.0) or {})
    out = dict(cached)
    changed = False
    for sym, name in symbols:
        if sym in out:
            continue
        art = wiki_article(name)
        out[sym] = art                      # cache misses too — do not re-ask
        changed = True
    if changed:
        _save_cache("wiki_map.json", out)
    return {k: v for k, v in out.items() if v}
