"""Pluggable data providers, each with its own switch.

SONAR runs on Yahoo Finance, which is free, broad and **unofficial**. It is not
a documented product, it can change shape or start refusing requests without
notice, and it already has: the ``quoteSummary`` endpoint used for earnings
dates now answers 401. Depending on one undocumented endpoint for everything is
the single largest fragility in the app.

So sources sit behind one interface with three properties each:

* a **capability** — quotes, daily bars, FX or crypto — so a caller asks for
  what it needs rather than naming a vendor;
* a **tier** — ``keyless`` works out of the box, ``keyed`` needs a free account;
* a **switch** — on or off, persisted, so a provider can be disabled without
  touching code.

:func:`resolve` walks the enabled providers for a capability in preference
order and returns the first that answers. A provider that is off, unconfigured
or failing is skipped rather than breaking the call.

On what is *not* here
---------------------
Stooq appears in a lot of "free market data" lists and is in none of this code:
both its CSV endpoints now return an HTML bot-block page rather than data. An
adapter for it would parse that page into silence and look like a working
fallback. Verified-not-working beats plausible-looking.
"""

from __future__ import annotations

import csv
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from . import paths

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh) sonar/0.5"}

QUOTES, BARS, FX, CRYPTO = "quotes", "bars", "fx", "crypto"


def _get(url: str, timeout: float = 12.0, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or _UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


def _json(url: str, **kw):
    return json.loads(_get(url, **kw))


@dataclass
class Provider:
    name: str
    tier: str                       # keyless | keyed
    capabilities: set[str]
    fetchers: dict[str, Callable] = field(default_factory=dict)
    env_key: str = ""
    signup: str = ""
    note: str = ""
    preference: int = 50            # lower wins when several can serve

    @property
    def configured(self) -> bool:
        return self.tier == "keyless" or bool(os.environ.get(self.env_key))

    def status(self) -> dict:
        return {"name": self.name, "tier": self.tier,
                "capabilities": sorted(self.capabilities),
                "configured": self.configured, "enabled": is_enabled(self.name),
                "env_key": self.env_key, "signup": self.signup,
                "note": self.note}


REGISTRY: dict[str, Provider] = {}


def register(p: Provider) -> Provider:
    """Register a provider, and let a quotes fetcher serve its asset-class
    capabilities too.

    Without this, a provider declaring ``{CRYPTO, QUOTES}`` but implementing one
    ``quotes`` fetcher looks unavailable for crypto — status() reported empty
    chains for fx and crypto while both were in fact being served.
    """
    quote_fn = p.fetchers.get(QUOTES)
    if quote_fn:
        for cap in (FX, CRYPTO):
            if cap in p.capabilities:
                p.fetchers.setdefault(cap, quote_fn)
    REGISTRY[p.name] = p
    return p


# --------------------------------------------------------------------------- #
# switches — persisted so a provider stays off across restarts
# --------------------------------------------------------------------------- #
def _config_path():
    return paths.user_data_base() / "providers.json"


def _load_config() -> dict:
    try:
        return json.loads(_config_path().read_text())
    except (OSError, ValueError):
        return {}


def set_enabled(name: str, on: bool) -> dict:
    cfg = _load_config()
    cfg[name] = bool(on)
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=1))
    return cfg


def is_enabled(name: str) -> bool:
    """Providers are on unless explicitly switched off."""
    return _load_config().get(name, True)


# --------------------------------------------------------------------------- #
# keyless providers — verified working
# --------------------------------------------------------------------------- #
def _yahoo_bars(symbol: str, rng: str = "1mo") -> dict | None:
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?range={rng}&interval=1d")
    d = _json(url)
    r = d["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    closes = [c for c in q["close"] if c is not None]
    if not closes:
        return None
    return {"symbol": symbol, "price": r["meta"].get("regularMarketPrice") or closes[-1],
            "currency": r["meta"].get("currency", ""), "closes": closes,
            "source": "yahoo"}


def _yahoo_quote(symbol: str) -> dict | None:
    b = _yahoo_bars(symbol, "5d")
    return {"symbol": symbol, "price": b["price"], "currency": b["currency"],
            "source": "yahoo"} if b else None


register(Provider(
    name="yahoo", tier="keyless", capabilities={QUOTES, BARS, FX, CRYPTO},
    fetchers={QUOTES: _yahoo_quote, BARS: _yahoo_bars},
    preference=10,
    note="Broad and free, but undocumented and unstable — the reason this "
         "abstraction exists. Its quoteSummary endpoint already returns 401."))


def _coingecko_quote(symbol: str) -> dict | None:
    ids = {"BTC-USD": "bitcoin", "ETH-USD": "ethereum", "BNB-USD": "binancecoin",
           "XRP-USD": "ripple", "SOL-USD": "solana", "TRX-USD": "tron",
           "DOGE-USD": "dogecoin", "ADA-USD": "cardano",
           "AVAX-USD": "avalanche-2", "LINK-USD": "chainlink",
           "XMR-USD": "monero"}
    cid = ids.get(symbol.upper())
    if not cid:
        return None
    d = _json("https://api.coingecko.com/api/v3/simple/price"
              f"?ids={cid}&vs_currencies=usd")
    price = (d.get(cid) or {}).get("usd")
    return {"symbol": symbol, "price": float(price), "currency": "USD",
            "source": "coingecko"} if price else None


register(Provider(
    name="coingecko", tier="keyless", capabilities={CRYPTO, QUOTES},
    fetchers={QUOTES: _coingecko_quote}, preference=20,
    note="Crypto spot. Broader coin coverage than the exchanges, and it "
         "survives a coin being delisted from any one venue."))


def _frankfurter_quote(symbol: str) -> dict | None:
    s = symbol.upper().replace("=X", "")
    if len(s) != 6:
        return None
    base, quote = s[:3], s[3:]
    d = _json(f"https://api.frankfurter.app/latest?from={base}&to={quote}")
    rate = (d.get("rates") or {}).get(quote)
    return {"symbol": symbol, "price": float(rate), "currency": quote,
            "source": "frankfurter"} if rate else None


register(Provider(
    name="frankfurter", tier="keyless", capabilities={FX, QUOTES},
    fetchers={QUOTES: _frankfurter_quote}, preference=20,
    note="ECB reference rates. Authoritative for FX and genuinely stable, "
         "but published once a day rather than live."))


# --------------------------------------------------------------------------- #
# keyed providers — a free account, keys via a git-ignored .env
# --------------------------------------------------------------------------- #
def _finnhub_quote(symbol: str) -> dict | None:
    tok = os.environ.get("FINNHUB_API_KEY", "")
    if not tok:
        return None
    d = _json(f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={tok}")
    price = d.get("c")
    return {"symbol": symbol, "price": float(price), "currency": "USD",
            "source": "finnhub"} if price else None


register(Provider(
    name="finnhub", tier="keyed", capabilities={QUOTES, BARS},
    fetchers={QUOTES: _finnhub_quote}, env_key="FINNHUB_API_KEY",
    signup="https://finnhub.io/register", preference=5,
    note="Documented and supported, unlike Yahoo — the sturdiest upgrade "
         "available free. Also carries company news and earnings dates."))


def _twelvedata_quote(symbol: str) -> dict | None:
    tok = os.environ.get("TWELVEDATA_API_KEY", "")
    if not tok:
        return None
    d = _json(f"https://api.twelvedata.com/quote?symbol={symbol}&apikey={tok}")
    price = d.get("close")
    return {"symbol": symbol, "price": float(price), "currency":
            d.get("currency", ""), "source": "twelvedata"} if price else None


register(Provider(
    name="twelvedata", tier="keyed", capabilities={QUOTES, BARS, FX, CRYPTO},
    fetchers={QUOTES: _twelvedata_quote}, env_key="TWELVEDATA_API_KEY",
    signup="https://twelvedata.com/pricing", preference=15,
    note="Wide asset coverage on a free tier, with a tight request limit."))


def _alphavantage_quote(symbol: str) -> dict | None:
    tok = os.environ.get("ALPHAVANTAGE_API_KEY", "")
    if not tok:
        return None
    d = _json("https://www.alphavantage.co/query?function=GLOBAL_QUOTE"
              f"&symbol={symbol}&apikey={tok}")
    price = (d.get("Global Quote") or {}).get("05. price")
    return {"symbol": symbol, "price": float(price), "currency": "USD",
            "source": "alphavantage"} if price else None


register(Provider(
    name="alphavantage", tier="keyed", capabilities={QUOTES, BARS},
    fetchers={QUOTES: _alphavantage_quote}, env_key="ALPHAVANTAGE_API_KEY",
    signup="https://www.alphavantage.co/support/#api-key", preference=40,
    note="Long history, but roughly 25 requests a day free — fine for research, "
         "far too slow to drive a live screen."))


# --------------------------------------------------------------------------- #
# resolution
# --------------------------------------------------------------------------- #
def candidates(capability: str) -> list[Provider]:
    """Enabled, configured providers for a capability, best first."""
    out = [p for p in REGISTRY.values()
           if capability in p.capabilities and p.configured
           and is_enabled(p.name) and capability in p.fetchers]
    return sorted(out, key=lambda p: p.preference)


def fetch(capability: str, *args, **kw) -> dict | None:
    """First provider that answers wins; failures fall through silently.

    Deliberately silent per-provider: one vendor being down is an expected
    state, not an error worth propagating, and the caller only cares whether
    *some* source answered. :func:`status` is where you look to see who is
    actually carrying the load.
    """
    for p in candidates(capability):
        try:
            out = p.fetchers[capability](*args, **kw)
            if out:
                out.setdefault("provider", p.name)
                return out
        except Exception:
            continue
    return None


def status() -> dict:
    """Everything registered, what it can do, and whether it is usable now."""
    rows = [p.status() for p in sorted(REGISTRY.values(),
                                       key=lambda p: (p.tier, p.preference))]
    active = {c: [p.name for p in candidates(c)]
              for c in (QUOTES, BARS, FX, CRYPTO)}
    return {"providers": rows, "active": active,
            "generated": int(time.time()),
            "keyless_available": sum(1 for r in rows
                                     if r["tier"] == "keyless" and r["enabled"]),
            "keyed_configured": sum(1 for r in rows
                                    if r["tier"] == "keyed" and r["configured"])}
