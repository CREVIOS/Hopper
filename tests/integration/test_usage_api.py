from datetime import datetime, timedelta
from pathlib import Path
import sys

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.dependencies import get_current_user, get_db
from app.main import create_app
from app.middleware import audit as audit_middleware
from app.models import Account, AuditLog, IssueReport, LedgerEntry, MetricsSample, PodSession, SSHKey, Transfer, User
from app.schemas.user import TokenPayload


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


@pytest_asyncio.fixture
async def current_user_payload() -> TokenPayload:
    return TokenPayload(
        sub="student-1",
        email="student1@cs.du.ac.bd",
        name="Student One",
        role="student",
        exp=4_102_444_800,
        email_verified=True,
    )


@pytest_asyncio.fixture
async def clean_database(db_session):
    for model in (
        AuditLog,
        IssueReport,
        MetricsSample,
        SSHKey,
        PodSession,
        LedgerEntry,
        Transfer,
        Account,
        User,
    ):
        await db_session.execute(delete(model))
    await db_session.commit()
    yield
    for model in (
        AuditLog,
        IssueReport,
        MetricsSample,
        SSHKey,
        PodSession,
        LedgerEntry,
        Transfer,
        Account,
        User,
    ):
        await db_session.execute(delete(model))
    await db_session.commit()


@pytest_asyncio.fixture
async def client(db_session, current_user_payload, clean_database):
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    app = create_app()
    original_async_session = audit_middleware.async_session

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def override_get_current_user():
        return current_user_payload

    audit_middleware.async_session = session_factory
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    audit_middleware.async_session = original_async_session


@pytest.mark.asyncio
async def test_get_pod_usage_aggregates_samples_for_requested_pod(client, db_session):
    now = datetime.utcnow().replace(second=0, microsecond=0)
    db_session.add_all(
        [
            MetricsSample(
                time=now - timedelta(minutes=10),
                pod_id="pod-1",
                user_id="student-1",
                cpu_percent=25,
                memory_used_bytes=1_000,
                memory_limit_bytes=2_000,
            ),
            MetricsSample(
                time=now - timedelta(minutes=9),
                pod_id="pod-1",
                user_id="student-1",
                cpu_percent=35,
                memory_used_bytes=1_500,
                memory_limit_bytes=2_000,
            ),
            MetricsSample(
                time=now - timedelta(minutes=8),
                pod_id="pod-2",
                user_id="student-1",
                cpu_percent=90,
                memory_used_bytes=3_000,
                memory_limit_bytes=4_000,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get("/usage/pod-1", params={"range": "1h"})

    assert response.status_code == 200
    body = response.json()
    assert body["pod_id"] == "pod-1"
    assert body["range"] == "1h"
    assert len(body["data"]) >= 1
    assert all(point["memory_limit_bytes"] == 2_000 for point in body["data"])


@pytest.mark.asyncio
async def test_get_my_usage_summary_and_series_include_all_user_pods(client, db_session):
    now = datetime.utcnow().replace(second=0, microsecond=0)
    db_session.add_all(
        [
            MetricsSample(
                time=now - timedelta(minutes=20),
                pod_id="pod-1",
                user_id="student-1",
                cpu_percent=20,
                memory_used_bytes=1_000,
                memory_limit_bytes=2_000,
            ),
            MetricsSample(
                time=now - timedelta(minutes=10),
                pod_id="pod-2",
                user_id="student-1",
                cpu_percent=40,
                memory_used_bytes=3_000,
                memory_limit_bytes=4_000,
            ),
            MetricsSample(
                time=now - timedelta(minutes=5),
                pod_id="pod-3",
                user_id="other-user",
                cpu_percent=80,
                memory_used_bytes=8_000,
                memory_limit_bytes=8_000,
            ),
        ]
    )
    await db_session.commit()

    summary_response = await client.get("/usage/summary/me")
    series_response = await client.get("/usage/summary/me/series", params={"range": "24h"})

    assert summary_response.status_code == 200
    assert summary_response.json()["pod_count"] == 2
    assert summary_response.json()["avg_cpu_percent"] == 30.0
    assert summary_response.json()["avg_memory_bytes"] == 2000

    assert series_response.status_code == 200
    series = series_response.json()
    assert series["range"] == "24h"
    assert len(series["data"]) >= 1
