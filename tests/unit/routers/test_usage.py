from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.usage import RANGE_MAP, get_my_usage_summary, get_pod_usage
from app.schemas.user import TokenPayload

_OWNED_SESSION = SimpleNamespace(id="pod-1", pod_name="vm-pod-1", user_id="user-1")


class FakeUsageResult:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class FakeSessionResult:
    """Result of the ownership-resolution SELECT (db.execute called with no params)."""

    def __init__(self, session):
        self._session = session

    def scalars(self):
        return self

    def first(self):
        return self._session


class FakeDB:
    def __init__(self, result=None, side_effects=None, session=_OWNED_SESSION):
        self.result = result
        self.side_effects = list(side_effects or [])
        self.session = session
        self.calls = []

    async def execute(self, stmt, params=None):
        # get_pod_usage first resolves the owning session with a param-less
        # SELECT, then runs the metrics query with bind params.
        if params is None:
            return FakeSessionResult(self.session)
        self.calls.append(params)
        if self.side_effects:
            effect = self.side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect
        return self.result


def _payload(sub: str = "user-1", role: str = "student") -> TokenPayload:
    return TokenPayload(
        sub=sub,
        email="user@example.com",
        name="Test User",
        role=role,
        exp=1234567890,
    )


def test_range_map_contains_expected_presets():
    assert set(RANGE_MAP) == {"1h", "6h", "24h", "7d"}


async def test_get_pod_usage_formats_rows():
    db = FakeDB(
        result=FakeUsageResult(
            rows=[
                SimpleNamespace(
                    bucket=datetime(2026, 1, 1, 12, 0, 0),
                    avg_cpu=50.5,
                    avg_memory=2048,
                    memory_limit=4096,
                )
            ]
        )
    )

    result = await get_pod_usage("pod-1", range="1h", current_user=_payload(), db=db)

    assert result["pod_id"] == "pod-1"
    assert result["range"] == "1h"
    assert result["data"][0]["cpu_percent"] == 50.5
    assert result["data"][0]["memory_limit_bytes"] == 4096


async def test_get_pod_usage_falls_back_when_primary_query_fails():
    fallback_result = FakeUsageResult(rows=[])
    db = FakeDB(side_effects=[Exception("no time_bucket"), fallback_result])

    result = await get_pod_usage("pod-1", range="7d", current_user=_payload(), db=db)

    assert result["range"] == "7d"
    assert len(db.calls) == 2


async def test_get_my_usage_summary_returns_zeroes_without_row():
    db = FakeDB(result=FakeUsageResult(row=None))

    result = await get_my_usage_summary(current_user=_payload(), db=db)

    assert result == {
        "pod_count": 0,
        "avg_cpu_percent": 0,
        "avg_memory_bytes": 0,
    }


async def test_get_pod_usage_rejects_non_owner():
    # A student must not read another tenant's metrics by guessing a pod id (IDOR).
    db = FakeDB(
        result=FakeUsageResult(rows=[]),
        session=SimpleNamespace(id="pod-1", pod_name="vm-pod-1", user_id="someone-else"),
    )
    with pytest.raises(HTTPException) as exc:
        await get_pod_usage("pod-1", range="1h", current_user=_payload(), db=db)

    assert exc.value.status_code == 403


async def test_get_pod_usage_404_when_session_missing():
    db = FakeDB(result=FakeUsageResult(rows=[]), session=None)
    with pytest.raises(HTTPException) as exc:
        await get_pod_usage("nope", range="1h", current_user=_payload(), db=db)

    assert exc.value.status_code == 404


async def test_get_pod_usage_admin_can_view_any_pod():
    # Admins may inspect any user's usage (read-only), bypassing ownership.
    db = FakeDB(
        result=FakeUsageResult(rows=[]),
        session=SimpleNamespace(id="pod-1", pod_name="vm-pod-1", user_id="someone-else"),
    )
    result = await get_pod_usage("pod-1", range="1h", current_user=_payload("admin-1", "admin"), db=db)

    assert result["pod_id"] == "pod-1"
