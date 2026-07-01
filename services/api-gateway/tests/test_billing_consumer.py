import json

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.services import billing_consumer


class FakeMsg:
    def __init__(self, payload: dict):
        self.data = json.dumps(payload).encode()
        self.acked = False
        self.nacked = False
        self.nak_delay = None

    async def ack(self):
        self.acked = True

    async def nak(self, delay=0):
        self.nacked = True
        self.nak_delay = delay


@pytest.mark.asyncio
async def test_duplicate_billing_tx_is_acked(monkeypatch):
    async def duplicate(*args, **kwargs):
        raise IntegrityError("duplicate", None, None)

    monkeypatch.setattr(billing_consumer, "deduct_credits", duplicate)
    msg = FakeMsg({"pod_id": "pod-1", "amount": 1, "user_id": "user-1", "tx_id": "tx-1"})

    await billing_consumer._handle_billing_deducted(msg)

    assert msg.acked is True
    assert msg.nacked is False


@pytest.mark.asyncio
async def test_transient_billing_db_error_is_nacked(monkeypatch):
    async def transient(*args, **kwargs):
        raise OperationalError("statement", {}, Exception("db down"))

    monkeypatch.setattr(billing_consumer, "deduct_credits", transient)
    msg = FakeMsg({"pod_id": "pod-1", "amount": 1, "user_id": "user-1", "tx_id": "tx-1"})

    await billing_consumer._handle_billing_deducted(msg)

    assert msg.acked is False
    assert msg.nacked is True
    assert msg.nak_delay == 10


@pytest.mark.asyncio
async def test_credit_exhaustion_publishes_durable_event_and_acks(monkeypatch):
    published = []

    async def exhausted(*args, **kwargs):
        raise ValueError("insufficient")

    async def publish(subject, payload):
        published.append((subject, payload))

    monkeypatch.setattr(billing_consumer, "deduct_credits", exhausted)
    monkeypatch.setattr(billing_consumer.nats_client, "publish_billing_event", publish)
    msg = FakeMsg({"pod_id": "pod-1", "amount": 1, "user_id": "user-1", "tx_id": "tx-1"})

    await billing_consumer._handle_billing_deducted(msg)

    assert msg.acked is True
    assert published == [("billing.exhausted", {"pod_id": "pod-1", "user_id": "user-1"})]
