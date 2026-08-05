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
