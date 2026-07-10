"""Integration tests for the audit-log retention purge (NFR-NF-014)."""

from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest
from sqlalchemy import func, select


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _docker_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker is required for integration tests",
)

from app.models import AuditLog
from app.services import audit_retention


async def _insert_audit_row(db, row_id: str, age_days: int) -> None:
    # created_at has a server_default of now(); we overwrite it explicitly so
    # each row has a deterministic age relative to the DB clock.
    db.add(
        AuditLog(
            id=row_id,
            user_id="user-1",
            action="test.event",
            resource_type="test",
            resource_id=None,
            ip_address="127.0.0.1",
            status_code=200,
            metadata_={},
            created_at=datetime.utcnow() - timedelta(days=age_days),
        )
    )
    await db.commit()


async def _count_audit_rows(db) -> int:
    result = await db.execute(select(func.count()).select_from(AuditLog))
    return result.scalar_one()


async def test_purge_removes_only_rows_older_than_window(db_session):
    await _insert_audit_row(db_session, "old-1", age_days=100)
    await _insert_audit_row(db_session, "old-2", age_days=91)
    await _insert_audit_row(db_session, "recent-1", age_days=1)
    await _insert_audit_row(db_session, "recent-2", age_days=89)
    assert await _count_audit_rows(db_session) == 4

    deleted = await audit_retention.purge_expired_audit_logs(db_session, 90)
    assert deleted == 2
    assert await _count_audit_rows(db_session) == 2

    remaining = (await db_session.execute(select(AuditLog.id))).scalars().all()
    assert set(remaining) == {"recent-1", "recent-2"}


async def test_purge_is_idempotent(db_session):
    await _insert_audit_row(db_session, "old-1", age_days=200)
    await _insert_audit_row(db_session, "recent-1", age_days=2)

    first = await audit_retention.purge_expired_audit_logs(db_session, 90)
    second = await audit_retention.purge_expired_audit_logs(db_session, 90)
    assert first == 1
    assert second == 0
    assert await _count_audit_rows(db_session) == 1


async def test_purge_disabled_keeps_everything(db_session):
    await _insert_audit_row(db_session, "old-1", age_days=500)
    deleted = await audit_retention.purge_expired_audit_logs(db_session, 0)
    assert deleted == 0
    assert await _count_audit_rows(db_session) == 1
