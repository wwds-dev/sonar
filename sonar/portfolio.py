"""A paper book for any instrument, long or short.

The hourly BTC engine settles one binary bet an hour. This is the general case:
open a position in anything on the screener, with a volatility-scaled target and
stop from :mod:`sonar.scoring`, and let it resolve. Two reasons it exists:

1. **You can act on what the screener says.** A number you cannot trade against
   is a number nobody ever finds out was wrong.
2. **It manufactures ground truth.** Every closed position carries the score it
   was opened on, so :mod:`sonar.calibration` can ask the only question that
   matters — did high scores actually win more often?

Everything here is paper. Two brokers implement the ``Broker`` protocol and
both are simulations: ``PaperBroker`` fills instantly in-process, and
``AlpacaPaperBroker`` sends real orders to Alpaca's **paper** environment, which
has real market hours and real order handling but no money. No live broker
exists, and ``sonar/alpaca.py`` makes the live endpoint structurally
unreachable rather than merely discouraged.

One honest limit: positions are marked against a **polled** price, so a spike
that touches a target and reverses between two polls is not seen. Fills are also
assumed at exactly the target or stop. Both flatter the results slightly, in the
same direction real slippage would hurt them.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from . import scoring

STARTING_CASH = 10_000.0
# Fraction of the book risked per position if the stop is hit. Overridden by the
# active risk profile; this is the fallback.
DEFAULT_RISK_FRACTION = 0.01


# A position's lifecycle. PENDING exists only for brokers whose fills are
# asynchronous; see Position.status.
PENDING, OPEN = "PENDING", "OPEN"


@dataclass
class Position:
    """One paper position, carrying the belief it was opened on."""

    id: str
    symbol: str
    name: str
    direction: str                 # LONG | SHORT
    units: float
    entry: float
    target: float
    stop: float
    opened_at: float
    cash_at_risk: float
    # what the app claimed at the moment of entry — the calibration record
    confidence: float
    rr: float
    p_profit: float
    horizon: str
    asset_class: str = ""
    # PENDING until the venue reports a fill. A paper broker fills instantly so
    # nothing is ever pending there; a real one accepts first and fills later,
    # partially, or never — and a book that records "open" on acceptance is
    # recording an intention and calling it a holding.
    status: str = OPEN
    client_order_id: str = ""
    # filled on close
    closed_at: float | None = None
    exit: float | None = None
    pnl: float | None = None
    outcome: str | None = None     # TARGET | STOP | MANUAL

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def pending(self) -> bool:
        """Accepted by the venue, not yet filled. No exposure exists yet."""
        return self.status == PENDING

    def unrealised(self, price: float) -> float:
        sign = 1.0 if self.direction == "LONG" else -1.0
        return sign * (price - self.entry) * self.units

    def hit(self, price: float) -> str | None:
        """Has this price touched a barrier? Returns TARGET, STOP or None."""
        if self.direction == "LONG":
            if price >= self.target:
                return "TARGET"
            if price <= self.stop:
                return "STOP"
        else:
            if price <= self.target:
                return "TARGET"
            if price >= self.stop:
                return "STOP"
        return None


class Broker(Protocol):
    """The seam a broker sits behind.

    :class:`PaperBroker` and Alpaca's paper broker implement it. A live
    implementation would place real orders with real money and is deliberately
    not provided.
    """

    # True when execute() returns a completed fill, as the internal paper book
    # does. False means it returns an *acceptance* and the fill lands later —
    # the book then holds the position PENDING until settlements() reports it.
    synchronous: bool = True

    def execute(self, symbol: str, direction: str, units: float,
                price: float) -> dict: ...


def default_broker():
    """Alpaca's paper environment when configured, the internal book otherwise.

    Both are paper. The Alpaca path is strictly more honest — real market hours,
    real order handling, orders that sit unfilled when the market is shut —
    while the internal one fills instantly at the quoted price and so flatters
    every result. Neither can reach real money: see sonar/alpaca.py for the
    guards that make the live endpoint unreachable.
    """
    try:
        from . import alpaca
        ok, _why = alpaca.available()
        if ok:
            return alpaca.AlpacaPaperBroker()
    except Exception:
        pass                     # any problem at all falls back to the local book
    return PaperBroker()


class PaperBroker:
    """Fills instantly at the quoted price. No fees, no slippage, no queue.

    Being explicit about that matters: a real fill is worse than this on every
    axis, so paper results are an optimistic bound, never a forecast.
    """

    live = False
    name = "paper"
    synchronous = True                 # the fill *is* the return value

    def execute(self, symbol: str, direction: str, units: float,
                price: float) -> dict:
        return {"symbol": symbol, "direction": direction, "units": units,
                "price": price, "at": time.time(), "broker": self.name}


class Portfolio:
    """The paper book: cash, open positions, and everything already resolved."""

    def __init__(self, path: Path, broker: Broker | None = None,
                 starting_cash: float = STARTING_CASH) -> None:
        self.path = Path(path)
        self.broker = broker or PaperBroker()
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.open: list[Position] = []
        self.closed: list[Position] = []
        self._load()

    # -- persistence ------------------------------------------------------- #
    def _load(self) -> None:
        try:
            d = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        self.starting_cash = d.get("starting_cash", self.starting_cash)
        self.cash = d.get("cash", self.starting_cash)
        self.open = [Position(**p) for p in d.get("open", [])]
        self.closed = [Position(**p) for p in d.get("closed", [])]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"starting_cash": self.starting_cash, "cash": self.cash,
                   "open": [asdict(p) for p in self.open],
                   "closed": [asdict(p) for p in self.closed]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(self.path)

    # -- trading ----------------------------------------------------------- #
    def position_for(self, symbol: str) -> Position | None:
        return next((p for p in self.open if p.symbol == symbol), None)

    def enter(self, asset: dict, direction: str, horizon_days: int,
              horizon_name: str, risk_fraction: float = DEFAULT_RISK_FRACTION,
              ) -> tuple[Position | None, str]:
        """Open a position from a screener row. Returns ``(position, message)``.

        One position per symbol: doubling up would quietly turn a fixed risk
        budget into an unbounded one.
        """
        symbol = asset["symbol"]
        if self.position_for(symbol) is not None:
            return None, f"already holding {symbol}"
        price = float(asset.get("price") or 0.0)
        vol = float(asset.get("volatility") or 0.0)
        if price <= 0:
            return None, f"no price for {symbol}"
        if vol <= 0:
            return None, f"no volatility for {symbol} — cannot place a stop"

        plan = scoring.build_plan(price, vol, horizon_days, direction)
        units, at_risk = scoring.position_size(
            self.equity({symbol: price}), risk_fraction, plan.entry, plan.stop)
        if units <= 0:
            return None, "position would be zero-sized"
        cost = units * price
        if direction.upper() == "LONG" and cost > self.cash:
            # Scale into the cash actually available rather than refusing: the
            # risk budget, not the notional, is the thing being controlled.
            units = self.cash / price
            at_risk = units * abs(plan.entry - plan.stop)
            cost = units * price
        if units <= 0:
            return None, "not enough cash"

        reply = self.broker.execute(symbol, plan.direction, units, price) or {}
        sync = bool(getattr(self.broker, "synchronous", True))
        pos = Position(
            id=uuid.uuid4().hex[:12], symbol=symbol,
            name=asset.get("name", symbol), direction=plan.direction,
            units=units, entry=price, target=plan.target, stop=plan.stop,
            opened_at=time.time(), cash_at_risk=at_risk,
            confidence=float(asset.get("confidence") or 0.0),
            rr=plan.rr, p_profit=plan.p_profit, horizon=horizon_name,
            asset_class=asset.get("cls", ""),
            status=OPEN if sync else PENDING,
            client_order_id=str(reply.get("client_order_id") or ""))
        # A short borrows rather than spends; only a long consumes cash. A
        # pending long reserves it too: the money is committed the moment the
        # order is accepted, and settle_fills() refunds it if the order dies.
        if pos.direction == "LONG":
            self.cash -= cost
        self.open.append(pos)
        self.save()
        return pos, f"opened {pos.direction} {symbol}"

    def close(self, pos_id: str, price: float, outcome: str = "MANUAL",
              ) -> Position | None:
        pos = next((p for p in self.open if p.id == pos_id), None)
        if pos is None:
            return None
        self.broker.execute(pos.symbol,
                            "SELL" if pos.direction == "LONG" else "COVER",
                            pos.units, price)
        pos.exit = price
        pos.pnl = round(pos.unrealised(price), 2)
        pos.closed_at = time.time()
        pos.outcome = outcome
        if pos.direction == "LONG":
            self.cash += pos.units * price
        else:
            self.cash += pos.pnl
        self.open.remove(pos)
        self.closed.append(pos)
        self.save()
        return pos

    def poll_fills(self) -> list[Position]:
        """Ask the broker which accepted orders have reached a terminal state.

        The order-state poller. Brokers that fill synchronously never have
        anything pending and never implement ``settlements()``, so this is a
        no-op for the internal paper book.
        """
        if not any(p.pending for p in self.open):
            return []
        fetch = getattr(self.broker, "settlements", None)
        if fetch is None:
            return []
        try:
            records = fetch()
        except Exception:
            return []                     # a venue being unreachable is not an error here
        return self.settle_fills(records or [])

    def settle_fills(self, records: list[dict]) -> list[Position]:
        """Reconcile pending positions against what the venue actually did.

        A fill is not the order you sent. The quantity can be smaller, the
        price worse, and the whole thing can be rejected — so the position is
        rewritten from the venue's numbers rather than confirmed against its
        own.

        The target and stop are deliberately **not** re-derived from the new
        entry. They were the thesis; a worse fill eats into the reward it was
        supposed to pay, which is exactly the cost that should show up in the
        results rather than being tidied away by moving the barriers.
        """
        by_id = {str(r.get("client_order_id") or ""): r for r in records}
        changed: list[Position] = []
        for pos in list(self.open):
            if not pos.pending or pos.client_order_id not in by_id:
                continue
            rec = by_id[pos.client_order_id]
            filled = float(rec.get("quantity") or 0.0)
            price = float(rec.get("fill_price") or 0.0)

            if filled <= 0 or price <= 0:
                # Rejected, cancelled, or expired unfilled. Nothing was bought,
                # so the reservation goes back.
                if pos.direction == "LONG":
                    self.cash += pos.units * pos.entry
                self.open.remove(pos)
                changed.append(pos)
                continue

            if pos.direction == "LONG":
                # Refund what was reserved, charge what it actually cost.
                self.cash += pos.units * pos.entry
                self.cash -= filled * price
            pos.units = filled
            pos.entry = price
            pos.cash_at_risk = round(filled * abs(price - pos.stop), 2)
            pos.status = OPEN
            changed.append(pos)

        if changed:
            self.save()
        return changed

    def mark(self, prices: dict[str, float]) -> list[Position]:
        """Mark open positions and close any whose barrier was touched.

        Pending positions are skipped: an order that has not filled carries no
        exposure, so closing it on a barrier would book a profit or loss on a
        holding that does not exist.
        """
        done = []
        for pos in list(self.open):
            price = prices.get(pos.symbol)
            if price is None or pos.pending:
                continue
            reason = pos.hit(price)
            if reason:
                fill = pos.target if reason == "TARGET" else pos.stop
                closed = self.close(pos.id, fill, reason)
                if closed:
                    done.append(closed)
        return done

    # -- reporting --------------------------------------------------------- #
    def equity(self, prices: dict[str, float]) -> float:
        total = self.cash
        for pos in self.open:
            # Pending: the cash is reserved but nothing is owned, so it is
            # carried at what was committed rather than marked to market.
            price = pos.entry if pos.pending else prices.get(pos.symbol, pos.entry)
            if pos.direction == "LONG":
                total += pos.units * price
            else:
                total += pos.unrealised(price)
        return total

    def stats(self, prices: dict[str, float] | None = None) -> dict:
        prices = prices or {}
        settled = [p for p in self.closed if p.pnl is not None]
        wins = [p for p in settled if (p.pnl or 0) > 0]
        gross_win = sum(p.pnl for p in wins)
        gross_loss = -sum(p.pnl for p in settled if (p.pnl or 0) < 0)
        eq = self.equity(prices)
        return {
            "cash": round(self.cash, 2),
            "equity": round(eq, 2),
            "starting_cash": self.starting_cash,
            "total_pnl": round(eq - self.starting_cash, 2),
            "return_pct": round((eq / self.starting_cash - 1) * 100, 2),
            "n_open": len(self.open),
            "n_pending": sum(1 for p in self.open if p.pending),
            "n_closed": len(settled),
            "n_wins": len(wins),
            "win_rate": round(len(wins) / len(settled) * 100, 1) if settled else 0.0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
            "unrealised": round(sum(p.unrealised(prices.get(p.symbol, p.entry))
                                    for p in self.open if not p.pending), 2),
            "broker": getattr(self.broker, "name", "paper"),
            "live": bool(getattr(self.broker, "live", False)),
        }

    def open_rows(self, prices: dict[str, float] | None = None) -> list[dict]:
        prices = prices or {}
        rows = []
        for p in self.open:
            price = prices.get(p.symbol, p.entry)
            d = asdict(p)
            d["price"] = price
            d["unrealised"] = round(p.unrealised(price), 2)
            d["progress"] = _progress(p, price)
            rows.append(d)
        return rows


def _progress(pos: Position, price: float) -> float:
    """How far from stop (0.0) to target (1.0) price currently sits."""
    lo, hi = (pos.stop, pos.target) if pos.direction == "LONG" else (pos.target, pos.stop)
    if hi == lo:
        return 0.5
    frac = (price - lo) / (hi - lo)
    if pos.direction == "SHORT":
        frac = 1.0 - frac
    return max(0.0, min(1.0, frac))
