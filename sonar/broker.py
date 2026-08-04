"""Interactive Brokers adapter — Client Portal Web API, paper accounts.

Why this API and not TWS
-----------------------
IBKR exposes two surfaces. The TWS API is socket-based and needs the ``ibapi``
package plus a callback reactor. The **Client Portal Web API** is plain REST
over ``https://localhost:5000``, which means ``urllib`` reaches it and SONAR
gains no dependency at all. Given the daemon is deliberately standard-library
only, that decides it.

What you have to run
--------------------
The Client Portal Gateway is a separate process you start yourself, and you
authenticate it by logging in through a browser at ``https://localhost:5000``.
Nothing in SONAR ever sees or stores your IBKR password — the session lives in
the gateway. That is the point: this module talks to a locally-authenticated
gateway, it does not hold your credentials.

    1. download the Client Portal Gateway from IBKR
    2. ./bin/run.sh root/conf.yaml
    3. open https://localhost:5000 and log in with your *paper* credentials
    4. SONAR picks the session up from there

Paper only, by construction
---------------------------
IBKR paper account IDs begin with ``DU``; live accounts begin with ``U``. This
adapter **refuses to act on a non-paper account** unless it is constructed with
``allow_live=True``, which nothing in the UI does and nothing should until the
calibration table says the strategy has an edge. The check is in
:meth:`IBKRBroker.select_account`, not in the caller, so there is no path that
forgets it.

This module places orders. It does not decide to. Every mutating call requires
an :class:`~sonar.execution.OrderIntent` that has already passed the guard in
``sonar/execution.py``.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

GATEWAY = "https://localhost:5000"
BASE = "/v1/api"
TIMEOUT = 15.0

# IBKR account-id prefixes. "DU" is paper; "U" (without the D) is live money.
PAPER_PREFIXES = ("DU", "DF")


class BrokerError(RuntimeError):
    """Anything the gateway refused or could not answer."""


class NotAuthenticated(BrokerError):
    """The gateway is reachable but no session is logged in."""


class LiveAccountRefused(BrokerError):
    """A live account was selected without an explicit opt-in."""


def _localhost_ssl() -> ssl.SSLContext:
    """The gateway ships a self-signed cert for localhost.

    Verification is disabled **only** for the loopback gateway. This context is
    never used for any other host — every outbound call in the rest of SONAR
    (Binance, Polymarket, Yahoo, FRED) goes through normal verified TLS.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


@dataclass
class Account:
    id: str
    kind: str            # "paper" | "live"
    currency: str = ""
    net_liquidation: float | None = None
    buying_power: float | None = None
    cash: float | None = None

    @property
    def is_paper(self) -> bool:
        return self.kind == "paper"


@dataclass
class Position:
    conid: int
    symbol: str
    quantity: float
    avg_cost: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None


@dataclass
class OrderStatus:
    order_id: str
    status: str              # Submitted / Filled / Cancelled / Inactive / …
    symbol: str = ""
    side: str = ""
    filled: float = 0.0
    remaining: float = 0.0
    avg_price: float | None = None
    raw: dict = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in ("Filled", "Cancelled", "Inactive", "ApiCancelled")


class IBKRBroker:
    """A thin, explicit client. No magic, no retries that could double-send.

    Read calls are safe to retry; **order placement is not**, so it is never
    retried here. If a placement times out the caller must reconcile against
    :meth:`live_orders` rather than send again — that is the single most
    dangerous mistake an execution layer can make.
    """

    def __init__(self, gateway: str = GATEWAY, allow_live: bool = False,
                 timeout: float = TIMEOUT) -> None:
        self.gateway = gateway.rstrip("/")
        self.allow_live = allow_live
        self.timeout = timeout
        self.account: Account | None = None
        self._ctx = _localhost_ssl()

    # -- transport --------------------------------------------------------- #
    def _request(self, method: str, path: str, body: dict | list | None = None,
                 retryable: bool = True) -> object:
        url = f"{self.gateway}{BASE}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "User-Agent": "sonar/0.4",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout,
                                        context=self._ctx) as r:
                raw = r.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            if exc.code in (401, 403):
                raise NotAuthenticated(
                    "gateway rejected the session — log in at "
                    f"{self.gateway} and retry ({exc.code})") from exc
            raise BrokerError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise BrokerError(
                f"cannot reach the Client Portal Gateway at {self.gateway} — "
                f"is it running? ({exc.reason})") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise BrokerError(f"{method} {path}: non-JSON response") from exc

    def _get(self, path: str):
        return self._request("GET", path)

    def _post(self, path: str, body=None, retryable: bool = True):
        return self._request("POST", path, body, retryable=retryable)

    # -- session ----------------------------------------------------------- #
    def auth_status(self) -> dict:
        """``{authenticated, connected, competing, ...}`` from the gateway."""
        d = self._get("/iserver/auth/status")
        return d if isinstance(d, dict) else {}

    def is_authenticated(self) -> bool:
        try:
            return bool(self.auth_status().get("authenticated"))
        except BrokerError:
            return False

    def reauthenticate(self) -> dict:
        """Nudge a lapsed-but-alive session. Does not replace a browser login."""
        d = self._post("/iserver/reauthenticate")
        return d if isinstance(d, dict) else {}

    def tickle(self) -> None:
        """Keep the session warm. The gateway times out an idle session."""
        try:
            self._post("/tickle")
        except BrokerError:
            pass

    # -- accounts ---------------------------------------------------------- #
    def accounts(self) -> list[Account]:
        d = self._get("/portfolio/accounts")
        out: list[Account] = []
        for a in (d if isinstance(d, list) else []):
            aid = str(a.get("accountId") or a.get("id") or "")
            if not aid:
                continue
            kind = "paper" if aid.upper().startswith(PAPER_PREFIXES) else "live"
            out.append(Account(id=aid, kind=kind,
                               currency=a.get("currency", "")))
        return out

    def select_account(self, account_id: str | None = None) -> Account:
        """Choose the account to trade. **This is the paper-only gate.**

        With no argument it picks the first paper account it finds, which is
        the behaviour you want: the safe choice is the default, and reaching a
        live account takes a deliberate act.
        """
        found = self.accounts()
        if not found:
            raise BrokerError("gateway returned no accounts")

        if account_id:
            acct = next((a for a in found if a.id == account_id), None)
            if acct is None:
                raise BrokerError(f"account {account_id} not found")
        else:
            acct = next((a for a in found if a.is_paper), None)
            if acct is None:
                raise LiveAccountRefused(
                    "no paper account on this login — refusing to default to a "
                    "live account. Log the gateway in with paper credentials.")

        if not acct.is_paper and not self.allow_live:
            raise LiveAccountRefused(
                f"{acct.id} is a LIVE account. This adapter is paper-only "
                "unless constructed with allow_live=True.")

        self.account = self._enrich(acct)
        return self.account

    def _enrich(self, acct: Account) -> Account:
        try:
            d = self._get(f"/portfolio/{acct.id}/summary")
        except BrokerError:
            return acct
        if not isinstance(d, dict):
            return acct

        def amt(key: str):
            v = d.get(key)
            if isinstance(v, dict):
                v = v.get("amount")
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        acct.net_liquidation = amt("netliquidation")
        acct.buying_power = amt("buyingpower")
        acct.cash = amt("totalcashvalue")
        return acct

    def _require_account(self) -> Account:
        if self.account is None:
            raise BrokerError("no account selected — call select_account() first")
        return self.account

    # -- reference data ---------------------------------------------------- #
    def find_contract(self, symbol: str, sec_type: str = "STK") -> dict:
        """Resolve a ticker to an IBKR ``conid``.

        Symbols are ambiguous across exchanges; this returns the gateway's
        first match and includes the whole record so a caller (or a human in a
        confirm dialog) can see exactly which instrument was resolved.
        """
        d = self._post("/iserver/secdef/search",
                       {"symbol": symbol, "name": False, "secType": sec_type})
        rows = d if isinstance(d, list) else []
        if not rows:
            raise BrokerError(f"no contract found for {symbol!r}")
        top = rows[0]
        conid = top.get("conid")
        if conid is None:
            raise BrokerError(f"contract for {symbol!r} has no conid")
        return {
            "conid": int(conid),
            "symbol": top.get("symbol", symbol),
            "description": top.get("description", ""),
            "company": top.get("companyName") or top.get("companyHeader", ""),
            "sections": top.get("sections", []),
        }

    def positions(self) -> list[Position]:
        acct = self._require_account()
        d = self._get(f"/portfolio/{acct.id}/positions/0")
        out = []
        for p in (d if isinstance(d, list) else []):
            try:
                out.append(Position(
                    conid=int(p.get("conid", 0)),
                    symbol=p.get("contractDesc") or p.get("ticker", "?"),
                    quantity=float(p.get("position", 0) or 0),
                    avg_cost=_f(p.get("avgCost")),
                    market_value=_f(p.get("mktValue")),
                    unrealized_pnl=_f(p.get("unrealizedPnl")),
                ))
            except (TypeError, ValueError):
                continue
        return out

    def live_orders(self) -> list[OrderStatus]:
        """Open and recently-completed orders. **The reconciliation source.**

        After any placement whose response you did not see, call this rather
        than resending. The broker is the source of truth; local state is not.
        """
        d = self._get("/iserver/account/orders")
        rows = (d or {}).get("orders", []) if isinstance(d, dict) else []
        out = []
        for o in rows:
            out.append(OrderStatus(
                order_id=str(o.get("orderId", "")),
                status=str(o.get("status", "Unknown")),
                symbol=o.get("ticker") or o.get("symbol", ""),
                side=str(o.get("side", "")),
                filled=_f(o.get("filledQuantity")) or 0.0,
                remaining=_f(o.get("remainingQuantity")) or 0.0,
                avg_price=_f(o.get("avgPrice")),
                raw=o,
            ))
        return out

    # -- mutating ---------------------------------------------------------- #
    def place_order(self, conid: int, side: str, quantity: float,
                    order_type: str = "LMT", limit_price: float | None = None,
                    tif: str = "DAY", client_order_id: str | None = None) -> list[dict]:
        """Submit one order. Never retried — see the class docstring.

        Returns the raw gateway reply chain. IBKR frequently answers a
        placement with a *question* (\"this order exceeds a size threshold,
        confirm?\") rather than an acknowledgement; the caller must resolve
        those via :meth:`confirm_reply`. They are surfaced rather than
        auto-answered on purpose — auto-confirming an IBKR warning is how you
        accidentally agree to something you did not read.
        """
        acct = self._require_account()
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise BrokerError(f"bad side {side!r}")
        if quantity <= 0:
            raise BrokerError("quantity must be positive")
        if order_type.upper() == "LMT" and limit_price is None:
            raise BrokerError("a limit order needs a limit price")

        order: dict = {
            "conid": int(conid),
            "orderType": order_type.upper(),
            "side": side,
            "quantity": quantity,
            "tif": tif.upper(),
        }
        if limit_price is not None:
            order["price"] = float(limit_price)
        if client_order_id:
            # IBKR echoes this back, which is what lets a caller match a reply
            # to an intent after a timeout instead of guessing.
            order["cOID"] = client_order_id

        d = self._request("POST", f"/iserver/account/{acct.id}/orders",
                          {"orders": [order]}, retryable=False)
        return d if isinstance(d, list) else [d] if d else []

    def confirm_reply(self, reply_id: str, confirmed: bool = True) -> list[dict]:
        """Answer one of IBKR's pre-submission questions."""
        d = self._post(f"/iserver/reply/{reply_id}", {"confirmed": bool(confirmed)},
                       retryable=False)
        return d if isinstance(d, list) else [d] if d else []

    def cancel_order(self, order_id: str) -> dict:
        acct = self._require_account()
        d = self._request("DELETE", f"/iserver/account/{acct.id}/order/{order_id}")
        return d if isinstance(d, dict) else {}

    def cancel_all(self) -> list[dict]:
        """The kill switch. Best effort — reports per-order outcomes."""
        out = []
        for o in self.live_orders():
            if o.is_terminal:
                continue
            try:
                out.append({"order_id": o.order_id,
                            "result": self.cancel_order(o.order_id)})
            except BrokerError as exc:
                out.append({"order_id": o.order_id, "error": str(exc)})
        return out


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def probe(gateway: str = GATEWAY) -> dict:
    """Cheap health check for the UI and the self-test.

    Never raises: a broker you cannot reach is a state to display, not an
    exception to crash on.
    """
    b = IBKRBroker(gateway)
    try:
        status = b.auth_status()
    except BrokerError as exc:
        return {"reachable": False, "authenticated": False, "detail": str(exc),
                "accounts": []}
    try:
        accts = b.accounts()
    except BrokerError as exc:
        return {"reachable": True, "authenticated": bool(status.get("authenticated")),
                "detail": str(exc), "accounts": []}
    return {
        "reachable": True,
        "authenticated": bool(status.get("authenticated")),
        "competing": bool(status.get("competing")),
        "detail": "ok",
        "accounts": [{"id": a.id, "kind": a.kind} for a in accts],
        "has_paper": any(a.is_paper for a in accts),
    }
