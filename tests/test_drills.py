"""Full-stack drills: the book, the guard and a venue, together.

The unit tests in test_execution.py exercise the guard against a simulator it
owns. These run the whole path — Portfolio -> GuardedBroker -> Guard -> venue —
and rehearse the two situations you would want to have practised *before* real
money is involved, rather than discovering them during one.

Both are listed in TODO.md as drills for exactly that reason.
"""

import pytest

from sonar import execution
from sonar.execution import Guard, GuardedBroker, SimBroker
from sonar.portfolio import Portfolio

ASSET = {"symbol": "AAPL", "name": "Apple", "price": 100.0,
         "volatility": 0.02, "cls": "Equity", "confidence": 50}

# The caps are not what these drills test, and the defaults would reject a
# normally-sized position before the drill began.
WIDE = {"max_order_notional": 1e9, "max_orders_per_day": 10_000,
        "max_open_positions": 100, "max_quantity": 1e9,
        "max_notional_pct_equity": 0.0}


@pytest.fixture
def stack(tmp_path):
    venue = SimBroker()
    guard = Guard(broker=venue, allowlist=("AAPL", "MSFT"),
                  limits=WIDE, audit=execution.AuditLog(tmp_path / "audit.jsonl"))
    book = Portfolio(tmp_path / "book.json",
                     broker=GuardedBroker(guard, confirm=lambda _i: True))
    return venue, guard, book


def open_one(book, symbol="AAPL"):
    asset = {**ASSET, "symbol": symbol}
    pos, msg = book.enter(asset, "LONG", horizon_days=5, horizon_name="week")
    assert pos is not None, msg
    return pos


def local_view(book) -> dict:
    """What the book believes it holds, in the shape reconcile() expects."""
    view: dict[str, float] = {}
    for p in book.open:
        view[p.symbol] = view.get(p.symbol, 0.0) + (
            p.units if p.direction == "LONG" else -p.units)
    return view


# --- drill 1: the venue moves behind SONAR's back ------------------------- #
def test_reconciliation_drill_detects_a_position_appearing_at_the_venue(stack):
    """Someone traded in the broker's own app. SONAR has never heard of it."""
    venue, guard, book = stack
    open_one(book)
    venue._positions["MSFT"] = {"symbol": "MSFT", "quantity": 40.0,
                                "avg_price": 300.0}

    out = guard.reconcile(expected=local_view(book))

    assert "MSFT" in out["divergence"]
    assert guard.halted, "kept trading on a picture it knew was wrong"


def test_reconciliation_drill_detects_a_position_vanishing(stack):
    """Closed by hand at the venue, still open in the book."""
    venue, guard, book = stack
    pos = open_one(book)
    venue._positions.pop(pos.symbol)

    out = guard.reconcile(expected=local_view(book))
    assert pos.symbol in out["divergence"]
    assert guard.halted


def test_reconciliation_drill_detects_a_changed_size(stack):
    """Half sold elsewhere — the subtlest of the three, and the easiest to miss."""
    venue, guard, book = stack
    pos = open_one(book)
    venue._positions[pos.symbol]["quantity"] /= 2

    assert pos.symbol in guard.reconcile(expected=local_view(book))["divergence"]
    assert guard.halted


def test_reconciliation_drill_is_quiet_when_the_two_agree(stack):
    """The control. A drill that always fires proves nothing."""
    _venue, guard, book = stack
    open_one(book)
    out = guard.reconcile(expected=local_view(book))
    assert out["divergence"] == {}
    assert not guard.halted


def test_a_halted_guard_refuses_the_next_order(stack):
    """Halting has to actually stop trading, not just log a complaint."""
    venue, guard, book = stack
    open_one(book)
    venue._positions["MSFT"] = {"symbol": "MSFT", "quantity": 1.0,
                                "avg_price": 1.0}
    guard.reconcile(expected=local_view(book))

    with pytest.raises(execution.GuardRejection, match="halted"):
        book.enter({**ASSET, "symbol": "MSFT"}, "LONG",
                   horizon_days=5, horizon_name="week")


# --- drill 2: the kill switch ---------------------------------------------- #
def test_kill_switch_drill_leaves_the_venue_flat(stack):
    """Flat at the venue, checked at the venue — not in the audit log.

    A kill switch verified by reading its own log is a kill switch that has
    never been tested.
    """
    venue, guard, book = stack
    open_one(book, "AAPL")
    open_one(book, "MSFT")
    assert len(venue.positions()) == 2

    guard.panic()

    assert venue.positions() == [], "still holding after the kill switch"
    assert guard.halted


def test_kill_switch_drill_works_from_an_already_halted_guard(stack):
    """The realistic case: something went wrong, it halted, *then* you flatten."""
    venue, guard, book = stack
    open_one(book)
    guard.halt("something looked wrong")

    guard.flatten()
    assert venue.positions() == [], "the halt trapped the position it was raised over"


def test_kill_switch_drill_after_the_daily_cap_is_exhausted(tmp_path):
    """A cap you have hit must not be a cap that traps you."""
    venue = SimBroker()
    guard = Guard(broker=venue, allowlist=("AAPL",), audit=execution.AuditLog(
        tmp_path / "a.jsonl"), limits={**WIDE, "max_orders_per_day": 1})
    book = Portfolio(tmp_path / "b.json",
                     broker=GuardedBroker(guard, confirm=lambda _i: True))
    open_one(book)
    assert venue.positions()

    guard.flatten()
    assert venue.positions() == []
