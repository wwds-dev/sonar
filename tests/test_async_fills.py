"""Tests for the gap between sending an order and owning something.

The internal paper book fills instantly at the quoted price, so intent and
outcome are the same object and none of this matters. Every real venue — and
Alpaca's paper environment, which is the point of using it — *accepts* first
and fills later, partially, or never. A book that records "open" on acceptance
is recording an intention and calling it a holding.

These pin down the three things that go wrong: a fill that never comes, a fill
smaller than the order, and a fill at a worse price than the one the plan was
built on.
"""

import pytest

from sonar import portfolio
from sonar.portfolio import OPEN, PENDING, Portfolio

ASSET = {"symbol": "AAPL", "name": "Apple", "price": 100.0,
         "volatility": 0.02, "cls": "Equity", "confidence": 50}


class AsyncBroker:
    """Accepts orders and reports nothing until told to."""

    live = False
    name = "async-test"
    synchronous = False

    def __init__(self):
        self.sent = []
        self.pending_records = []

    def execute(self, symbol, direction, units, price):
        coid = f"coid-{len(self.sent)}"
        self.sent.append((symbol, direction, units, price, coid))
        return {"client_order_id": coid, "reply": {"status": "accepted"}}

    def settlements(self):
        out, self.pending_records = self.pending_records, []
        return out


@pytest.fixture
def book(tmp_path):
    return Portfolio(tmp_path / "book.json", broker=AsyncBroker())


def enter(book):
    pos, msg = book.enter(ASSET, "LONG", horizon_days=5, horizon_name="week")
    assert pos is not None, msg
    return pos


# --- acceptance is not a holding ------------------------------------------ #
def test_an_accepted_order_is_pending_not_open(book):
    pos = enter(book)
    assert pos.status == PENDING
    assert pos.pending is True
    assert pos.client_order_id == "coid-0"


def test_the_paper_book_is_never_pending(tmp_path):
    """Nothing changes for the synchronous path."""
    b = Portfolio(tmp_path / "b.json", broker=portfolio.PaperBroker())
    pos, _ = b.enter(ASSET, "LONG", horizon_days=5, horizon_name="week")
    assert pos.status == OPEN and pos.pending is False


def test_a_pending_position_is_not_marked_against_barriers(book):
    """The bug this prevents: booking a profit on something you do not own."""
    pos = enter(book)
    book.mark({"AAPL": pos.target * 1.5})       # way through the target
    assert book.closed == [], "settled a position that never filled"
    assert book.open[0].pending


def test_a_pending_position_carries_no_unrealised_pnl(book):
    enter(book)
    assert book.stats({"AAPL": 200.0})["unrealised"] == 0.0


def test_stats_report_pending_separately(book):
    enter(book)
    st = book.stats()
    assert st["n_open"] == 1 and st["n_pending"] == 1


# --- settlement rewrites the position from the venue's numbers ------------ #
def test_a_full_fill_opens_the_position(book):
    pos = enter(book)
    book.broker.pending_records = [
        {"client_order_id": pos.client_order_id, "quantity": pos.units,
         "fill_price": pos.entry, "status": "filled"}]
    book.poll_fills()
    assert book.open[0].status == OPEN
    assert book.open[0].pending is False


def test_a_partial_fill_shrinks_the_position(book):
    pos = enter(book)
    half = pos.units / 2
    book.broker.pending_records = [
        {"client_order_id": pos.client_order_id, "quantity": half,
         "fill_price": pos.entry, "status": "filled"}]
    book.poll_fills()
    assert book.open[0].units == pytest.approx(half), \
        "the book kept the size it asked for rather than the size it got"


def test_a_worse_fill_becomes_the_entry(book):
    pos = enter(book)
    worse = pos.entry * 1.01
    book.broker.pending_records = [
        {"client_order_id": pos.client_order_id, "quantity": pos.units,
         "fill_price": worse, "status": "filled"}]
    book.poll_fills()
    assert book.open[0].entry == pytest.approx(worse)


def test_the_target_and_stop_survive_a_worse_fill(book):
    """Slippage must eat the reward, not move the goalposts.

    Re-deriving the barriers from the new entry would restore the planned R:R
    on paper and hide the cost — which is the one thing the fill price is for.
    """
    pos = enter(book)
    target, stop = pos.target, pos.stop
    book.broker.pending_records = [
        {"client_order_id": pos.client_order_id, "quantity": pos.units,
         "fill_price": pos.entry * 1.01, "status": "filled"}]
    book.poll_fills()
    assert book.open[0].target == target and book.open[0].stop == stop


def test_a_rejected_order_leaves_no_position(book):
    pos = enter(book)
    book.broker.pending_records = [
        {"client_order_id": pos.client_order_id, "quantity": 0.0,
         "fill_price": 0.0, "status": "rejected"}]
    book.poll_fills()
    assert book.open == [], "a rejected order left a position behind"


def test_a_rejected_order_refunds_the_reserved_cash(book):
    before = book.cash
    pos = enter(book)
    assert book.cash < before, "cash was not reserved on acceptance"
    book.broker.pending_records = [
        {"client_order_id": pos.client_order_id, "quantity": 0.0,
         "fill_price": 0.0, "status": "rejected"}]
    book.poll_fills()
    assert book.cash == pytest.approx(before), "cash stayed committed to nothing"


def test_cash_reflects_what_the_fill_actually_cost(book):
    before = book.cash
    pos = enter(book)
    worse = pos.entry * 1.10
    book.broker.pending_records = [
        {"client_order_id": pos.client_order_id, "quantity": pos.units,
         "fill_price": worse, "status": "filled"}]
    book.poll_fills()
    assert book.cash == pytest.approx(before - pos.units * worse)


def test_cash_at_risk_is_recomputed_from_the_real_fill(book):
    pos = enter(book)
    half, worse = pos.units / 2, pos.entry * 1.01
    book.broker.pending_records = [
        {"client_order_id": pos.client_order_id, "quantity": half,
         "fill_price": worse, "status": "filled"}]
    book.poll_fills()
    p = book.open[0]
    assert p.cash_at_risk == pytest.approx(round(half * abs(worse - p.stop), 2))


# --- the poller itself ---------------------------------------------------- #
def test_polling_with_nothing_pending_does_nothing(book):
    assert book.poll_fills() == []


def test_a_broker_with_no_settlements_is_not_an_error(tmp_path):
    """The internal paper book has no settlements() at all."""
    b = Portfolio(tmp_path / "b.json", broker=portfolio.PaperBroker())
    b.enter(ASSET, "LONG", horizon_days=5, horizon_name="week")
    assert b.poll_fills() == []


def test_an_unreachable_venue_does_not_break_the_loop(book):
    enter(book)
    book.broker.settlements = lambda: (_ for _ in ()).throw(OSError("down"))
    assert book.poll_fills() == []          # called from the poll loop; must not raise


def test_settlement_survives_a_reload(book, tmp_path):
    """PENDING has to round-trip through the state file."""
    enter(book)
    reloaded = Portfolio(tmp_path / "book.json", broker=AsyncBroker())
    assert reloaded.open[0].status == PENDING
    assert reloaded.open[0].client_order_id == "coid-0"
