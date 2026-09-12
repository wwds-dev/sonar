"""Scheduled institutional events — the calendar that actually moves prices.

Central banks are the most market-moving institutions there are, and unusually
for anything in this app they are **scheduled and public**. An FOMC decision has
a date known months ahead, arrives at a known minute, and reprices the entire
curve. That is a catalyst in the precise sense `assets.py` means: a known future
moment at which an instrument gets repriced, whichever way it goes.

What is here and what is not
----------------------------
Every source below was probed before it was added, and the ones that failed are
recorded rather than quietly dropped — the same rule as `providers.py`, where a
plausible-looking adapter that silently returns nothing is worse than no adapter:

* **Working** — Federal Reserve press releases, FOMC-only releases, Fed speeches,
  Bank of England news.
* **Not working from here** — the ECB and OPEC feeds both fail certificate
  verification, the IMF answers 403, the BIS feed 404s, and the US Treasury feed
  times out. ECB decisions still reach SONAR through the wires, second-hand; the
  others are simply absent. None of them is faked with a placeholder.
* **SEC EDGAR** is deliberately not wired up. It answers 403 without a contact
  address in the User-Agent, and its policy is that the address be a real one —
  so that is a decision for the operator, not something to hardcode.

Direction is not asserted, here or anywhere
-------------------------------------------
A rate decision is a **variance** event. It widens the distribution of outcomes;
it does not tell you which tail. That is the same position the rest of the app
takes on news and on politics, and it is the only claim the evidence supports —
see CONFIDENCE.md §7.3 and §8. Nothing in this module produces a lean.
"""

from __future__ import annotations

import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

_UA = {"User-Agent": "Mozilla/5.0 (compatible; sonar/0.5; +paper-demo)"}
_ATOM = "{http://www.w3.org/2005/Atom}"

# Verified reachable on 2026-09-12. See the module docstring for what was tried
# and refused to answer.
SOURCES: dict[str, tuple[str, str, str]] = {
    # name: (url, institution, kind)
    "Fed press":     ("https://www.federalreserve.gov/feeds/press_all.xml",
                      "Federal Reserve", "release"),
    "FOMC":          ("https://www.federalreserve.gov/feeds/press_monetary.xml",
                      "Federal Reserve", "policy"),
    "Fed speeches":  ("https://www.federalreserve.gov/feeds/speeches.xml",
                      "Federal Reserve", "speech"),
    "BoE":           ("https://www.bankofengland.co.uk/rss/news",
                      "Bank of England", "release"),
}

# Words that mark a release as a policy action rather than administrative
# housekeeping. The Fed's press feed carries a great deal of the latter —
# enforcement actions, personnel, banking supervision — and treating all of it
# as market-moving would be exactly the volume-not-signal mistake the news
# component already makes.
_POLICY = re.compile(
    r"\b(fomc|federal funds|interest rate|monetary policy|rate decision|"
    r"bank rate|policy rate|quantitative|balance sheet|dot plot|projections|"
    r"minutes|statement on longer-run)\b", re.I)

# A statement by a named principal. Distinct from a policy action: it moves
# markets through what it signals rather than through what it changes.
_PRINCIPAL = re.compile(
    r"\b(chair|chairman|governor|president|vice chair|secretary|minister)\b", re.I)


@dataclass
class Event:
    """One institutional communication."""

    title: str
    link: str
    institution: str
    kind: str                  # policy | release | speech
    ts: int                    # unix seconds, 0 if undated

    @property
    def age_hours(self) -> float:
        return (time.time() - self.ts) / 3600 if self.ts else 9999.0

    @property
    def policy(self) -> bool:
        """Does this change or describe policy, rather than administer it?"""
        return self.kind == "policy" or bool(_POLICY.search(self.title))

    @property
    def principal(self) -> bool:
        """Is a named office-holder speaking?"""
        return self.kind == "speech" or bool(_PRINCIPAL.search(self.title))

    def as_dict(self) -> dict:
        return {"title": self.title, "link": self.link,
                "institution": self.institution, "kind": self.kind,
                "ts": self.ts, "policy": self.policy,
                "principal": self.principal,
                "age_h": round(self.age_hours, 1) if self.ts else None}


def _parse_ts(node, atom: bool) -> int:
    from .news import _parse_date
    if atom:
        return _parse_date(node.findtext(f"{_ATOM}published")
                           or node.findtext(f"{_ATOM}updated"))
    return _parse_date(node.findtext("pubDate") or node.findtext("date"))


def _fetch_one(name: str) -> list[Event]:
    url, institution, kind = SOURCES[name]
    try:
        raw = urllib.request.urlopen(
            urllib.request.Request(url, headers=_UA), timeout=12).read()
        root = ET.fromstring(raw)
    except Exception:
        return []                      # a source being down is expected, not an error
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
        else:
            link = (it.findtext("link") or "").strip()
        out.append(Event(title=title, link=link, institution=institution,
                         kind=kind, ts=_parse_ts(it, atom)))
    return out


class InstitutionCache:
    """Fetches and caches the institutional feeds.

    Central banks publish on a schedule measured in weeks, so the TTL is long.
    Polling them hard would buy nothing and is rude to a public service.
    """

    def __init__(self, ttl: float = 900.0) -> None:
        self.ttl = ttl
        self._at = 0.0
        self._events: list[Event] = []

    def events(self) -> list[Event]:
        now = time.time()
        if now - self._at > self.ttl or not self._events:
            self._refresh()
            self._at = now
        return self._events

    def _refresh(self) -> None:
        with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
            batches = pool.map(_fetch_one, list(SOURCES))
        seen: set[str] = set()
        out: list[Event] = []
        for batch in batches:
            for e in batch:
                key = e.title.lower().strip()
                if key in seen:
                    continue
                seen.add(key)
                out.append(e)
        if out:                        # keep the last good set on a total outage
            out.sort(key=lambda e: e.ts, reverse=True)
            self._events = out

    def payload(self, limit: int = 20) -> dict:
        evs = self.events()
        policy = [e for e in evs if e.policy]
        return {
            "generated": int(time.time()),
            "n": len(evs),
            "n_policy": len(policy),
            "institutions": sorted({e.institution for e in evs}),
            "recent": [e.as_dict() for e in evs[:limit]],
            "policy": [e.as_dict() for e in policy[:limit]],
            "pressure": pressure(evs),
        }


def pressure(events: list[Event], window_h: float = 72.0) -> dict:
    """How much policy communication has landed recently.

    A *variance* reading, deliberately, and not a direction. Heavy policy traffic
    in a short window means the rate path is being repriced, which widens the
    distribution of outcomes for everything priced off it. Which way it widens is
    not something this can know, and the rest of the app does not ask it to —
    see CONFIDENCE.md §7.3.
    """
    recent = [e for e in events if e.ts and e.age_hours <= window_h]
    pol = [e for e in recent if e.policy]
    speak = [e for e in recent if e.principal]
    # Three policy communications in three days is a busy week by the standards
    # of a central bank; the scale saturates there rather than at some number
    # chosen to make the reading look dramatic.
    score = min(1.0, len(pol) / 3.0)
    if len(pol) >= 3:
        level = "Heavy"
    elif len(pol) >= 1:
        level = "Active"
    elif speak:
        level = "Speeches only"
    else:
        level = "Quiet"
    return {"window_h": window_h, "n_recent": len(recent), "n_policy": len(pol),
            "n_principal": len(speak), "score": round(score, 3), "level": level}


if __name__ == "__main__":        # quick manual smoke test
    c = InstitutionCache()
    p = c.payload()
    print(f"{p['n']} events from {', '.join(p['institutions'])}")
    print("pressure:", p["pressure"])
    for e in p["recent"][:6]:
        print(f"  [{e['institution']}] {e['title'][:70]}")
