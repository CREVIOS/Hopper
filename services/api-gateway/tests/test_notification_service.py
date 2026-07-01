from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.notifications import read_notification
from app.schemas.user import TokenPayload
from app.services import notification_service


class FakeScalars:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class FakeDB:
    def __init__(self, existing=None, old_ids=None):
        self.existing = existing
        self.old_ids = old_ids or []
        self.added = []
        self.deleted = False
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, stmt):
        return self.existing

    async def scalars(self, stmt):
        return FakeScalars(self.old_ids)

    async def execute(self, stmt):
        self.deleted = True

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        for item in self.added:
            item.created_at = datetime(2026, 1, 1, 12, 0)

    async def commit(self):
        self.commits += 1

    async def refresh(self, item):
        if item.created_at is None:
            item.created_at = datetime(2026, 1, 1, 12, 0)

    async def rollback(self):
        self.rollbacks += 1


def user(sub: str) -> TokenPayload:
    return TokenPayload(
        sub=sub,
        email=f"{sub}@example.edu",
        name=sub,
        role="student",
        exp=9999999999,
        email_verified=True,
    )


def test_notification_subject_is_safe_and_stable():
    subject = notification_service.notification_subject("user.with.dot@example.edu")

    assert subject.startswith("notifications.")
    assert "*" not in subject
    assert ">" not in subject
    assert " " not in subject


@pytest.mark.asyncio
async def test_create_notification_dedupes_existing(monkeypatch):
    existing = SimpleNamespace(id="existing")
    db = FakeDB(existing=existing)
    published = []

    async def publish(notification):
        published.append(notification)

    monkeypatch.setattr(notification_service, "publish_notification", publish)

    result = await notification_service.create_notification(
        db,
        user_id="user-1",
        type="vm_ready",
        severity="success",
        title="VM ready",
        body="Ready",
        dedupe_key="same-event",
    )

    assert result is existing
    assert db.added == []
    assert published == []


@pytest.mark.asyncio
async def test_create_notification_prunes_and_publishes(monkeypatch):
    db = FakeDB(old_ids=["old-1", "old-2"])
    published = []

    async def publish(notification):
        published.append(notification.id)

    monkeypatch.setattr(notification_service, "publish_notification", publish)

    result = await notification_service.create_notification(
        db,
        user_id="user-1",
        type="credits_received",
        severity="success",
        title="Credits received",
        body="50 credits",
        dedupe_key="transfer-1",
    )

    assert result.id
    assert db.deleted is True
    assert db.commits == 1
    assert published == [result.id]


@pytest.mark.asyncio
async def test_read_notification_rejects_missing_or_other_user(monkeypatch):
    class MissingDB(FakeDB):
        async def scalar(self, stmt):
            return None

    with pytest.raises(HTTPException) as exc:
        await read_notification("notif-1", current_user=user("user-1"), db=MissingDB())

    assert exc.value.status_code == 404
