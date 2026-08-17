"""Tests for the execution guard.

Every rule the guard claims to enforce gets a test that proves it, and the
dangerous paths — double-submission, unknown outcomes, the kill switch — get
tests that prove the *failure* mode is the safe one.
"""

import json

import pytest

from sonar.execution import (DEFAULT_LIMITS, AuditLog, ExecutionError, Guard,
                             GuardRejection, OrderIntent, SimBroker)

ALLOW = ("AAPL", "MSFT")


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl")


@pytest.fixture
def guard(audit):
    return Guard(broker=SimBroker(), allowlist=ALLOW, audit=audit)


def intent(**kw):
    base = dict(symbol="AAPL", side="BUY", quantity=1, limit_price=100.0,
                confirmed=True)
    base.update(kw)
    return OrderIntent(**base)


# --- the happy path exists, so the rejections below mean something --------- #
def test_confirmed_order_within_limits_is_sent(guard):
    out = guard.submit(intent())
    assert out["reply"]["status"] == "Filled"
    assert out["client_order_id"].startswith("sonar-")
    assert len(guard.broker.positions()) == 1


# --- confirmation ---------------------------------------------------------- #
def test_unconfirmed_intent_is_refused(guard):
    with pytest.raises(GuardRejection, match="not confirmed"):
        guard.submit(intent(confirmed=False))
    assert guard.broker.orders == []


def test_check_does_not_send_anything(guard):
    guard.check(intent())
    assert guard.broker.orders == []


# --- allowlist fails closed ------------------------------------------------ #
def test_symbol_off_allowlist_is_refused(guard):
    with pytest.raises(GuardRejection, match="allowlist"):
        guard.submit(intent(symbol="GME"))


def test_empty_allowlist_permits_nothing(audit):
    g = Guard(broker=SimBroker(), allowlist=(), audit=audit)
    with pytest.raises(GuardRejection, match="allowlist"):
        g.submit(intent())


# --- caps ------------------------------------------------------------------ #
def test_notional_cap(guard):
    over = DEFAULT_LIMITS["max_order_notional"] + 1
    with pytest.raises(GuardRejection, match="exceeds per-order cap"):
        guard.submit(intent(quantity=1, limit_price=over))


def test_quantity_cap(guard):
    with pytest.raises(GuardRejection, match="exceeds cap"):
        guard.submit(intent(quantity=DEFAULT_LIMITS["max_quantity"] + 1,
                            limit_price=1.0))


def test_unpriced_order_is_refused(guard):
    with pytest.raises(GuardRejection, match="no notional to cap"):
        guard.submit(intent(limit_price=None))


def test_negative_quantity_is_refused(guard):
    with pytest.raises(GuardRejection, match="positive"):
        guard.submit(intent(quantity=-5))


def test_bad_side_is_refused(guard):
    with pytest.raises(GuardRejection, match="bad side"):
        guard.submit(intent(side="LONG"))


def test_daily_order_cap(audit):
    g = Guard(broker=SimBroker(), allowlist=ALLOW, audit=audit,
              limits={"max_orders_per_day": 2, "max_open_positions": 99})
    g.submit(intent())
    g.submit(intent(symbol="MSFT"))
    with pytest.raises(GuardRejection, match="daily order cap"):
        g.submit(intent(quantity=2))


def test_open_position_cap(audit):
    g = Guard(broker=SimBroker(), allowlist=ALLOW, audit=audit,
              limits={"max_open_positions": 1})
    g.submit(intent())
    with pytest.raises(GuardRejection, match="max open positions"):
        g.submit(intent(symbol="MSFT"))


# --- idempotency: the one that actually costs money ------------------------ #
def test_same_intent_cannot_be_submitted_twice(guard):
    i = intent()
    guard.submit(i)
    with pytest.raises(GuardRejection, match="idempotency"):
        guard.submit(i)
    assert len(guard.broker.orders) == 1


def test_two_distinct_intents_for_the_same_trade_both_go_through(guard):
    """Different orders for the same thing must still be possible."""
    guard.submit(intent())
    guard.submit(intent())          # new object -> new nonce -> new coid
    assert len(guard.broker.orders) == 2


def test_idempotency_survives_a_new_guard_via_the_audit_log(audit):
    i = intent()
    Guard(broker=SimBroker(), allowlist=ALLOW, audit=audit).submit(i)
    fresh = Guard(broker=SimBroker(), allowlist=ALLOW, audit=audit)
    with pytest.raises(GuardRejection, match="idempotency"):
        fresh.submit(i)


def test_client_order_id_is_stable_for_one_intent():
    i = intent()
    assert i.client_order_id == i.client_order_id


# --- unknown outcomes fail closed ------------------------------------------ #
def test_transport_failure_halts_the_guard(audit):
    g = Guard(broker=SimBroker(fail=True), allowlist=ALLOW, audit=audit)
    with pytest.raises(ExecutionError):
        g.submit(intent())
    assert g.halted
    assert "unknown outcome" in g.halt_reason


def test_after_a_failure_nothing_else_submits(audit):
    g = Guard(broker=SimBroker(fail=True), allowlist=ALLOW, audit=audit)
    with pytest.raises(ExecutionError):
        g.submit(intent())
    with pytest.raises(GuardRejection, match="halted"):
        g.submit(intent(symbol="MSFT"))


def test_failed_intent_is_never_resent(audit):
    """The coid is burned before the send, so a retry cannot duplicate it."""
    g = Guard(broker=SimBroker(fail=True), allowlist=ALLOW, audit=audit)
    i = intent()
    with pytest.raises(ExecutionError):
        g.submit(i)
    g.resume()
    with pytest.raises(GuardRejection, match="idempotency"):
        g.submit(i)


# --- kill switch ----------------------------------------------------------- #
def test_panic_halts_and_blocks(guard):
    guard.panic()
    assert guard.halted
    with pytest.raises(GuardRejection, match="halted"):
        guard.submit(intent())


def test_resume_reopens(guard):
    guard.panic()
    guard.resume()
    assert not guard.halted
    guard.submit(intent())


# --- the audit trail ------------------------------------------------------- #
def test_every_decision_is_logged(guard, audit):
    guard.submit(intent())
    try:
        guard.submit(intent(symbol="GME"))
    except GuardRejection:
        pass
    events = [json.loads(l)["event"] for l in audit.path.read_text().splitlines()]
    assert "submitted" in events and "venue_reply" in events and "rejected" in events


def test_audit_log_is_append_only(guard, audit):
    guard.submit(intent())
    first = audit.path.read_text()
    guard.submit(intent(symbol="MSFT"))
    assert audit.path.read_text().startswith(first)


def test_rejected_orders_do_not_consume_the_daily_budget(guard, audit):
    try:
        guard.submit(intent(symbol="GME"))
    except GuardRejection:
        pass
    assert audit.today_count() == 0


def test_audit_survives_an_unwritable_path(tmp_path):
    """Logging must never break the flow it observes."""
    a = AuditLog(tmp_path / "nope" / "deep" / "audit.jsonl")
    a.write("x", k=1)          # creates parents
    bad = AuditLog(tmp_path)   # a directory, not a file
    bad.write("x", k=1)        # must not raise
    assert bad.today_count() == 0


# --- reconciliation -------------------------------------------------------- #
def test_reconcile_reports_venue_state(guard):
    guard.submit(intent())
    r = guard.reconcile()
    assert r["positions"] and r["positions"][0]["symbol"] == "AAPL"


# --- the human-facing description ------------------------------------------ #
def test_describe_is_unambiguous():
    d = intent(quantity=3, limit_price=99.5).describe()
    assert "BUY" in d and "3" in d and "AAPL" in d and "99.50" in d and "298.50" in d


def test_sim_broker_touches_nothing_real():
    assert SimBroker().describe()["kind"] == "paper"


# --------------------------------------------------------------------------- #
# Flattening — the half of the kill switch that actually removes exposure.
#
# The tests that matter here are the exemptions. Every one of them looks like a
# hole in the limits and is the opposite: a cap that can stop you closing a
# position is a cap that traps you in it.
# --------------------------------------------------------------------------- #
class StickyBroker(SimBroker):
    """A venue whose orders rest instead of filling.

    SimBroker fills instantly, which would let a flatten-idempotency test pass
    without testing anything: the position would already be gone on the second
    call. Here the position survives, so a second flatten has something to be
    wrong about.
    """

    def place(self, coid, symbol, side, quantity, limit_price):
        rec = {"order_id": f"rest-{len(self.orders) + 1}", "client_order_id": coid,
               "symbol": symbol, "side": side, "quantity": quantity,
               "limit_price": limit_price, "status": "accepted", "filled": 0.0}
        self.orders.append(rec)
        return rec


class NoEquityBroker(SimBroker):
    def equity(self):
        raise RuntimeError("venue unreachable")


def seed(broker, symbol="AAPL", quantity=5.0, **extra):
    """Put a position on the books without going through an order."""
    broker._positions[symbol] = {"symbol": symbol, "quantity": quantity, **extra}
    return broker


def test_flatten_closes_a_long(guard):
    guard.submit(intent(quantity=4))
    assert guard.broker.positions()
    guard.flatten()
    assert guard.broker.positions() == [], "still holding after a flatten"


def test_flatten_closes_a_short(guard):
    guard.submit(intent(side="SELL", quantity=3))
    assert guard.broker.positions()[0]["quantity"] == -3
    guard.flatten()
    assert guard.broker.positions() == []


def test_flatten_works_while_halted(guard):
    """The exemption that matters most.

    Halt then flatten: if the latch applied here, triggering the kill switch
    would be what stops you closing the position it was triggered over.
    """
    guard.submit(intent(quantity=2))
    guard.halt("something looked wrong")
    guard.flatten()
    assert guard.broker.positions() == []
    assert guard.halted, "flatten must not quietly clear the halt"


def test_flatten_ignores_the_daily_order_cap(audit):
    g = Guard(broker=SimBroker(), allowlist=ALLOW, audit=audit,
              limits={"max_orders_per_day": 1})
    g.submit(intent(quantity=2))
    with pytest.raises(GuardRejection, match="daily order cap"):
        g.submit(intent(symbol="MSFT"))
    g.flatten()
    assert g.broker.positions() == [], "the daily cap trapped the position"


def test_flatten_ignores_the_allowlist(audit):
    """You can end up holding something you would not be allowed to buy —
    the allowlist changed, or it was bought before the rule existed."""
    g = Guard(broker=seed(SimBroker(), "TSLA", 7.0, avg_price=200.0),
              allowlist=ALLOW, audit=audit)
    g.flatten()
    assert g.broker.positions() == []


def test_flatten_ignores_the_notional_cap(audit):
    g = Guard(broker=seed(SimBroker(), "AAPL", 100.0, avg_price=500.0),
              allowlist=ALLOW, audit=audit)
    g.flatten()
    assert g.broker.positions() == [], "a position larger than the cap was stranded"


def test_flatten_is_idempotent(audit):
    """A duplicate closing order does not flatten twice — it goes the other way."""
    b = seed(StickyBroker(), "AAPL", 5.0, avg_price=100.0)
    g = Guard(broker=b, allowlist=ALLOW, audit=audit)
    g.flatten()
    g.flatten()
    sent = [o for o in b.orders if o["symbol"] == "AAPL"]
    assert len(sent) == 1, f"sent {len(sent)} closing orders for one position"


def test_flatten_idempotency_survives_a_new_guard(audit):
    """The in-memory set is not the protection; the audit log is."""
    b = seed(StickyBroker(), "AAPL", 5.0, avg_price=100.0)
    Guard(broker=b, allowlist=ALLOW, audit=audit).flatten()
    Guard(broker=b, allowlist=ALLOW, audit=audit).flatten()
    assert len(b.orders) == 1


def test_a_changed_position_can_be_flattened_again(audit):
    """A partial fill landed, so the holding is genuinely different now."""
    b = seed(StickyBroker(), "AAPL", 5.0, avg_price=100.0)
    g = Guard(broker=b, allowlist=ALLOW, audit=audit)
    g.flatten()
    b._positions["AAPL"]["quantity"] = 3.0
    g.flatten()
    assert len(b.orders) == 2, "a changed position must be closeable"


def test_flatten_refuses_to_guess_a_price(audit):
    """No mark, no order. A stale guess is worse than a hand-off."""
    b = seed(SimBroker(), "AAPL", 5.0)            # no price, no avg_price
    g = Guard(broker=b, allowlist=ALLOW, audit=audit)
    out = g.flatten()
    assert b.orders == [], "priced a closing order off nothing"
    assert "no usable price" in out["flattened"][0]["error"]


def test_flatten_prices_through_the_mark_to_be_marketable(audit):
    b = seed(SimBroker(), "AAPL", 10.0, avg_price=100.0)
    g = Guard(broker=b, allowlist=ALLOW, audit=audit)
    g.flatten(slippage=0.01)
    assert b.orders[0]["side"] == "SELL"
    assert b.orders[0]["limit_price"] == pytest.approx(99.0), \
        "a sell must be priced below the mark or it may never fill"


def test_flatten_prices_a_buy_above_the_mark(audit):
    b = seed(SimBroker(), "AAPL", -10.0, avg_price=100.0)
    g = Guard(broker=b, allowlist=ALLOW, audit=audit)
    g.flatten(slippage=0.01)
    assert b.orders[0]["side"] == "BUY"
    assert b.orders[0]["limit_price"] == pytest.approx(101.0)


def test_a_supplied_price_beats_the_venue_mark(audit):
    b = seed(SimBroker(), "AAPL", 10.0, avg_price=100.0)
    g = Guard(broker=b, allowlist=ALLOW, audit=audit)
    g.flatten(prices={"AAPL": 200.0}, slippage=0.0)
    assert b.orders[0]["limit_price"] == pytest.approx(200.0)


def test_one_bad_position_does_not_strand_the_others(audit):
    b = seed(SimBroker(), "AAPL", 5.0)                      # unpriced, will fail
    seed(b, "MSFT", 5.0, avg_price=50.0)                    # fine
    g = Guard(broker=b, allowlist=ALLOW, audit=audit)
    out = g.flatten()
    closed = [r for r in out["flattened"] if "reply" in r]
    assert [r["symbol"] for r in closed] == ["MSFT"]


# --- panic: cancel, flatten, then latch ------------------------------------ #
def test_panic_leaves_you_flat(guard):
    """The headline. Before this, panic cancelled orders and left the position."""
    guard.submit(intent(quantity=3))
    assert guard.broker.positions()
    guard.panic()
    assert guard.broker.positions() == [], "panic halted but left exposure open"
    assert guard.halted


def test_panic_cancels_before_it_flattens(audit):
    """A resting order must not fill into the position being closed."""
    b = StickyBroker()
    g = Guard(broker=b, allowlist=ALLOW, audit=audit)
    g.submit(intent(quantity=2))                     # rests, does not fill
    assert b.working_orders()
    g.panic()
    assert b.working_orders() == []


# --- reconciliation against the venue -------------------------------------- #
def test_reconcile_without_an_expectation_never_halts(guard):
    guard.submit(intent())
    guard.reconcile()
    assert not guard.halted


def test_reconcile_accepts_agreement(guard):
    guard.submit(intent(quantity=4))
    r = guard.reconcile(expected={"AAPL": 4.0})
    assert r["divergence"] == {}
    assert not guard.halted


def test_reconcile_halts_when_quantities_disagree(guard):
    guard.submit(intent(quantity=4))
    r = guard.reconcile(expected={"AAPL": 1.0})
    assert r["divergence"]["AAPL"] == {"expected": 1.0, "venue": 4.0}
    assert guard.halted


def test_reconcile_catches_a_position_only_the_venue_knows_about(guard):
    """Bought by hand in the broker's own app. Local state has never heard of it."""
    guard.submit(intent(quantity=2))
    guard.reconcile(expected={})
    assert guard.halted


def test_reconcile_catches_a_position_only_local_state_believes_in(guard):
    guard.reconcile(expected={"AAPL": 5.0})
    assert guard.halted, "a phantom local position must not be trusted"


def test_reconcile_tolerates_float_dust(guard):
    guard.submit(intent(quantity=3))
    guard.reconcile(expected={"AAPL": 3.0 + 1e-15})
    assert not guard.halted


def test_a_halted_guard_still_refuses_ordinary_orders(guard):
    guard.reconcile(expected={"AAPL": 99.0})
    assert guard.halted
    with pytest.raises(GuardRejection, match="halted"):
        guard.submit(intent())


# --- the notional cap measured against venue equity ------------------------ #
def test_notional_is_capped_against_venue_equity(audit):
    g = Guard(broker=SimBroker(equity=1_000.0), allowlist=ALLOW, audit=audit)
    with pytest.raises(GuardRejection, match="of venue equity"):
        g.submit(intent(quantity=2, limit_price=100.0))       # 200 > 10% of 1,000


def test_an_order_within_the_equity_share_goes_through(audit):
    g = Guard(broker=SimBroker(equity=10_000.0), allowlist=ALLOW, audit=audit)
    g.submit(intent(quantity=2, limit_price=100.0))           # 200 < 10% of 10,000


def test_unreadable_equity_fails_closed(audit):
    """Fail closed, as with the allowlist: unmeasurable is not the same as fine."""
    g = Guard(broker=NoEquityBroker(), allowlist=ALLOW, audit=audit)
    with pytest.raises(GuardRejection, match="equity unavailable"):
        g.submit(intent())


def test_the_equity_check_can_be_switched_off(audit):
    g = Guard(broker=NoEquityBroker(), allowlist=ALLOW, audit=audit,
              limits={"max_notional_pct_equity": 0.0})
    g.submit(intent())


def test_status_reports_equity(guard):
    assert guard.status()["equity"] == 100_000.0
