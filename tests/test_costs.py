"""Tests for settlement and the cost ledger.

The point of both is to produce one number — what a round trip costs — that
decides whether trading this system is worth doing at all. So the tests here
care most about the ways that number could be flattering: slippage measured
against the wrong benchmark, a still-working order settled early, an open
position counted as a completed round trip, or a sample too small to mean
anything reported as though it meant something.
"""

import pytest

from sonar import costs
from sonar.execution import (TERMINAL_STATUSES, AuditLog, Guard, OrderIntent,
                             SimBroker)

ALLOW = ("AAPL", "MSFT")


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl")


# The caps are not what is under test here, and the default 500 notional would
# reject the round numbers that make the cost arithmetic checkable by eye.
WIDE = {"max_order_notional": 1e9, "max_orders_per_day": 10_000,
        "max_open_positions": 100}


def mkguard(broker, audit, **limits):
    return Guard(broker=broker, allowlist=ALLOW, audit=audit,
                 limits={**WIDE, **limits})


@pytest.fixture
def guard(audit):
    return mkguard(SimBroker(), audit)


def order(g, side="BUY", qty=1.0, price=100.0, **kw):
    return g.submit(OrderIntent(symbol=kw.pop("symbol", "AAPL"), side=side,
                                quantity=qty, limit_price=price,
                                confirmed=True, **kw))


class SlippingBroker(SimBroker):
    """Fills away from the limit, the way a real venue does."""

    def __init__(self, slip: float = 0.0, **kw) -> None:
        super().__init__(**kw)
        self.slip = slip

    def place(self, coid, symbol, side, quantity, limit_price):
        rec = super().place(coid, symbol, side, quantity, limit_price)
        fill = limit_price * (1 + self.slip if side == "BUY" else 1 - self.slip)
        rec["avg_price"] = fill
        rec["fee"] = round(quantity * fill * self.fee_rate, 6)
        self._positions[symbol]["avg_price"] = fill
        return rec


class WorkingBroker(SimBroker):
    """Accepts orders and leaves them working — the normal live case."""

    def place(self, coid, symbol, side, quantity, limit_price):
        rec = {"order_id": f"w-{len(self.orders) + 1}", "client_order_id": coid,
               "symbol": symbol, "side": side, "quantity": quantity,
               "limit_price": limit_price, "status": "accepted", "filled": 0.0}
        self.orders.append(rec)
        return rec


# --- settlement ------------------------------------------------------------ #
def test_a_filled_order_settles(guard):
    order(guard)
    out = guard.settle()
    assert len(out["settled"]) == 1
    assert out["settled"][0]["status"] == "filled"


def test_a_working_order_is_pending_not_settled(audit):
    g = mkguard(WorkingBroker(), audit)
    order(g)
    out = g.settle()
    assert out["settled"] == []
    assert out["pending"][0]["status"] == "accepted"


def test_an_unknown_status_is_treated_as_still_working(audit):
    """Settling early records a fill quantity that can still change."""
    class Odd(SimBroker):
        def order_status(self, coid):
            return {"client_order_id": coid, "status": "some_new_venue_state"}

    g = mkguard(Odd(), audit)
    order(g)
    assert g.settle()["settled"] == []


def test_settling_twice_records_once(guard):
    order(guard)
    guard.settle()
    assert guard.settle()["settled"] == []
    assert len(costs.orders(guard.audit)) == 1


def test_settlement_survives_a_new_guard(audit):
    """The audit log is the state, not anything held in memory."""
    b = SimBroker()
    g1 = mkguard(b, audit)
    order(g1)
    g1.settle()
    g2 = mkguard(b, audit)
    assert g2.settle()["settled"] == []


def test_a_venue_error_does_not_stop_the_others(audit):
    class Flaky(SimBroker):
        def order_status(self, coid):
            if coid.endswith("zzz"):
                raise RuntimeError("timeout")
            return super().order_status(coid)

    g = mkguard(Flaky(), audit)
    order(g)
    order(g, symbol="MSFT")
    assert len(g.settle()["settled"]) == 2


def test_every_terminal_status_is_lowercase():
    """Matching is case-insensitive, so the set must be too or it never hits."""
    assert all(s == s.lower() for s in TERMINAL_STATUSES)


# --- the economics --------------------------------------------------------- #
def test_paying_above_the_benchmark_to_buy_is_a_cost(audit):
    g = mkguard(SlippingBroker(slip=0.01), audit)
    order(g, side="BUY", qty=10, price=100.0)
    rec = g.settle()["settled"][0]
    assert rec["fill_price"] == pytest.approx(101.0)
    assert rec["slippage"] == pytest.approx(10.0), "10 units x 1.00 worse"


def test_receiving_below_the_benchmark_to_sell_is_also_a_cost(audit):
    g = mkguard(SlippingBroker(slip=0.01), audit)
    order(g, side="SELL", qty=10, price=100.0)
    rec = g.settle()["settled"][0]
    assert rec["fill_price"] == pytest.approx(99.0)
    assert rec["slippage"] == pytest.approx(10.0), "a sign error would net to zero"


def test_price_improvement_is_negative_not_a_cost(audit):
    g = mkguard(SlippingBroker(slip=-0.01), audit)
    order(g, side="BUY", qty=10, price=100.0)
    assert g.settle()["settled"][0]["slippage"] == pytest.approx(-10.0)


def test_fees_are_counted_on_top_of_slippage(audit):
    g = mkguard(SlippingBroker(slip=0.01, fee_rate=0.002), audit)
    order(g, side="BUY", qty=10, price=100.0)
    rec = g.settle()["settled"][0]
    assert rec["fee"] == pytest.approx(2.02)          # 0.2% of 10 x 101
    assert rec["cost"] == pytest.approx(12.02)        # slippage + fee


def test_slippage_is_measured_against_the_reference_not_the_limit(guard):
    """A marketable limit is priced through the book on purpose.

    Scoring that deliberate offset as slippage would invent a cost on every
    closing order — and, on the other side, report free money.
    """
    guard.submit(OrderIntent(symbol="AAPL", side="SELL", quantity=10,
                             limit_price=99.0,        # crossed to be marketable
                             reference_price=100.0,   # the actual mark
                             confirmed=True))
    rec = guard.settle()["settled"][0]
    assert rec["benchmark"] == 100.0
    assert rec["slippage"] == pytest.approx(10.0), \
        "measured against the limit this would have read as zero"


def test_the_benchmark_falls_back_to_the_limit():
    assert OrderIntent(symbol="A", side="BUY", quantity=1,
                       limit_price=50.0).benchmark == 50.0
    assert OrderIntent(symbol="A", side="BUY", quantity=1, limit_price=50.0,
                       reference_price=52.0).benchmark == 52.0


# --- round trips ----------------------------------------------------------- #
def _round_trip(g, symbol="AAPL", qty=10.0, price=100.0):
    order(g, side="BUY", qty=qty, price=price, symbol=symbol)
    order(g, side="SELL", qty=qty, price=price, symbol=symbol)
    g.settle()


def test_a_completed_round_trip_is_counted(audit):
    g = mkguard(SlippingBroker(slip=0.01), audit)
    _round_trip(g)
    rt = costs.round_trips(audit)
    assert len(rt) == 1
    assert rt[0]["n_orders"] == 2
    assert rt[0]["cost"] == pytest.approx(20.0)       # both sides slipped


def test_an_open_position_is_not_a_round_trip(audit):
    g = mkguard(SlippingBroker(slip=0.01), audit)
    order(g, side="BUY", qty=10)
    g.settle()
    assert costs.round_trips(audit) == [], "an entry alone has no known cost"


def test_a_position_closed_in_pieces_is_one_round_trip(audit):
    g = mkguard(SlippingBroker(slip=0.01), audit)
    order(g, side="BUY", qty=10)
    order(g, side="SELL", qty=4)
    order(g, side="SELL", qty=6)
    g.settle()
    rt = costs.round_trips(audit)
    assert len(rt) == 1 and rt[0]["n_orders"] == 3


def test_symbols_do_not_bleed_into_each_other(audit):
    g = mkguard(SlippingBroker(slip=0.01), audit)
    order(g, side="BUY", qty=10, symbol="AAPL")
    order(g, side="SELL", qty=10, symbol="MSFT")     # a short, not a close
    g.settle()
    assert costs.round_trips(audit) == []


def test_two_round_trips_in_one_symbol(audit):
    g = mkguard(SlippingBroker(slip=0.01), audit)
    _round_trip(g)
    _round_trip(g, qty=11.0)
    assert len(costs.round_trips(audit)) == 2


# --- the summary, and its refusal to overclaim ----------------------------- #
def test_summary_declines_below_the_threshold(audit):
    g = mkguard(SlippingBroker(slip=0.01), audit)
    _round_trip(g)
    s = costs.summary(audit)
    assert s["n_round_trips"] == 1
    assert s["reliable"] is False
    assert "too few" in s["verdict"]


def test_summary_reports_once_there_is_a_sample(audit):
    g = mkguard(SlippingBroker(slip=0.01), audit)
    for i in range(costs.MIN_ROUND_TRIPS):
        _round_trip(g, qty=10.0 + i)                 # distinct, so ids differ
    s = costs.summary(audit)
    assert s["n_round_trips"] == costs.MIN_ROUND_TRIPS
    assert s["reliable"] is True
    assert s["cost_per_round_trip"] > 0
    assert "per round trip" in s["verdict"]


def test_summary_on_an_empty_log(audit):
    s = costs.summary(audit)
    assert s["n_round_trips"] == 0
    assert s["cost_per_round_trip"] is None
    assert "no completed round trips" in s["verdict"]


def test_a_free_venue_reports_zero_cost(guard):
    """SimBroker fills at the limit with no fee, and must not invent a cost."""
    _round_trip(guard)
    assert costs.summary(guard.audit)["total_cost"] == pytest.approx(0.0)
