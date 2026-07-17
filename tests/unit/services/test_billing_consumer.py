import json

import pytest
from nats.errors import NotJSMessageError
from sqlalchemy.exc import IntegrityError, OperationalError

from app.services import billing_consumer as billing_module


class FakeMessage:
    def __init__(self, data=b""):
        self.data = data
        self.acked = False
        self.nak_delay = None

    async def ack(self):
        self.acked = True

    async def nak(self, delay=0):
        self.nak_delay = delay


async def test_safe_ack_ignores_non_js_message():
    class NonJSMessage(FakeMessage):
        async def ack(self):
            raise NotJSMessageError()

    await billing_module._safe_ack(NonJSMessage())


async def test_safe_nak_ignores_non_js_message():
    class NonJSMessage(FakeMessage):
        async def nak(self, delay=0):
            raise NotJSMessageError()

    await billing_module._safe_nak(NonJSMessage(), delay=10)


async def test_handle_billing_deducted_acks_malformed_message(monkeypatch):
    msg = FakeMessage(b"{bad json")
    acked = {}

    async def fake_safe_ack(message):
        acked["called"] = True

    monkeypatch.setattr("app.services.billing_consumer._safe_ack", fake_safe_ack)

    await billing_module._handle_billing_deducted(msg)

    assert acked["called"] is True


async def test_handle_billing_deducted_runs_grace_logic_on_insufficient_credits(monkeypatch):
    """Insufficient credits no longer kills the VM instantly — the tick is
    routed into the grace-period handler (and still ACKed)."""
    msg = FakeMessage(
        json.dumps({"pod_id": "pod-1", "user_id": "user-1", "amount": 2.5, "tx_id": "tx-1"}).encode()
    )
    grace_called = {}
    acked = {}

    class FakeDBContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_deduct_credits(db, user_id, amount, description, tx_id):
        raise ValueError("insufficient")

    async def fake_exhausted_tick(pod_id, user_id):
        grace_called["pod_id"] = pod_id
        grace_called["user_id"] = user_id

    async def fake_safe_ack(message):
        acked["called"] = True

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.deduct_credits", fake_deduct_credits)
    monkeypatch.setattr("app.services.billing_consumer._handle_exhausted_tick", fake_exhausted_tick)
    monkeypatch.setattr("app.services.billing_consumer._safe_ack", fake_safe_ack)

    await billing_module._handle_billing_deducted(msg)

    assert grace_called == {"pod_id": "pod-1", "user_id": "user-1"}
    assert acked["called"] is True


async def test_handle_billing_deducted_naks_on_operational_error(monkeypatch):
    msg = FakeMessage(
        json.dumps({"pod_id": "pod-1", "user_id": "user-1", "amount": 2.5, "tx_id": "tx-1"}).encode()
    )
    nacked = {}

    class FakeDBContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_deduct_credits(db, user_id, amount, description, tx_id):
        raise OperationalError("stmt", {}, Exception("db down"))

    async def fake_safe_nak(message, delay=0):
        nacked["delay"] = delay

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.deduct_credits", fake_deduct_credits)
    monkeypatch.setattr("app.services.billing_consumer._safe_nak", fake_safe_nak)

    await billing_module._handle_billing_deducted(msg)

    assert nacked["delay"] == 10


async def test_handle_billing_deducted_acks_on_duplicate_tx(monkeypatch):
    msg = FakeMessage(
        json.dumps({"pod_id": "pod-1", "user_id": "user-1", "amount": 2.5, "tx_id": "tx-1"}).encode()
    )
    acked = {}

    class FakeDBContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_deduct_credits(db, user_id, amount, description, tx_id):
        raise IntegrityError("stmt", {}, Exception("duplicate"))

    async def fake_safe_ack(message):
        acked["called"] = True

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.deduct_credits", fake_deduct_credits)
    monkeypatch.setattr("app.services.billing_consumer._safe_ack", fake_safe_ack)

    await billing_module._handle_billing_deducted(msg)

    assert acked["called"] is True


async def test_handle_billing_deducted_acks_on_success(monkeypatch):
    msg = FakeMessage(
        json.dumps({"pod_id": "pod-1", "user_id": "user-1", "amount": 2.5, "tx_id": "tx-1"}).encode()
    )
    acked = {}

    class FakeDBContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_deduct_credits(db, user_id, amount, description, tx_id):
        assert user_id == "user-1"
        assert amount == 2.5
        assert description == "vm_usage:pod-1"
        assert tx_id == "tx-1"

    async def fake_safe_ack(message):
        acked["called"] = True

    async def fake_resolve_session(db, pod_ref):
        return None

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.deduct_credits", fake_deduct_credits)
    monkeypatch.setattr("app.services.billing_consumer.resolve_session", fake_resolve_session)
    monkeypatch.setattr("app.services.billing_consumer._safe_ack", fake_safe_ack)

    await billing_module._handle_billing_deducted(msg)

    assert acked["called"] is True


async def test_handle_billing_deducted_acks_on_unknown_exception(monkeypatch):
    msg = FakeMessage(
        json.dumps({"pod_id": "pod-1", "user_id": "user-1", "amount": 2.5, "tx_id": "tx-1"}).encode()
    )
    acked = {}

    class FakeDBContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_deduct_credits(db, user_id, amount, description, tx_id):
        raise RuntimeError("unexpected")

    async def fake_safe_ack(message):
        acked["called"] = True

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.deduct_credits", fake_deduct_credits)
    monkeypatch.setattr("app.services.billing_consumer._safe_ack", fake_safe_ack)

    await billing_module._handle_billing_deducted(msg)

    assert acked["called"] is True


async def test_handle_billing_exhausted_ignores_malformed_message():
    msg = FakeMessage(b"{bad json")

    assert await billing_module._handle_billing_exhausted(msg) is None


async def test_handle_billing_exhausted_marks_active_pod_terminated(monkeypatch):
    session = type(
        "Session", (), {"state": "running", "id": "sess-1", "user_id": "user-1"}
    )()
    committed = {}
    notified = {}

    class FakeDB:
        async def commit(self):
            committed["called"] = True

    class FakeDBContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_resolve_session(db, pod_ref):
        assert pod_ref == "pod-1"
        return session

    async def fake_notify(db, user_id, **kwargs):
        notified["user_id"] = user_id
        notified.update(kwargs)

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.resolve_session", fake_resolve_session)
    monkeypatch.setattr("app.services.billing_consumer.notify", fake_notify)

    msg = FakeMessage(json.dumps({"pod_id": "pod-1"}).encode())
    await billing_module._handle_billing_exhausted(msg)

    assert session.state == "terminated"
    assert committed["called"] is True
    assert notified["user_id"] == "user-1"
    assert notified["data"]["reason"] == "credits_exhausted"


async def test_handle_billing_exhausted_skips_terminal_states(monkeypatch):
    session = type(
        "Session", (), {"state": "failed", "id": "sess-1", "user_id": "user-1"}
    )()
    committed = {"called": False}
    notified = {}

    class FakeDB:
        async def commit(self):
            committed["called"] = True

    class FakeDBContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_resolve_session(db, pod_ref):
        return session

    async def fake_notify(db, user_id, **kwargs):
        notified["user_id"] = user_id

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.resolve_session", fake_resolve_session)
    monkeypatch.setattr("app.services.billing_consumer.notify", fake_notify)

    msg = FakeMessage(json.dumps({"pod_id": "pod-1"}).encode())
    await billing_module._handle_billing_exhausted(msg)

    assert session.state == "failed"
    assert committed["called"] is False
    assert notified == {}


async def test_start_billing_consumer_subscribes_to_both_subjects(monkeypatch):
    subscriptions = []

    class FakeNC:
        async def subscribe(self, subject, queue, cb):
            subscriptions.append((subject, queue, cb))

    monkeypatch.setattr("app.services.billing_consumer.nats_client.get_nc", lambda: FakeNC())

    await billing_module.start_billing_consumer()

    assert subscriptions[0][0] == "billing.deducted"
    assert subscriptions[1][0] == "billing.exhausted"
    assert all(queue == "billing-workers" for _, queue, _ in subscriptions)


# ---------------------------------------------------------------------------
# Grace period (_handle_exhausted_tick)
# ---------------------------------------------------------------------------


class FakePodSession:
    def __init__(self, state="running", grace_expires_at=None):
        self.id = "sess-1"
        self.user_id = "user-1"
        self.state = state
        self.grace_expires_at = grace_expires_at


class FakeDB:
    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


def _grace_env(monkeypatch, session):
    """Wire the fakes shared by all grace tests; returns (db, published, notified)."""
    db = FakeDB()
    published = {}
    notified = {}

    class FakeDBContext:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_resolve_session(_db, pod_ref):
        return session

    class FakeNC:
        async def publish(self, subject, payload):
            published["subject"] = subject
            published["payload"] = json.loads(payload)

    async def fake_notify(_db, user_id, **kwargs):
        notified["user_id"] = user_id
        notified.update(kwargs)

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.resolve_session", fake_resolve_session)
    monkeypatch.setattr("app.services.billing_consumer.nats_client.get_nc", lambda: FakeNC())
    monkeypatch.setattr("app.services.billing_consumer.notify", fake_notify)
    return db, published, notified


async def test_first_exhausted_tick_starts_grace_and_warns(monkeypatch):
    session = FakePodSession(grace_expires_at=None)
    db, published, notified = _grace_env(monkeypatch, session)

    await billing_module._handle_exhausted_tick("pod-1", "user-1")

    assert session.grace_expires_at is not None
    assert db.committed is True
    assert notified["user_id"] == "user-1"
    assert notified["type_"] == "warning"
    assert "subject" not in published  # NOT killed yet


async def test_exhausted_tick_within_grace_is_noop(monkeypatch):
    from datetime import datetime, timedelta

    deadline = datetime.utcnow() + timedelta(minutes=3)
    session = FakePodSession(grace_expires_at=deadline)
    db, published, notified = _grace_env(monkeypatch, session)

    await billing_module._handle_exhausted_tick("pod-1", "user-1")

    assert session.grace_expires_at == deadline  # unchanged
    assert "subject" not in published
    assert notified == {}


async def test_exhausted_tick_after_grace_publishes_exhausted(monkeypatch):
    from datetime import datetime, timedelta

    session = FakePodSession(grace_expires_at=datetime.utcnow() - timedelta(seconds=1))
    db, published, notified = _grace_env(monkeypatch, session)

    await billing_module._handle_exhausted_tick("pod-1", "user-1")

    assert published["subject"] == "billing.exhausted"
    assert published["payload"] == {"pod_id": "pod-1", "user_id": "user-1"}


async def test_exhausted_tick_skips_terminal_sessions(monkeypatch):
    session = FakePodSession(state="terminated")
    db, published, notified = _grace_env(monkeypatch, session)

    await billing_module._handle_exhausted_tick("pod-1", "user-1")

    assert session.grace_expires_at is None
    assert "subject" not in published
    assert notified == {}


# ---------------------------------------------------------------------------
# Low-credit threshold warnings (_maybe_warn_low_credits)
# ---------------------------------------------------------------------------


class FakeTransfer:
    def __init__(self, prev=None, new=None):
        if prev is not None:
            self.previous_user_balance = prev
        if new is not None:
            self.new_user_balance = new


def _warn_env(monkeypatch, burn_per_minute):
    published = {}
    notified = {}

    async def fake_burn(db, user_id):
        return burn_per_minute

    class FakeNC:
        async def publish(self, subject, payload):
            published["subject"] = subject
            published["payload"] = json.loads(payload)

    async def fake_notify(_db, user_id, **kwargs):
        notified["user_id"] = user_id
        notified.update(kwargs)

    monkeypatch.setattr("app.services.billing_consumer._burn_per_minute", fake_burn)
    monkeypatch.setattr("app.services.billing_consumer.nats_client.get_nc", lambda: FakeNC())
    monkeypatch.setattr("app.services.billing_consumer.notify", fake_notify)
    return published, notified


async def test_warns_when_crossing_threshold(monkeypatch):
    # 1 credit/min burn: 31 min → 29 min remaining crosses the 30-min line.
    published, notified = _warn_env(monkeypatch, burn_per_minute=1.0)
    transfer = FakeTransfer(prev=31.0, new=29.0)

    await billing_module._maybe_warn_low_credits(object(), "user-1", "pod-1", transfer)

    assert published["subject"] == "billing.warning"
    assert published["payload"]["threshold_minutes"] == 30
    assert published["payload"]["minutes_remaining"] == 29
    assert notified["type_"] == "warning"


async def test_no_warning_without_crossing(monkeypatch):
    published, notified = _warn_env(monkeypatch, burn_per_minute=1.0)
    transfer = FakeTransfer(prev=29.0, new=28.0)  # already under 30, above 10

    await billing_module._maybe_warn_low_credits(object(), "user-1", "pod-1", transfer)

    assert published == {}
    assert notified == {}


async def test_no_warning_on_idempotent_replay(monkeypatch):
    published, notified = _warn_env(monkeypatch, burn_per_minute=1.0)
    transfer = FakeTransfer()  # replay path: no balance attributes

    await billing_module._maybe_warn_low_credits(object(), "user-1", "pod-1", transfer)

    assert published == {}
    assert notified == {}


async def test_crossing_multiple_thresholds_fires_largest_only(monkeypatch):
    # A big deduction can jump 65 → 8 minutes: warn once, at the highest
    # threshold crossed (60), not four times.
    published, notified = _warn_env(monkeypatch, burn_per_minute=1.0)
    transfer = FakeTransfer(prev=65.0, new=8.0)

    await billing_module._maybe_warn_low_credits(object(), "user-1", "pod-1", transfer)

    assert published["payload"]["threshold_minutes"] == 60
    assert notified["type_"] == "warning"


async def test_grace_cleared_on_successful_tick(monkeypatch):
    """A top-up makes the next deduction succeed — the pending grace deadline
    must be cleared so the VM survives."""
    from datetime import datetime, timedelta

    msg = FakeMessage(
        json.dumps({"pod_id": "pod-1", "user_id": "user-1", "amount": 1.0, "tx_id": "tx-9"}).encode()
    )
    session = FakePodSession(grace_expires_at=datetime.utcnow() + timedelta(minutes=2))
    db = FakeDB()

    class FakeDBContext:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_deduct_credits(_db, user_id, amount, description, tx_id):
        return FakeTransfer()  # replay-shaped: no warning side effects

    async def fake_resolve_session(_db, pod_ref):
        return session

    async def fake_safe_ack(message):
        pass

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.deduct_credits", fake_deduct_credits)
    monkeypatch.setattr("app.services.billing_consumer.resolve_session", fake_resolve_session)
    monkeypatch.setattr("app.services.billing_consumer._safe_ack", fake_safe_ack)

    await billing_module._handle_billing_deducted(msg)

    assert session.grace_expires_at is None
    assert db.committed is True
