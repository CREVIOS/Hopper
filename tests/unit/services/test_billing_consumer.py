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


async def test_handle_billing_deducted_publishes_exhausted_on_insufficient_credits(monkeypatch):
    msg = FakeMessage(
        json.dumps({"pod_id": "pod-1", "user_id": "user-1", "amount": 2.5, "tx_id": "tx-1"}).encode()
    )
    published = {}
    acked = {}

    class FakeDBContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_deduct_credits(db, user_id, amount, description, tx_id):
        raise ValueError("insufficient")

    class FakeNC:
        async def publish(self, subject, payload):
            published["subject"] = subject
            published["payload"] = json.loads(payload)

    async def fake_safe_ack(message):
        acked["called"] = True

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.deduct_credits", fake_deduct_credits)
    monkeypatch.setattr("app.services.billing_consumer.nats_client.get_nc", lambda: FakeNC())
    monkeypatch.setattr("app.services.billing_consumer._safe_ack", fake_safe_ack)

    await billing_module._handle_billing_deducted(msg)

    assert published["subject"] == "billing.exhausted"
    assert published["payload"] == {"pod_id": "pod-1", "user_id": "user-1"}
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

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())
    monkeypatch.setattr("app.services.billing_consumer.deduct_credits", fake_deduct_credits)
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
    session = type("Session", (), {"state": "running"})()
    committed = {}

    class FakeResult:
        def scalars(self):
            return self

        def first(self):
            return session

    class FakeDB:
        async def execute(self, stmt):
            return FakeResult()

        async def commit(self):
            committed["called"] = True

    class FakeDBContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())

    msg = FakeMessage(json.dumps({"pod_id": "pod-1"}).encode())
    await billing_module._handle_billing_exhausted(msg)

    assert session.state == "terminated"
    assert committed["called"] is True


async def test_handle_billing_exhausted_skips_terminal_states(monkeypatch):
    session = type("Session", (), {"state": "failed"})()
    committed = {"called": False}

    class FakeResult:
        def scalars(self):
            return self

        def first(self):
            return session

    class FakeDB:
        async def execute(self, stmt):
            return FakeResult()

        async def commit(self):
            committed["called"] = True

    class FakeDBContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())

    msg = FakeMessage(json.dumps({"pod_id": "pod-1"}).encode())
    await billing_module._handle_billing_exhausted(msg)

    assert session.state == "failed"
    assert committed["called"] is False


async def test_handle_billing_exhausted_matches_pod_by_id_or_pod_name(monkeypatch):
    """Fresh pods emit the K8s pod name as pod_id while reconciled pods emit the
    UUID, so the exhaustion handler must match on either. Guard that the query
    references both columns (the id-only lookup left fresh pods stuck 'running')."""
    session = type("Session", (), {"state": "running"})()
    captured = {}

    class FakeResult:
        def scalars(self):
            return self

        def first(self):
            return session

    class FakeDB:
        async def execute(self, stmt):
            captured["sql"] = str(stmt)
            return FakeResult()

        async def commit(self):
            pass

    class FakeDBContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.services.billing_consumer.async_session", lambda: FakeDBContext())

    # pod_id here is the K8s name a fresh pod emits, not the session UUID.
    msg = FakeMessage(json.dumps({"pod_id": "vm-1700000000"}).encode())
    await billing_module._handle_billing_exhausted(msg)

    assert session.state == "terminated"
    assert "id" in captured["sql"] and "pod_name" in captured["sql"]


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
