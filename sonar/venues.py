"""Where a watchlist row could actually be traded, and when it could not.

The screener happily scores `^GSPC`, `GC=F` and `XMR-USD`. None of the three is
something a retail account in Europe can buy: the first is an index, the second
is a Comex futures contract, and the third has been delisted from every
mainstream regulated venue. A board that ranks instruments while staying silent
about that is inviting an order that cannot be placed.

So this module answers two questions per row, and the second one matters more:

1. **What would you actually trade?** Often not the symbol on the board. An
   index is traded through an ETF, a futures contract through an ETC.
2. **Can you trade it at all, from here?** Sometimes no, and saying so plainly is
   the entire point of the module.

Region
------
Availability is regional, and pretending otherwise is the failure mode. The
default is ``eu`` because that is where this app is run; a US account has a
materially different list, most obviously in being able to buy the US-domiciled
ETFs that PRIIPs blocks here.

This is reference information, not advice and not an endorsement of any venue.
It also goes stale — exchanges delist, regulations arrive — so
:data:`CHECKED` records when it was last verified and the UI says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CHECKED = "2026-09-12"

# Mainstream retail venues available in the EU. Named for identification only.
_BROKERS = "Trade Republic, Scalable Capital, Revolut, Interactive Brokers"
_CRYPTO = "Kraken, Coinbase, Bitpanda, Revolut"


@dataclass(frozen=True)
class Venue:
    """How a row could be acted on, if it can be."""

    instrument: str            # what you would actually buy
    venues: str                # where, in plain names
    tradeable: bool = True     # False when nothing mainstream lists it
    proxy: bool = False        # True when the tradeable thing is not the symbol
    note: str = ""

    def as_dict(self) -> dict:
        return {"instrument": self.instrument, "venues": self.venues,
                "tradeable": self.tradeable, "proxy": self.proxy,
                "note": self.note, "checked": CHECKED}

    def summary(self) -> str:
        """One line for a tooltip."""
        if not self.tradeable:
            return f"Not tradeable from the EU — {self.note}"
        head = f"{self.instrument} · {self.venues}"
        return f"{head}\n{self.note}" if self.note else head


# --------------------------------------------------------------------------- #
# Per-symbol, where the symbol is not the thing you trade
# --------------------------------------------------------------------------- #
_SYMBOL: dict[str, Venue] = {
    # Indices are not instruments. The UCITS wrapper is the retail route, and
    # the obvious US tickers are specifically unavailable: PRIIPs requires a Key
    # Information Document, US-domiciled funds do not publish one, so EU brokers
    # cannot sell SPY, VOO or QQQ to retail clients at all.
    "^GSPC": Venue("An S&P 500 UCITS ETF (e.g. CSPX, VUSA)", _BROKERS, proxy=True,
                   note="The index itself cannot be bought. SPY and VOO are "
                        "closed to EU retail under PRIIPs — the UCITS version is "
                        "the route."),
    "^IXIC": Venue("A Nasdaq-100 UCITS ETF (e.g. EQQQ, CNDX, XNDX)", _BROKERS,
                   proxy=True,
                   note="Note this tracks the Nasdaq-100, not the Composite the "
                        "board scores. QQQ is closed to EU retail under PRIIPs."),
    "^DJI": Venue("A Dow Jones Industrial Average UCITS ETF", _BROKERS, proxy=True,
                  note="Thinner choice than the S&P or Nasdaq wrappers. DIA is "
                       "closed to EU retail under PRIIPs."),

    # Futures contracts. No mainstream EU retail app offers them; the retail
    # route is a commodity ETC, which tracks the price without the contract.
    "GC=F": Venue("A physically-backed gold ETC (e.g. Xetra-Gold, Invesco "
                  "Physical Gold)", _BROKERS, proxy=True,
                  note="GC=F is a Comex futures contract — not available on "
                       "retail apps. An ETC tracks the metal without roll."),
    "CL=F": Venue("A crude oil ETC", _BROKERS, proxy=True,
                  note="CL=F is a NYMEX futures contract. Oil ETCs roll their "
                       "contracts, so they drift from spot over time — they are "
                       "not a buy-and-hold on the oil price."),

    # Delisted from every mainstream regulated venue.
    "XMR-USD": Venue("Monero", "", tradeable=False,
                     note="Binance delisted XMR globally in Feb 2024 and Kraken "
                          "across the whole EEA in Oct 2024; Coinbase, Bitstamp "
                          "and Bitfinex do not list it in regulated regions. The "
                          "EU AML Regulation bars regulated platforms from "
                          "handling anonymity-enhancing coins from Jul 2027. "
                          "Owning it is legal; buying it through a mainstream EU "
                          "venue is not currently possible."),
}

# --------------------------------------------------------------------------- #
# Per-class defaults
# --------------------------------------------------------------------------- #
_CLASS: dict[str, Venue] = {
    "Equity": Venue("The share itself", _BROKERS,
                    note="US large caps are on every mainstream EU broker, "
                         "usually with fractional shares."),
    "Index": Venue("A UCITS ETF tracking it", _BROKERS, proxy=True,
                   note="An index is not an instrument — the ETF is."),
    "Crypto": Venue("Spot", _CRYPTO,
                    note="Spot on an exchange is the position. Revolut and "
                         "Trade Republic hold it for you rather than letting "
                         "you withdraw to your own wallet."),
    "Commodity": Venue("An ETC tracking it", _BROKERS, proxy=True,
                       note="The board's symbol is a futures contract; retail "
                            "access is through an ETC."),
    # Currency *exchange* and an FX *position* are different things, and the
    # apps that do the first are routinely mistaken for doing the second.
    "Forex": Venue("A spot FX position", "Interactive Brokers", proxy=True,
                   note="Revolut and Trade Republic convert currency; they do "
                        "not let you hold a directional FX position. Converting "
                        "EUR to USD is not the same trade as being long USD."),
}

_UNKNOWN = Venue("—", "", tradeable=False,
                 note="no venue mapping for this instrument")


def where(symbol: str, cls: str = "") -> Venue:
    """Where this row could be acted on. Symbol mapping wins over class."""
    hit = _SYMBOL.get(symbol.upper())
    if hit is not None:
        return hit
    return _CLASS.get(cls, _UNKNOWN)


def coverage() -> dict:
    """How much of the watchlist is actually actionable.

    Written to be run, not assumed: the answer moved the first time it was,
    which is why the module exists.
    """
    from .assets import WATCHLIST
    rows = [(sym, where(sym, cls)) for sym, _n, cls, _k in WATCHLIST]
    untradeable = [s for s, v in rows if not v.tradeable]
    proxied = [s for s, v in rows if v.tradeable and v.proxy]
    return {"n": len(rows), "untradeable": untradeable, "proxied": proxied,
            "direct": len(rows) - len(untradeable) - len(proxied),
            "checked": CHECKED}


if __name__ == "__main__":        # quick manual check
    c = coverage()
    print(f"{c['n']} instruments · {c['direct']} direct · "
          f"{len(c['proxied'])} via a proxy · {len(c['untradeable'])} not tradeable")
    print("  proxied:    ", ", ".join(c["proxied"]))
    print("  untradeable:", ", ".join(c["untradeable"]) or "none")
