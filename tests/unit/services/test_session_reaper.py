from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.session_reaper import reap_expired_sessions


NOW = datetime(2026, 7, 12, 12, 0, 0)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


def session(*, state="running", expires_at=None):
    return SimpleNamespace(
        id="pod-1", user_id="student-1", pod_name="vm-pod-1",
        state=state, expires_at=expires_at or NOW - timedelta(seconds=1),
        updated_at=None,
    )


def database(rows):
    db = SimpleNamespace(
        execute=AsyncMock(return_value=Result(rows)),
        commit=AsyncMock(),
        add=Mock(),
    )
    return db


@pytest.mark.asyncio
async def test_expired_session_cleaned_up():
    row, db, terminate = session(), database([]), AsyncMock(return_value=True)
    db.execute.return_value = Result([row])
    assert await reap_expired_sessions(db, now=NOW, terminate=terminate, publish=AsyncMock()) == ["pod-1"]
    terminate.assert_awaited_once_with("vm-pod-1")
    assert row.state == "terminated"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_session_not_reaped():
    db, terminate = database([]), AsyncMock()
    assert await reap_expired_sessions(db, now=NOW, terminate=terminate, publish=AsyncMock()) == []
    terminate.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reaper_idempotent():
    row, db, terminate = session(), database([]), AsyncMock(return_value=True)
    db.execute.side_effect = [Result([row]), Result([])]
    assert await reap_expired_sessions(db, now=NOW, terminate=terminate, publish=AsyncMock()) == ["pod-1"]
    assert await reap_expired_sessions(db, now=NOW, terminate=terminate, publish=AsyncMock()) == []
    terminate.assert_awaited_once()


@pytest.mark.asyncio
async def test_reaper_handles_already_deleted_namespace():
    row, db = session(), database([])
    db.execute.return_value = Result([row])
    terminate = AsyncMock(side_effect=RuntimeError("pod already deleted: not found"))
    assert await reap_expired_sessions(db, now=NOW, terminate=terminate, publish=AsyncMock()) == ["pod-1"]
    assert row.state == "terminated"


@pytest.mark.asyncio
async def test_audit_event_emitted_on_reap():
    row, db, publish = session(), database([]), AsyncMock()
    db.execute.return_value = Result([row])
    await reap_expired_sessions(db, now=NOW, terminate=AsyncMock(return_value=True), publish=publish)
    audit = db.add.call_args.args[0]
    assert audit.action == "session.reaped"
    assert audit.resource_id == "pod-1"
    publish.assert_awaited_once()
    assert publish.call_args.args[0] == "session.reaped"
