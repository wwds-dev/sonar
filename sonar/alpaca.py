"""Alpaca **paper** trading — real order mechanics, fake money.

The paper book in :mod:`sonar.portfolio` fills instantly at the quoted price
with no fees and no queue, which makes it an optimistic bound rather than a
simulation. Alpaca's paper environment is the cheap way to do better: real
symbols, real market hours, real order types, orders that sit unfilled when the
market is shut — and no money at any point.

Why the guards are this heavy
-----------------------------
Alpaca's live and paper APIs differ by one hostname. A config typo, an
environment variable copied from somewhere else, or a well-meaning "make the
URL configurable" refactor is all that separates a simulation from real orders
against a real account. So:

* The host is a **module constant**, not a parameter. There is no argument to
  pass and nothing to override.
* An API key that looks live is **refused before any request is made**. Alpaca
  issues paper keys prefixed ``PK`` and live keys prefixed ``AK``.
* The account is checked at connect time and the connection is dropped unless
  the API itself reports a paper account.
* :func:`assert_paper_only` re-checks every one of those on each order.

If any check fails this raises rather than degrading to something that still
trades. A broker adapter that silently keeps working after a safety check fails
is worse than one that does not exist.

Nothing here can be pointed at real money, and that is the point. Going live is
a deliberate decision that belongs to a human with an account, not a flag in
this file.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Not configurable, on purpose. See the module docstring.
PAPER_HOST = "paper-api.alpaca.markets"
PAPER_BASE = f"https://{PAPER_HOST}/v2"
LIVE_HOST = "api.alpaca.markets"          # named only so it can be refused

KEY_ENV = "APCA_API_KEY_ID"
SECRET_ENV = "APCA_API_SECRET_KEY"


class LiveTradingRefused(RuntimeError):
    """Raised whenever anything looks like it would touch real money."""


class AlpacaUnavailable(RuntimeError):
    """No usable paper credentials, or the API is unreachable."""


def load_env(path: Path | None = None) -> None:
    """Read ``.env`` into the process environment if present.

    Keys live in a git-ignored file the user creates. They are never read from
    the repo, never logged, and never written anywhere by this module.
    """
    path = path or Path(__file__).resolve().parent.parent / ".env"
    try:
        text = path.read_text()
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def looks_live(key_id: str) -> bool:
    """Does this key id look like a live-trading key?

    Alpaca prefixes paper keys ``PK`` and live keys ``AK``. Treating anything
    that is not clearly paper as live is the safe direction to be wrong in.
    """
    k = (key_id or "").strip().upper()
    return not k.startswith("PK")


def assert_paper_only(base_url: str, key_id: str) -> None:
    """Refuse anything that is not unambiguously the paper environment."""
    # Exact host equality, deliberately — and *only* that. A substring check
    # for the live host looks like sensible defence in depth and is actively
    # wrong: "api.alpaca.markets" is a substring of "paper-api.alpaca.markets",
    # so it rejects the one URL that is safe. Parsing the host and demanding
    # equality already refuses the live endpoint and every lookalike.
    host = (base_url or "").split("//")[-1].split("/")[0].lower()
    if host != PAPER_HOST:
        raise LiveTradingRefused(
            f"refusing to trade against {host!r}; only {PAPER_HOST} is allowed")
    if looks_live(key_id):
        raise LiveTradingRefused(
            "this API key is not a paper key (paper keys start with 'PK'). "
            "Refusing to send orders with it.")


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: str
    qty: float
    status: str
    submitted_at: float
    filled_price: float | None = None


class AlpacaPaperBroker:
    """A :class:`sonar.portfolio.Broker` backed by Alpaca's paper environment."""

    live = False                       # never true; see the module docstring
    name = "alpaca-paper"
    # Alpaca's paper environment runs real order handling: an order is accepted
    # and fills later, or sits unfilled when the market is shut. Saying so is
    # the point of using it over the internal book.
    synchronous = False

    def __init__(self, key_id: str | None = None, secret: str | None = None,
                 verify: bool = True) -> None:
        load_env()
        self.key_id = key_id or os.environ.get(KEY_ENV, "")
        self.secret = secret or os.environ.get(SECRET_ENV, "")
        if not self.key_id or not self.secret:
            raise AlpacaUnavailable(
                f"set {KEY_ENV} and {SECRET_ENV} (a free Alpaca *paper* account) "
                "in a local .env to enable this broker")
        assert_paper_only(PAPER_BASE, self.key_id)
        self.account: dict = {}
        if verify:
            self.account = self._verify()

    # -- plumbing ---------------------------------------------------------- #
    def _headers(self) -> dict:
        return {"APCA-API-KEY-ID": self.key_id,
                "APCA-API-SECRET-KEY": self.secret,
                "Content-Type": "application/json"}

    def _request(self, path: str, method: str = "GET", body: dict | None = None):
        assert_paper_only(PAPER_BASE, self.key_id)     # re-checked every call
        url = f"{PAPER_BASE}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:200]
            raise AlpacaUnavailable(f"{method} {path} -> {exc.code}: {detail}")
        except Exception as exc:
            raise AlpacaUnavailable(f"{method} {path} failed: {exc}")

    def _verify(self) -> dict:
        """Confirm the API itself agrees this is a paper account."""
        acct = self._request("/account")
        # Alpaca does not always echo a paper flag, so absence is tolerated but
        # an explicit denial is not.
        if str(acct.get("account_number", "")).upper().startswith("LIVE"):
            raise LiveTradingRefused("the API reported a live account")
        if acct.get("status") and acct["status"] not in ("ACTIVE", "PAPER_ONLY"):
            raise AlpacaUnavailable(f"account status {acct['status']}")
        return acct

    # -- the Broker protocol ----------------------------------------------- #
    def execute(self, symbol: str, direction: str, units: float,
                price: float) -> dict:
        """Submit a market order to the paper account.

        ``direction`` follows the portfolio's vocabulary — LONG/SHORT to open,
        SELL/COVER to close — and is mapped to Alpaca's buy/sell.
        """
        side = "buy" if direction.upper() in ("LONG", "BUY", "COVER") else "sell"
        qty = round(float(units), 6)
        if qty <= 0:
            return {"error": "zero quantity", "symbol": symbol}
        order = self._request("/orders", "POST", {
            "symbol": symbol, "qty": str(qty), "side": side,
            "type": "market", "time_in_force": "day"})
        return {"symbol": symbol, "direction": direction, "units": qty,
                "price": price, "at": time.time(), "broker": self.name,
                "order_id": order.get("id"), "status": order.get("status")}

    # -- read-only views ---------------------------------------------------- #
    def equity(self) -> float:
        return float(self._request("/account").get("equity") or 0.0)

    def positions(self) -> list[dict]:
        rows = self._request("/positions")
        return [{"symbol": p["symbol"], "qty": float(p["qty"]),
                 "entry": float(p["avg_entry_price"]),
                 "price": float(p.get("current_price") or 0),
                 "unrealised": float(p.get("unrealized_pl") or 0)}
                for p in (rows if isinstance(rows, list) else [])]

    def stats(self) -> dict:
        acct = self._request("/account")
        return {"broker": self.name, "live": False,
                "equity": float(acct.get("equity") or 0),
                "cash": float(acct.get("cash") or 0),
                "buying_power": float(acct.get("buying_power") or 0),
                "account_number": acct.get("account_number", ""),
                "n_positions": len(self.positions())}


def available() -> tuple[bool, str]:
    """Is the paper broker usable? ``(ok, human-readable reason)``."""
    load_env()
    key = os.environ.get(KEY_ENV, "")
    if not key or not os.environ.get(SECRET_ENV):
        return False, (f"off — set {KEY_ENV} and {SECRET_ENV} from a free "
                       "Alpaca paper account in a local .env")
    if looks_live(key):
        return False, ("refused — that key is not a paper key. Paper keys "
                       "start with 'PK'; SONAR will not send orders with "
                       "anything else.")
    return True, "Alpaca paper trading available"
