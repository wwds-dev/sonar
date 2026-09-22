"""Historical earnings dates from EDGAR, so the catalyst weight can face trial.

The catalyst component is 0.20 of the confidence score and, until this module,
the only one that had never been measured — the replay honestly reported
"not measured", because it had no historical earnings calendar to attribute
against. This is that calendar.

The source is the SEC's own submissions API: every 8-K a company files carries
its item numbers, and **Item 2.02 — Results of Operations and Financial
Condition** is the earnings release. The filing date of a 2.02 8-K *is* the
announcement date (occasionally the morning after), which makes it a clean,
free, documented record reaching back further than any free market-data
calendar does.

One assumption, named rather than hidden: treating the next filing date as
*known in advance* at the decision date. For earnings that is fair — companies
schedule and pre-announce these dates weeks out, and `catalyst_score` only
cares about events inside roughly one holding period — but it is an
approximation of the calendar a live screen would have shown, not a copy of it.

Foreign filers (ADRs — ASML, TSM, Novo and friends) report on 20-F and 6-K,
which carry no item numbers, so they yield no dates here and their rows simply
carry no catalyst series — skipped honestly, exactly as symbols without a
Wikipedia article are skipped by the attention study.

The SEC asks automated clients to identify themselves and stay under ten
requests a second; the User-Agent below and the throttle are that policy,
not decoration.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request

from .. import paths

_TICKERS = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
#: The SEC's fair-access policy wants a descriptive agent **with a contact** —
#: www.sec.gov 403s one without, while data.sec.gov shrugs. The contact is the
#: project's public git identity, which is pseudonymous by workspace
#: convention and already on every commit.
_UA = {"User-Agent": "sonar-research/0.4 "
                     "(243015673+Netrunner3000@users.noreply.github.com)"}

#: The 8-K item that is an earnings release.
EARNINGS_ITEM = "2.02"

#: Well under the SEC's ten-requests-per-second ceiling.
MIN_INTERVAL_S = 0.15

CACHE = "earnings_history.json"
#: Earnings histories move one date per quarter; a week of staleness is free.
CACHE_TTL = 7 * 86400.0

_last_call = 0.0


def _get(url: str):
    global _last_call
    wait = MIN_INTERVAL_S - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()
    try:
        req = urllib.request.Request(url, headers=_UA)
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception:
        return None


def ticker_cik_map() -> dict[str, int]:
    """``{ticker: CIK}`` for every registrant the SEC lists."""
    d = _get(_TICKERS)
    if not isinstance(d, dict):
        return {}
    out = {}
    for row in d.values():
        try:
            out[str(row["ticker"]).upper()] = int(row["cik_str"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def earnings_dates_from_submissions(d: dict) -> list[str]:
    """``YYYY-MM-DD`` filing dates of Item-2.02 8-Ks, oldest first.

    Split from the fetch so the parsing — the part that can silently be wrong
    — is testable against a saved payload. The submissions feed is parallel
    arrays; a malformed row costs itself and nothing else.
    """
    try:
        recent = d["filings"]["recent"]
        forms = recent["form"]
        dates = recent["filingDate"]
        items = recent.get("items") or [""] * len(forms)
    except (KeyError, TypeError):
        return []
    out = set()
    for form, date, item in zip(forms, dates, items):
        if str(form).strip() != "8-K":
            continue
        if EARNINGS_ITEM not in str(item or ""):
            continue
        if date:
            out.add(str(date))
    return sorted(out)


def history(symbols: list[str], refresh: bool = False) -> dict[str, list[str]]:
    """``{symbol: [YYYY-MM-DD, …]}`` for whatever EDGAR can answer.

    Cached on disk, misses included — a symbol with no CIK or no 2.02 filings
    is an empty list, and re-asking the SEC about it weekly is enough.
    """
    cache = paths.cache_dir() / CACHE
    stored: dict = {}
    if not refresh:
        try:
            if time.time() - cache.stat().st_mtime <= CACHE_TTL:
                stored = json.loads(cache.read_text())
        except (OSError, ValueError):
            stored = {}
    todo = [s for s in symbols if s.upper() not in stored]
    if todo:
        ciks = ticker_cik_map()
        for sym in todo:
            cik = ciks.get(sym.upper())
            payload = _get(_SUBMISSIONS.format(cik=cik)) if cik else None
            stored[sym.upper()] = (earnings_dates_from_submissions(payload)
                                   if payload else [])
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(stored))
        except OSError:
            pass
    return {s: stored.get(s.upper(), []) for s in symbols}


def days_to_next(dates: list[str], day: dt.date,
                 lookahead_days: int = 120) -> int | None:
    """Days from ``day`` to the next earnings on or after it, or ``None``.

    ``None`` past the lookahead rather than a large number: a print four
    months out is not on anyone's calendar yet, and `catalyst_score` treats
    None as "no scheduled event", which is the honest reading.
    """
    iso = day.isoformat()
    for d in dates:                       # sorted, so the first hit is next
        if d >= iso:
            away = (dt.date.fromisoformat(d) - day).days
            return away if away <= lookahead_days else None
    return None
