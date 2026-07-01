from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import billing_consumer, credit_alerts


class FakeMsg:
    def __init__(self, payload: bytes):
        self.data = payload
        self.acked = False
        self.nacked = False

    async def ack(self):
        self.acked = True

    async def nak(self, delay=0):
        self.nacked = True


class FakeSessionFactory:
    def __init__(self, db):
        self.db = db

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_warning_threshold_for_minutes():
    assert credit_alerts.warning_threshold_for_minutes(59.9) == 60
    assert credit_alerts.warning_threshold_for_minutes(30) == 30
    assert credit_alerts.warning_threshold_for_minutes(9.5) == 10
    assert credit_alerts.warning_threshold_for_minutes(4.5) == 5
    assert credit_alerts.warning_threshold_for_minutes(0) is None
    assert credit_alerts.warning_threshold_for_minutes(90) is None


def test_hourly_rate_for_plan():
    assert credit_alerts.hourly_rate_for_plan("small") == 1
    assert credit_alerts.hourly_rate_for_plan("medium") == 2
    assert credit_alerts.hourly_rate_for_plan("large") == 4
    assert credit_alerts.hourly_rate_for_plan("missing") == 0


@pytest.mark.asyncio
async def test_billing_insufficient_credits_starts_grace(monkeypatch):
    started = []
    published = []
    session = SimpleNamespace(id="pod-api", state="running")

    async def deduct(*args, **kwargs):
        raise ValueError("insufficient")

    async def get_session(db, pod_id):
        return session

    async def start_grace(db, session):
        started.append(session.id)

    async def publish_exhausted(pod_id, user_id):
        published.append((pod_id, user_id))

    monkeypatch.setattr(billing_consumer, "async_session", FakeSessionFactory(object()))
    monkeypatch.setattr(billing_consumer, "deduct_credits", deduct)
    monkeypatch.setattr(billing_consumer, "get_billing_session", get_session)
    monkeypatch.setattr(billing_consumer, "start_credit_grace", start_grace)
    monkeypatch.setattr(billing_consumer, "publish_billing_exhausted", publish_exhausted)

    msg = FakeMsg(
        b'{"pod_id": "pod-k8s", "amount": 1, "user_id": "user-1", "tx_id": "tx-1"}'
    )

    await billing_consumer._handle_billing_deducted(msg)

    assert started == ["pod-api"]
    assert published == []
    assert msg.acked is True


@pytest.mark.asyncio
async def test_start_credit_grace_sets_deadline_and_notifies(monkeypatch):
    notifications = []
    session = SimpleNamespace(
        id="pod-api",
        user_id="user-1",
        expires_at=None,
    )

    class FakeDB:
        commits = 0

        async def commit(self):
            self.commits += 1

        async def refresh(self, item):
            pass

    async def create_notification_safely(db, **kwargs):
        notifications.append(kwargs)

    monkeypatch.setattr(credit_alerts, "create_notification_safely", create_notification_safely)
    db = FakeDB()
    now = datetime(2026, 1, 1, 12, 0)

    await credit_alerts.start_credit_grace(db, session=session, now=now)

    assert session.expires_at == now + timedelta(minutes=5)
    assert db.commits == 1
    assert notifications[0]["type"] == "credit_grace"
    assert notifications[0]["severity"] == "error"
