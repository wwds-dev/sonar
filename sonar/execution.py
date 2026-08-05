"""The execution guard — safety logic, built and tested against a simulator.

This module contains **no broker integration**. It talks to an abstract
:class:`BrokerPort`, and the only implementation shipped here is
:class:`SimBroker`, which fills orders against SONAR's own paper prices. That
is deliberate: the guard is the part that deserves scrutiny, and building it
against a simulator means every rule in it can actually be tested — caps,
idempotency, confirmation, the audit log, the kill switch — none of which could
be exercised against a real broker without an account and a funded session.

If a real venue is ever connected, it implements :class:`BrokerPort` and the
guard is unchanged. The rules below are the contract.

What it enforces
----------------
**Confirmation.** :meth:`Guard.submit` refuses an intent a human has not
approved. Nothing here auto-trades; a model signal is an input to a decision,
never a trigger for one.

**Idempotency.** Each intent carries a client order id derived from its own
economic content plus a nonce, recorded *before* the send. A double-click, an
impatient retry, or a UI event firing twice cannot become two positions.

**Hard caps, evaluated locally.** Max notional per order, max orders per day,
max open positions, max quantity, and an instrument allowlist — all checked
before anything leaves this process, so a runaway loop stops here.

**Fail closed.** An empty allowlist permits nothing. An unpriced order is
rejected because it has no notional to cap. An unknown outcome halts the guard.

**An audit log.** Append-only JSONL under Application Support: every intent,
every decision, every reply. It is the record if you ever have to reconstruct
what happened.

**A kill switch.** :meth:`Guard.panic` cancels working orders and latches
closed until explicitly resumed.

What it deliberately does not do
--------------------------------
Retry a submission. If one fails with an unknown outcome the position state is
*unknown*, and the correct response is to reconcile against the venue — never
to send again. See :meth:`Guard.reconcile`.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Protocol

from . import paths

# Caps are intentionally small. They are a backstop against a bug, not a
# position-sizing strategy — sizing lives in risk.py and is a separate decision.
DEFAULT_LIMITS = {
    "max_order_notional": 500.0,
    "max_orders_per_day": 10,
    "max_open_positions": 5,
    "max_quantity": 100.0,
}

# Fail closed: an empty allowlist permits nothing, not everything.
DEFAULT_ALLOWLIST: tuple[str, ...] = ()


class ExecutionError(RuntimeError):
    """A venue-side failure. Outcome may be unknown."""


class GuardRejection(RuntimeError):
    """The guard refused. Nothing was sent."""


# --------------------------------------------------------------------------- #
# The port. Any venue implements this; the guard knows nothing else about it.
# --------------------------------------------------------------------------- #
class BrokerPort(Protocol):
    def describe(self) -> dict: ...
    def place(self, coid: str, symbol: str, side: str, quantity: float,
              limit_price: float) -> dict: ...
    def cancel(self, order_id: str) -> dict: ...
    def working_orders(self) -> list[dict]: ...
    def positions(self) -> list[dict]: ...


@dataclass
class OrderIntent:
    """A proposed order. Inert until confirmed."""

    symbol: str
    side: str                       # BUY | SELL
    quantity: float
    limit_price: float | None = None
    tif: str = "DAY"
    source: str = "manual"          # what proposed it — never what sends it
    note: str = ""
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    confirmed: bool = False
    created: float = field(default_factory=time.time)

    @property
    def notional(self) -> float | None:
        if self.limit_price is None:
            return None
        return round(self.quantity * self.limit_price, 2)

    @property
    def client_order_id(self) -> str:
        """Stable per intent, distinct across intents.

        Hashed from the economic content *plus* a nonce, so two genuinely
        separate orders for the same thing still differ, while re-submitting
        the same intent object cannot produce a second order.
        """
        h = hashlib.sha256(
            f"{self.symbol}|{self.side}|{self.quantity}|"
            f"{self.limit_price}|{self.nonce}".encode()).hexdigest()[:16]
        return f"sonar-{h}"

    def describe(self) -> str:
        """The exact line a human confirms. Must be unambiguous."""
        px = f"@ {self.limit_price:,.2f}" if self.limit_price is not None else "at MARKET"
        val = f"  (≈{self.notional:,.2f})" if self.notional is not None else ""
        return (f"{self.side} {self.quantity:g} {self.symbol} {px}{val}  TIF={self.tif}")


class AuditLog:
    """Append-only JSONL. Never rewritten or truncated by this module."""

    def __init__(self, path=None) -> None:
        self.path = path or (paths.user_data_base() / "execution_audit.jsonl")

    def write(self, event: str, **fields) -> None:
        rec = {"t": time.time(), "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "event": event, **fields}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
        except OSError:
            pass          # logging must never break the flow it observes

    def _records(self):
        try:
            with self.path.open() as fh:
                for line in fh:
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
        except OSError:
            return

    def today_count(self, event: str = "submitted") -> int:
        today = date.today().isoformat()
        return sum(1 for r in self._records()
                   if r.get("event") == event
                   and str(r.get("iso", "")).startswith(today))

    def seen_client_id(self, coid: str) -> bool:
        return any(r.get("client_order_id") == coid for r in self._records())


class SimBroker:
    """A simulated venue — the only implementation shipped with SONAR.

    Fills marketable limit orders instantly at the limit price and tracks
    positions in memory. It exists so the guard's rules can be tested, and so
    the UI has something honest to talk to. It moves no money and reaches no
    network.
    """

    def __init__(self, reject: bool = False, fail: bool = False) -> None:
        self.orders: list[dict] = []
        self._positions: dict[str, dict] = {}
        self.reject = reject      # simulate a venue rejection
        self.fail = fail          # simulate an unknown-outcome failure

    def describe(self) -> dict:
        return {"venue": "simulator", "kind": "paper",
                "detail": "in-process simulator — no network, no money"}

    def place(self, coid, symbol, side, quantity, limit_price) -> dict:
        if self.fail:
            raise ExecutionError("simulated transport failure — outcome unknown")
        if self.reject:
            return {"client_order_id": coid, "status": "Rejected",
                    "reason": "simulated rejection"}
        oid = f"sim-{len(self.orders) + 1}"
        rec = {"order_id": oid, "client_order_id": coid, "symbol": symbol,
               "side": side, "quantity": quantity, "limit_price": limit_price,
               "status": "Filled", "filled": quantity, "avg_price": limit_price}
        self.orders.append(rec)
        pos = self._positions.setdefault(symbol, {"symbol": symbol, "quantity": 0.0,
                                                  "avg_price": 0.0})
        delta = quantity if side == "BUY" else -quantity
        pos["quantity"] += delta
        pos["avg_price"] = limit_price
        return rec

    def cancel(self, order_id) -> dict:
        for o in self.orders:
            if o["order_id"] == order_id and o["status"] not in ("Filled", "Cancelled"):
                o["status"] = "Cancelled"
                return {"order_id": order_id, "status": "Cancelled"}
        return {"order_id": order_id, "status": "not-working"}

    def working_orders(self) -> list[dict]:
        return [o for o in self.orders if o["status"] not in ("Filled", "Cancelled",
                                                              "Rejected")]

    def positions(self) -> list[dict]:
        return [p for p in self._positions.values() if p["quantity"] != 0]


class Guard:
    """The only supported way to submit an order from SONAR."""

    def __init__(self, broker: BrokerPort | None = None,
                 limits: dict | None = None,
                 allowlist: tuple[str, ...] = DEFAULT_ALLOWLIST,
                 audit: AuditLog | None = None) -> None:
        self.broker: BrokerPort = broker or SimBroker()
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        self.allowlist = tuple(s.upper() for s in allowlist)
        self.audit = audit or AuditLog()
        self.halted = False
        self.halt_reason = ""
        self._sent: set[str] = set()

    def status(self) -> dict:
        return {
            "venue": self.broker.describe(),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "orders_today": self.audit.today_count(),
            "limits": dict(self.limits),
            "allowlist": list(self.allowlist),
            "open_positions": len(self.broker.positions()),
        }

    # -- the gate ---------------------------------------------------------- #
    def check(self, intent: OrderIntent) -> list[str]:
        """Every reason this intent must not be sent. Empty list means allowed."""
        problems: list[str] = []
        L = self.limits

        if self.halted:
            problems.append(f"guard halted: {self.halt_reason or 'kill switch engaged'}")

        if intent.symbol.upper() not in self.allowlist:
            problems.append(f"{intent.symbol} is not on the instrument allowlist")
        if intent.side.upper() not in ("BUY", "SELL"):
            problems.append(f"bad side {intent.side!r}")
        if intent.quantity <= 0:
            problems.append("quantity must be positive")
        elif intent.quantity > L["max_quantity"]:
            problems.append(f"quantity {intent.quantity:g} exceeds cap {L['max_quantity']:g}")

        if intent.limit_price is None or intent.limit_price <= 0:
            problems.append("unpriced order rejected — without a limit price there "
                            "is no notional to cap, so it cannot be risk-checked")
        else:
            n = intent.notional or 0.0
            if n > L["max_order_notional"]:
                problems.append(f"notional {n:,.2f} exceeds per-order cap "
                                f"{L['max_order_notional']:,.2f}")

        used = self.audit.today_count()
        if used >= L["max_orders_per_day"]:
            problems.append(f"daily order cap reached ({used}/{L['max_orders_per_day']})")

        if len(self.broker.positions()) >= L["max_open_positions"]:
            problems.append(f"already at max open positions ({L['max_open_positions']})")

        coid = intent.client_order_id
        if coid in self._sent or self.audit.seen_client_id(coid):
            problems.append("this exact intent was already submitted (idempotency)")

        return problems

    def submit(self, intent: OrderIntent) -> dict:
        """Send, if and only if every rule above allows it."""
        if not intent.confirmed:
            raise GuardRejection(
                "intent not confirmed — SONAR never submits an order a human "
                "has not explicitly approved")

        problems = self.check(intent)
        if problems:
            self.audit.write("rejected", intent=asdict(intent), problems=problems)
            raise GuardRejection("; ".join(problems))

        coid = intent.client_order_id
        # Recorded BEFORE the call, not after: if it times out we must still be
        # unable to send it a second time.
        self._sent.add(coid)
        self.audit.write("submitted", client_order_id=coid, intent=asdict(intent),
                         describe=intent.describe())

        try:
            reply = self.broker.place(
                coid=coid, symbol=intent.symbol.upper(), side=intent.side.upper(),
                quantity=intent.quantity, limit_price=intent.limit_price)
        except Exception as exc:
            self.audit.write("submit_error", client_order_id=coid, error=str(exc),
                             note="OUTCOME UNKNOWN — reconcile, do not resend")
            self.halt(f"submission failed with unknown outcome: {exc}")
            raise ExecutionError(str(exc)) from exc

        self.audit.write("venue_reply", client_order_id=coid, reply=reply)
        return {"client_order_id": coid, "reply": reply}

    # -- safety ------------------------------------------------------------ #
    def halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason
        self.audit.write("halted", reason=reason)

    def resume(self) -> None:
        self.audit.write("resumed", was=self.halt_reason)
        self.halted = False
        self.halt_reason = ""

    def panic(self) -> dict:
        """Kill switch: cancel working orders, then latch closed."""
        self.audit.write("panic_requested")
        results = []
        for o in self.broker.working_orders():
            try:
                results.append(self.broker.cancel(o["order_id"]))
            except Exception as exc:
                results.append({"order_id": o.get("order_id"), "error": str(exc)})
        self.halt("kill switch engaged")
        self.audit.write("panic_done", results=results)
        return {"cancelled": results}

    def reconcile(self) -> dict:
        """Venue state is the truth. Call after any uncertain outcome."""
        orders = self.broker.working_orders()
        positions = self.broker.positions()
        self.audit.write("reconciled", n_orders=len(orders), n_positions=len(positions))
        return {"orders": orders, "positions": positions}
