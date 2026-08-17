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

**A kill switch that actually flattens.** :meth:`Guard.panic` cancels working
orders, closes every open position, then latches shut. :meth:`Guard.flatten`
does the closing half and is deliberately exempt from the halt latch, the daily
order cap and every other limit — see its docstring for why exemptions that look
like holes are the point.

**Reconciliation against the venue.** :meth:`Guard.reconcile` reads venue state,
and when handed what this process *believes* it holds, halts on any
disagreement. Call it at startup: a position opened by hand in the broker's own
app is invisible to local state, and trading on top of a wrong picture is how a
small bug becomes a large one.

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
    # Checked against equity read from the venue, not from local state. A local
    # bankroll that has gone stale after a drawdown sizes every later position
    # too large, in the direction that compounds.
    "max_notional_pct_equity": 0.10,
}

# Fail closed: an empty allowlist permits nothing, not everything.
DEFAULT_ALLOWLIST: tuple[str, ...] = ()

# How far through the book a flattening order is priced. A limit at the mark may
# simply not fill, which leaves exposure open during the one operation whose
# whole purpose is removing it; a market order has no worst case at all. Pricing
# through the mark gives a marketable limit: it crosses the spread like a market
# order but caps how bad the fill can be.
FLATTEN_SLIPPAGE = 0.01

# Quantities are fractional on crypto, so position comparison needs a tolerance
# rather than equality. Small enough that a real difference never hides under it.
POSITION_EPSILON = 1e-9

# States after which no more fills can arrive. Venues spell these differently
# and inconsistently, so the set is generous and matching is case-insensitive.
# Anything unrecognised is treated as *still working*: waiting on an order that
# is actually finished costs a delay, while settling one that is still live
# records a fill quantity that can still change.
TERMINAL_STATUSES = frozenset({
    "filled", "canceled", "cancelled", "rejected", "expired", "done_for_day",
    "closed", "stopped",
})


def _f(x, default: float = 0.0) -> float:
    """Coerce a venue-supplied number. Venues send quantities as strings, as
    ``None``, and occasionally as both across two fields of one response."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


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

    def order_status(self, coid: str) -> dict:
        """One order's current state, looked up by *client* order id.

        By client id rather than venue id because that is what survives a crash
        between the send and the reply: the client id is written to the audit
        log before the request leaves, the venue's id may never arrive.

        Returns at least ``status``. When terminal, also the filled quantity,
        the average fill price and any commission — ``filled``/``filled_qty``,
        ``avg_price``/``filled_avg_price``, ``fee``/``commission`` are all read.
        """

    def positions(self) -> list[dict]:
        """Open positions, each with at least ``symbol`` and a **signed**
        quantity under ``quantity`` (``qty`` is accepted, since venues name it
        that way). A ``price`` or ``avg_price`` lets :meth:`Guard.flatten` price
        a closing order without being handed one."""

    def equity(self) -> float:
        """Account equity, read from the venue.

        Required, not optional: the guard sizes its notional cap against this,
        and a port that cannot answer is refused rather than waved through. An
        adapter that returns a local guess here has removed the check while
        leaving it looking present."""


@dataclass
class OrderIntent:
    """A proposed order. Inert until confirmed."""

    symbol: str
    side: str                       # BUY | SELL
    quantity: float
    limit_price: float | None = None
    # The mark the decision was made at, when it differs from the limit. A
    # marketable limit is deliberately priced through the book, so measuring
    # slippage against the limit would score that deliberate offset as a cost
    # (or, closing, as free money). Cost is measured against this instead.
    reference_price: float | None = None
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
    def benchmark(self) -> float | None:
        """The price this order's execution is scored against."""
        return self.reference_price if self.reference_price else self.limit_price

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

    def records(self):
        """Every record, oldest first. Malformed lines are skipped rather than
        raising: a truncated final line after a crash must not make the whole
        history unreadable."""
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
        return sum(1 for r in self.records()
                   if r.get("event") == event
                   and str(r.get("iso", "")).startswith(today))

    def seen_client_id(self, coid: str) -> bool:
        return any(r.get("client_order_id") == coid for r in self.records())


class SimBroker:
    """A simulated venue — the only implementation shipped with SONAR.

    Fills marketable limit orders instantly at the limit price and tracks
    positions in memory. It exists so the guard's rules can be tested, and so
    the UI has something honest to talk to. It moves no money and reaches no
    network.
    """

    def __init__(self, reject: bool = False, fail: bool = False,
                 equity: float = 100_000.0, fee_rate: float = 0.0) -> None:
        self.orders: list[dict] = []
        self._positions: dict[str, dict] = {}
        self.reject = reject      # simulate a venue rejection
        self.fail = fail          # simulate an unknown-outcome failure
        self._equity = equity
        self.fee_rate = fee_rate  # 0 by default: the simulator is free, and says so

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
               "status": "Filled", "filled": quantity, "avg_price": limit_price,
               "fee": round(quantity * limit_price * self.fee_rate, 6)}
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

    def equity(self) -> float:
        return self._equity

    def order_status(self, coid: str) -> dict:
        for o in self.orders:
            if o["client_order_id"] == coid:
                return dict(o)
        return {"client_order_id": coid, "status": "unknown"}


def side_for_direction(direction: str) -> str:
    """Map the portfolio's vocabulary onto an order side.

    LONG/SHORT open, SELL/COVER close. Both closing directions invert: you sell
    to close a long and buy to close a short. This mirrors the mapping in
    :mod:`sonar.alpaca`; a test asserts the two stay in agreement.
    """
    return "BUY" if direction.upper() in ("LONG", "BUY", "COVER") else "SELL"


class GuardedBroker:
    """Presents :class:`sonar.portfolio.Broker` while enforcing the :class:`Guard`.

    There are two broker seams in SONAR and only one of them is guarded. The
    portfolio seam — ``execute(symbol, direction, units, price)`` — is what the
    Book tab calls and where the Alpaca paper adapter sits; it sends market
    orders and applies no caps, no confirmation and no audit. That is fine for
    paper and unacceptable for anything else. This class exists so the portfolio
    seam can be satisfied without a second, unguarded route to a venue existing.

    Confirmation is a constructor argument, and its default is refusal
    -----------------------------------------------------------------
    ``confirm`` is called with the *unconfirmed* intent and must return true for
    the order to go. With no confirmer every order is refused, the same way an
    empty allowlist permits nothing: a UI that forgets to wire the dialog gets a
    broker that cannot trade rather than one that trades unattended.

    Rejections raise, deliberately
    ------------------------------
    ``Portfolio.enter`` and ``Portfolio.close`` ignore what ``execute`` returns
    and update the local book regardless. So a refusal reported as
    ``{"error": ...}`` would leave the book recording a position that was never
    sent — manufacturing exactly the local-vs-venue divergence that
    :meth:`Guard.reconcile` exists to catch. Raising aborts before either method
    mutates anything.
    """

    def __init__(self, guard: "Guard", confirm=None, source: str = "book") -> None:
        self.guard = guard
        self._confirm = confirm
        self.source = source
        venue = guard.broker.describe()
        self.name = f"guarded:{venue.get('venue', 'unknown')}"
        self.live = str(venue.get("kind", "")).upper() == "LIVE"

    def confirmation_text(self, intent: OrderIntent) -> str:
        """The exact text a human approves. Live must not look like paper."""
        v = self.guard.broker.describe()
        banner = "*** REAL MONEY ***" if self.live else f"[{v.get('kind', '?')}]"
        return f"{banner}  {v.get('venue', '?')}\n{intent.describe()}"

    def execute(self, symbol: str, direction: str, units: float,
                price: float) -> dict:
        intent = OrderIntent(
            symbol=symbol, side=side_for_direction(direction),
            quantity=float(units), limit_price=float(price),
            source=self.source, note=direction.upper())

        if self._confirm is None:
            self.guard.audit.write("unconfirmable", intent=asdict(intent))
            raise GuardRejection(
                "no confirmation handler is attached to this broker, so nothing "
                "can approve an order. Refusing rather than sending unattended.")

        if not self._confirm(intent):
            self.guard.audit.write("declined", intent=asdict(intent))
            raise GuardRejection("declined at the confirmation prompt")

        intent.confirmed = True
        out = self.guard.submit(intent)
        return {"symbol": symbol, "direction": direction, "units": intent.quantity,
                "price": price, "at": time.time(), "broker": self.name,
                "client_order_id": out["client_order_id"], "reply": out["reply"]}


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

    def equity(self) -> float | None:
        """Account equity from the venue, or ``None`` if it cannot be read.

        ``None`` is a refusal, not a zero: callers treat it as "do not send".
        """
        try:
            eq = float(self.broker.equity())
        except Exception:
            return None
        return eq if eq > 0 else None

    def status(self) -> dict:
        return {
            "venue": self.broker.describe(),
            "equity": self.equity(),
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
            pct = L.get("max_notional_pct_equity") or 0.0
            if pct > 0:
                eq = self.equity()
                if eq is None:
                    # Fail closed, as with the allowlist: an order that cannot
                    # be measured against the account is not one to send.
                    problems.append("venue equity unavailable — refusing to send "
                                    "an order that cannot be size-checked")
                elif n > eq * pct:
                    problems.append(f"notional {n:,.2f} exceeds {pct:.0%} of venue "
                                    f"equity {eq:,.2f} ({eq * pct:,.2f})")

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

    def flatten(self, prices: dict[str, float] | None = None,
                slippage: float = FLATTEN_SLIPPAGE) -> dict:
        """Close every open position. The other half of the kill switch.

        **Exempt from the halt latch and every cap**, deliberately. Each limit in
        :meth:`check` exists to stop you *taking on* exposure, and none of them
        should be able to stop you shedding it. A daily cap you have hit, or a
        halt you have just triggered, would otherwise leave you holding a
        position with no way to close it from here — which is how a kill switch
        becomes the thing you need rescuing from.

        Idempotency is the one rule that still applies, and it matters more here
        than anywhere: a duplicate closing order does not flatten twice, it opens
        the opposite position. The nonce is derived from the position itself, so
        flattening the same holding twice is refused while a genuinely changed
        holding (a partial fill landed) is allowed through.

        Prices come from ``prices`` if given, else from whatever mark the venue
        reports. A position with no usable price is **reported, not guessed at** —
        pricing a closing order off a stale number is worse than telling you to
        close it at the venue by hand.
        """
        self.audit.write("flatten_requested")
        results: list[dict] = []

        for pos in self.broker.positions():
            symbol = str(pos.get("symbol") or "")
            qty = _f(pos.get("quantity", pos.get("qty")))
            if not symbol or abs(qty) <= POSITION_EPSILON:
                continue

            side = "SELL" if qty > 0 else "BUY"
            mark = _f((prices or {}).get(symbol)) or _f(pos.get("price")) \
                or _f(pos.get("avg_price"))
            if mark <= 0:
                results.append({"symbol": symbol, "quantity": qty,
                                "error": "no usable price — close this position at "
                                         "the venue by hand"})
                self.audit.write("flatten_unpriced", symbol=symbol, quantity=qty)
                continue

            # Price *through* the mark so the order is marketable in the
            # direction that closes: below it to sell, above it to buy.
            edge = (1.0 - slippage) if side == "SELL" else (1.0 + slippage)
            intent = OrderIntent(
                symbol=symbol, side=side, quantity=abs(qty),
                limit_price=round(mark * edge, 8),
                reference_price=mark,     # cost is measured against the mark,
                source="flatten",         # not the offset we chose to cross by
                note="kill switch", confirmed=True,
                nonce=f"flat-{symbol}-{abs(qty):.10g}")

            coid = intent.client_order_id
            if coid in self._sent or self.audit.seen_client_id(coid):
                results.append({"symbol": symbol,
                                "skipped": "already sent (idempotency)"})
                continue

            self._sent.add(coid)
            self.audit.write("submitted", client_order_id=coid, intent=asdict(intent),
                             describe=intent.describe(), exempt="flatten")
            try:
                reply = self.broker.place(
                    coid=coid, symbol=symbol.upper(), side=side,
                    quantity=abs(qty), limit_price=intent.limit_price)
                results.append({"symbol": symbol, "client_order_id": coid,
                                "reply": reply})
            except Exception as exc:
                # Keep going. The remaining positions still need closing, and
                # stopping here would strand them.
                self.audit.write("submit_error", client_order_id=coid, error=str(exc),
                                 note="OUTCOME UNKNOWN during flatten — reconcile "
                                      "at the venue, do not resend")
                results.append({"symbol": symbol, "error": str(exc)})

        self.audit.write("flatten_done", results=results)
        return {"flattened": results}

    def panic(self, prices: dict[str, float] | None = None) -> dict:
        """Kill switch: cancel working orders, flatten, then latch closed.

        In that order. Cancelling first stops a resting order filling into the
        position you are in the middle of closing, and halting last keeps the
        latch out of :meth:`flatten`'s way even though flatten ignores it.
        """
        self.audit.write("panic_requested")
        cancelled = []
        for o in self.broker.working_orders():
            try:
                cancelled.append(self.broker.cancel(o["order_id"]))
            except Exception as exc:
                cancelled.append({"order_id": o.get("order_id"), "error": str(exc)})

        flat = self.flatten(prices)
        self.halt("kill switch engaged")
        self.audit.write("panic_done", cancelled=cancelled, flattened=flat["flattened"])
        return {"cancelled": cancelled, "flattened": flat["flattened"]}

    # -- settlement: what the order actually cost --------------------------- #
    @staticmethod
    def _economics(coid: str, intent: dict, st: dict) -> dict:
        """Turn a terminal order into the numbers that decide whether to continue.

        Slippage is signed so that **positive always means worse**: paying above
        the benchmark to buy, or receiving below it to sell. Price improvement
        comes out negative, which happens often enough with marketable limits
        that scoring it as a cost would flatter nothing and confuse everything.
        """
        side = str(intent.get("side", "")).upper()
        qty = _f(st.get("filled", st.get("filled_qty")))
        fill = _f(st.get("avg_price", st.get("filled_avg_price")))
        fee = _f(st.get("fee", st.get("commission")))
        ref = _f(intent.get("reference_price")) or _f(intent.get("limit_price"))

        sign = 1.0 if side == "BUY" else -1.0
        slippage = (fill - ref) * sign * qty if (fill > 0 and ref > 0) else 0.0
        notional = fill * qty
        cost = slippage + fee
        return {
            "client_order_id": coid, "symbol": intent.get("symbol", ""),
            "side": side, "status": str(st.get("status", "")).lower(),
            "quantity": qty, "benchmark": ref, "fill_price": fill,
            "fee": round(fee, 6), "slippage": round(slippage, 6),
            "cost": round(cost, 6), "notional": round(notional, 6),
            "cost_bps": round(cost / notional * 10_000, 3) if notional else 0.0,
        }

    def settle(self) -> dict:
        """Poll every unsettled order to a terminal state and record what it cost.

        Paper needs none of this: ``PaperBroker`` fills instantly at the quoted
        price, so intent and outcome are the same object. A real order is
        *accepted* first and filled later, partially, or never — and the fill
        price is the only place the cost of trading actually appears. Without
        this the book records intentions and calls them holdings.

        Safe to call repeatedly. An order already settled is skipped, and one
        still working is reported as pending rather than guessed at.
        """
        intents: dict[str, dict] = {}
        settled: set[str] = set()
        for r in self.audit.records():
            ev, coid = r.get("event"), r.get("client_order_id")
            if not coid:
                continue
            if ev == "submitted":
                intents[coid] = r.get("intent") or {}
            elif ev == "settled":
                settled.add(coid)

        done, pending, errors = [], [], []
        for coid, intent in intents.items():
            if coid in settled:
                continue
            try:
                st = self.broker.order_status(coid)
            except Exception as exc:
                errors.append({"client_order_id": coid, "error": str(exc)})
                continue
            status = str(st.get("status", "")).lower()
            if status not in TERMINAL_STATUSES:
                pending.append({"client_order_id": coid, "status": status})
                continue
            rec = self._economics(coid, intent, st)
            self.audit.write("settled", **rec)
            done.append(rec)

        return {"settled": done, "pending": pending, "errors": errors}

    def reconcile(self, expected: dict[str, float] | None = None) -> dict:
        """Venue state is the truth. Call after any uncertain outcome, and at
        startup before anything else runs.

        Pass ``expected`` — ``{symbol: signed quantity}`` as this process
        believes it stands — and any disagreement **halts the guard**. Local
        state and venue state drift for ordinary reasons: an order filled after
        the app closed, or you traded by hand in the broker's own app. Trading
        on top of a wrong picture is how a small discrepancy compounds, so the
        resolution is deliberately manual.
        """
        orders = self.broker.working_orders()
        positions = self.broker.positions()
        actual = {str(p.get("symbol") or ""): _f(p.get("quantity", p.get("qty")))
                  for p in positions}
        out = {"orders": orders, "positions": positions, "venue": actual}

        if expected is not None:
            diverged = {}
            for sym in set(expected) | set(actual):
                want, have = _f(expected.get(sym)), _f(actual.get(sym))
                if abs(want - have) > POSITION_EPSILON:
                    diverged[sym] = {"expected": want, "venue": have}
            out["divergence"] = diverged
            if diverged:
                self.halt("local state disagrees with the venue on "
                          + ", ".join(sorted(diverged)) + " — resolve by hand")

        self.audit.write("reconciled", n_orders=len(orders),
                         n_positions=len(positions),
                         divergence=out.get("divergence"))
        return out
