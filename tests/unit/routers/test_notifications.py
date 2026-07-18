from datetime import datetime

import pytest
from fastapi import HTTPException

from app.models.notification import Notification
from app.routers.notifications import _serialize, list_notifications, mark_all_read, mark_read
from app.schemas.user import TokenPayload


def _payload() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="User One",
        role="student",
        exp=1234567890,
    )


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one(self):
        return self._rows


class FakeDB:
    def __init__(self, *, execute_results=None, fetched=None):
        self.execute_results = list(execute_results or [])
        self.fetched = fetched
        self.commits = 0

    async def execute(self, stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return FakeExecuteResult(self.execute_results.pop(0))

    async def get(self, model, notification_id):
        return self.fetched

    async def commit(self):
        self.commits += 1


def test_serialize_formats_notification_payload():
    notification = Notification(
        id="n1",
        user_id="user-1",
        type="info",
        title="Ready",
        body="VM ready",
        data={"pod_id": "p1"},
        read=False,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )

    result = _serialize(notification)

    assert result["id"] == "n1"
    assert result["data"] == {"pod_id": "p1"}
    assert result["created_at"] == "2026-01-01T12:00:00"


async def test_list_notifications_clamps_limit_and_returns_unread_count():
    notification = Notification(
        id="n1",
        user_id="user-1",
        type="info",
        title="Ready",
        body="VM ready",
        data=None,
        read=False,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    db = FakeDB(execute_results=[[notification], 3])

    result = await list_notifications(limit=999, current_user=_payload(), db=db)

    assert result["unread_count"] == 3
    assert result["notifications"][0]["id"] == "n1"


async def test_mark_all_read_commits():
    db = FakeDB(execute_results=[None])

    result = await mark_all_read(current_user=_payload(), db=db)

    assert result == {"message": "ok"}
    assert db.commits == 1


async def test_mark_read_rejects_missing_notification():
    db = FakeDB(fetched=None)

    with pytest.raises(HTTPException) as exc_info:
        await mark_read("missing", current_user=_payload(), db=db)

    assert exc_info.value.status_code == 404


async def test_mark_read_rejects_other_users_notification():
    row = Notification(
        id="n1",
        user_id="other-user",
        type="info",
        title="Ready",
        body="VM ready",
        data=None,
        read=False,
    )
    db = FakeDB(fetched=row)

    with pytest.raises(HTTPException) as exc_info:
        await mark_read("n1", current_user=_payload(), db=db)

    assert exc_info.value.status_code == 404


async def test_mark_read_marks_notification_as_read():
    row = Notification(
        id="n1",
        user_id="user-1",
        type="info",
        title="Ready",
        body="VM ready",
        data=None,
        read=False,
    )
    db = FakeDB(fetched=row)

    result = await mark_read("n1", current_user=_payload(), db=db)

    assert result == {"message": "ok"}
    assert row.read is True
    assert db.commits == 1
