from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.usage import get_pod_usage
from app.schemas.user import TokenPayload


def user(sub: str) -> TokenPayload:
    return TokenPayload(
        sub=sub,
        email=f"{sub}@example.edu",
        name=sub,
        role="student",
        exp=9999999999,
        email_verified=True,
    )


class FakeResult:
    def fetchall(self):
        return [
            SimpleNamespace(
                bucket=datetime(2026, 1, 1, 12, 0),
                avg_cpu=12.5,
                avg_memory=1024,
                memory_limit=2048,
            )
        ]


class FakeDB:
    def __init__(self, session):
        self.session = session
        self.executed = False

    async def scalar(self, stmt):
        return self.session

    async def execute(self, stmt, params):
        self.executed = True
        self.params = params
        return FakeResult()


@pytest.mark.asyncio
async def test_usage_rejects_other_users_pod():
    db = FakeDB(SimpleNamespace(user_id="owner", pod_name="vm-owner"))

    with pytest.raises(HTTPException) as exc:
        await get_pod_usage("pod-1", current_user=user("intruder"), db=db)

    assert exc.value.status_code == 404
    assert db.executed is False


@pytest.mark.asyncio
async def test_usage_allows_owner_and_queries_api_id_and_pod_name():
    db = FakeDB(SimpleNamespace(user_id="owner", pod_name="vm-owner"))

    response = await get_pod_usage("pod-1", current_user=user("owner"), db=db)

    assert db.executed is True
    assert db.params["pod_id"] == "pod-1"
    assert db.params["metrics_pod_name"] == "vm-owner"
    assert response["data"][0]["cpu_percent"] == 12.5
