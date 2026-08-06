"""Known catalysts: earnings dates and upcoming listings.

Momentum tells you what already happened. A **scheduled** event tells you when
the next repricing is likely, which is the more useful thing for a short holding
period — an earnings print inside your horizon is the difference between a quiet
drift and a gap.

Two feeds, both public and keyless:

* **Earnings** — Nasdaq's calendar, walked forward a couple of weeks and folded
  into a ``symbol -> next report`` map.
* **Listings** — Nasdaq's IPO calendar: priced, upcoming and filed.

What this deliberately does not do
----------------------------------
It never says which *way* an event will go. "Reports in 3 days" is a fact;
"reports in 3 days so buy" is a fabrication — the direction of an earnings
surprise is exactly the thing nobody gets for free from a calendar. So a
catalyst raises how *notable* something is and shortens the horizon you should
be thinking in. It contributes nothing to direction.

There is a real second-order effect worth naming: implied volatility usually
rises into a print and collapses after it. A volatility-scaled stop set the day
before earnings is narrower than the move that is actually coming, so positions
held through a print get stopped out more often than the maths suggests. The UI
flags the event; sizing around it is a judgement call.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request
from dataclasses import dataclass

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) sonar/0.4",
       "Accept": "application/json"}
_EARNINGS = "https://api.nasdaq.com/api/calendar/earnings?date={date}"
_IPO = "https://api.nasdaq.com/api/ipo/calendar?date={month}"

# Trading days to walk forward when building the earnings map.
LOOKAHEAD_DAYS = 14


def _get(url: str, timeout: float = 12.0):
    try:
        req = urllib.request.Request(url, headers=_UA)
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception:
        return None


@dataclass(frozen=True)
class Earnings:
    symbol: str
    date: str                 # ISO date
    when: str                 # pre-market | after-hours | unknown
    days_away: int

    @property
    def label(self) -> str:
        if self.days_away == 0:
            return f"earnings today ({self.when})"
        if self.days_away == 1:
            return f"earnings tomorrow ({self.when})"
        return f"earnings in {self.days_away}d"


@dataclass(frozen=True)
class Listing:
    symbol: str
    company: str
    status: str               # priced | upcoming | filed
    date: str
    price: str
    exchange: str


def _when(raw: str) -> str:
    raw = (raw or "").lower()
    if "pre" in raw:
        return "pre-market"
    if "post" in raw or "after" in raw:
        return "after-hours"
    return "unknown"


class EventsCache:
    """Earnings and listings, cached hard — a calendar does not change by the
    minute, and walking it costs one request per day looked at."""

    def __init__(self, ttl: float = 6 * 3600.0) -> None:
        self.ttl = ttl
        self._at = 0.0
        self._earnings: dict[str, Earnings] = {}
        self._listings: list[Listing] = []

    # -- fetching ---------------------------------------------------------- #
    def refresh(self, lookahead: int = LOOKAHEAD_DAYS) -> None:
        today = dt.date.today()
        found: dict[str, Earnings] = {}
        for offset in range(lookahead):
            day = today + dt.timedelta(days=offset)
            if day.weekday() >= 5:                 # no reports at the weekend
                continue
            d = _get(_EARNINGS.format(date=day.isoformat()))
            rows = ((d or {}).get("data") or {}).get("rows") or []
            for r in rows:
                sym = (r.get("symbol") or "").strip().upper()
                if not sym or sym in found:        # keep the *soonest* only
                    continue
                found[sym] = Earnings(symbol=sym, date=day.isoformat(),
                                      when=_when(r.get("time", "")),
                                      days_away=offset)
        if found:
            self._earnings = found

        d = _get(_IPO.format(month=today.strftime("%Y-%m")))
        data = (d or {}).get("data") or {}
        listings: list[Listing] = []
        for status in ("upcoming", "priced", "filed"):
            block = data.get(status) or {}
            for r in (block.get("rows") or [])[:12]:
                listings.append(Listing(
                    symbol=(r.get("proposedTickerSymbol") or "").strip(),
                    company=(r.get("companyName") or "").strip(),
                    status=status,
                    date=(r.get("pricedDate") or r.get("expectedPriceDate")
                          or r.get("filedDate") or ""),
                    price=(r.get("proposedSharePrice")
                           or r.get("dollarValueOfSharesOffered") or ""),
                    exchange=(r.get("proposedExchange") or "").strip()))
        if listings:
            self._listings = listings
        self._at = time.time()

    def _ensure(self) -> None:
        if time.time() - self._at > self.ttl or not self._at:
            self.refresh()

    # -- queries ----------------------------------------------------------- #
    def earnings_for(self, symbol: str) -> Earnings | None:
        self._ensure()
        return self._earnings.get(symbol.upper())

    def listings(self) -> list[Listing]:
        self._ensure()
        return list(self._listings)

    def payload(self) -> dict:
        self._ensure()
        return {
            "generated": int(self._at),
            "n_earnings": len(self._earnings),
            "listings": [vars(x) for x in self._listings],
            "earnings": [vars(e) for e in
                         sorted(self._earnings.values(), key=lambda e: e.days_away)],
        }


def catalyst_score(days_away: int | None, horizon_days: int) -> float:
    """How much a scheduled event sharpens this instrument, in ``[0, 1]``.

    Peaks for an event landing *inside* the holding period and decays to nothing
    once it falls well outside it. A print the day after you would have closed
    is not a catalyst, it is someone else's problem.
    """
    if days_away is None or days_away < 0:
        return 0.0
    horizon = max(1, horizon_days)
    if days_away <= horizon:
        return 1.0
    overshoot = (days_away - horizon) / horizon
    return max(0.0, 1.0 - overshoot)
