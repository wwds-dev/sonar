"""What trading actually costs, measured rather than assumed.

SONAR's own arithmetic says its expected value is zero before costs. The model
is a driftless random walk with a 1.5:1 target, so ``P(profit) = 1/(1+R:R) =
0.40`` and ``0.40 x 1.5 - 0.60 x 1.0 = 0`` exactly; five pre-registered studies
failed to find drift to add to it. Net of costs the expectation is therefore
``-c`` per trade, where ``c`` is what a round trip costs.

Which makes ``c`` the number that decides everything, and the one number in the
whole app that can be measured directly rather than estimated. This module
measures it.

Where the data comes from
-------------------------
Entirely from the execution audit log. :meth:`sonar.execution.Guard.settle`
writes a ``settled`` record per terminal order carrying the benchmark price, the
actual fill, the fee and the derived slippage; everything here is a read over
those records. There is deliberately no second store: a cost ledger that could
disagree with the audit log would raise the question of which one lied.

Slippage sign convention: **positive is worse**. Paying above the benchmark to
buy, or receiving below it to sell. Price improvement is negative.

On sample size
--------------
:data:`MIN_ROUND_TRIPS` mirrors the discipline in :mod:`sonar.calibration`.
Below it, :func:`summary` reports ``reliable: False`` and declines to name a
figure, because a handful of round trips in one instrument during one week says
more about that week than about what trading costs you.
"""

from __future__ import annotations

from collections import defaultdict

from .execution import POSITION_EPSILON, AuditLog

# Same threshold and the same reason as calibration's: below this, the spread of
# outcomes is wider than the quantity being estimated.
MIN_ROUND_TRIPS = 20


def _log(audit: AuditLog | None) -> AuditLog:
    return audit or AuditLog()


def orders(audit: AuditLog | None = None) -> list[dict]:
    """Every settled order's economics, oldest first."""
    out = []
    for r in _log(audit).records():
        if r.get("event") != "settled":
            continue
        row = {k: v for k, v in r.items() if k not in ("event", "iso")}
        row["at"] = r.get("t")
        out.append(row)
    return out


def round_trips(audit: AuditLog | None = None) -> list[dict]:
    """Completed round trips, one per return to a flat position in a symbol.

    Walks each symbol's settled orders in time order accumulating a signed
    quantity; when it returns to zero the legs since the last flat point are one
    round trip. This handles a position closed in pieces, which is the normal
    case once partial fills exist — pairing orders one-to-one would not.

    A position still open contributes nothing: its cost is not yet known, and
    counting the entry alone would report a cost with no matching exit.
    """
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for o in orders(audit):
        by_symbol[str(o.get("symbol") or "")].append(o)

    out: list[dict] = []
    for symbol, rows in by_symbol.items():
        rows.sort(key=lambda r: r.get("at") or 0)
        position, legs = 0.0, []
        for o in rows:
            qty = float(o.get("quantity") or 0.0)
            if qty <= 0:                       # a rejection or a zero fill
                continue
            position += qty if o.get("side") == "BUY" else -qty
            legs.append(o)
            if abs(position) <= POSITION_EPSILON:
                notional = sum(float(x.get("notional") or 0.0) for x in legs)
                cost = sum(float(x.get("cost") or 0.0) for x in legs)
                out.append({
                    "symbol": symbol,
                    "n_orders": len(legs),
                    "opened": legs[0].get("at"),
                    "closed": legs[-1].get("at"),
                    "notional": round(notional, 6),
                    "fees": round(sum(float(x.get("fee") or 0.0) for x in legs), 6),
                    "slippage": round(
                        sum(float(x.get("slippage") or 0.0) for x in legs), 6),
                    "cost": round(cost, 6),
                    # Halved: a round trip crosses the spread twice on the same
                    # capital, so per-side basis points is the comparable figure.
                    "cost_bps": round(cost / (notional / 2) * 10_000, 3)
                    if notional else 0.0,
                })
                position, legs = 0.0, []
    return sorted(out, key=lambda r: r.get("closed") or 0)


def summary(audit: AuditLog | None = None) -> dict:
    """The empirical ``c``, or an honest refusal to name one yet."""
    rt = round_trips(audit)
    n = len(rt)
    total = round(sum(r["cost"] for r in rt), 6)
    reliable = n >= MIN_ROUND_TRIPS
    return {
        "n_settled_orders": len(orders(audit)),
        "n_round_trips": n,
        "min_round_trips": MIN_ROUND_TRIPS,
        "reliable": reliable,
        "total_cost": total,
        "total_fees": round(sum(r["fees"] for r in rt), 6),
        "total_slippage": round(sum(r["slippage"] for r in rt), 6),
        "cost_per_round_trip": round(total / n, 6) if n else None,
        "mean_cost_bps": round(sum(r["cost_bps"] for r in rt) / n, 3) if n else None,
        "verdict": (
            f"{n} round trips: {total / n:,.4f} per round trip"
            if reliable else
            f"{n} of {MIN_ROUND_TRIPS} round trips — too few to state a cost"
        ) if n else "no completed round trips yet",
    }
