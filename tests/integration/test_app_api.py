from pathlib import Path
import sys
from urllib.parse import urlparse

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.main import create_app


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
async def client():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_health_and_ready_endpoints_report_liveness_and_deep_readiness(client):
    """/healthz is a shallow liveness signal; /readyz deep-checks dependencies.

    This client fixture runs the app without lifespan, so NATS is never
    connected — the correct /readyz answer here is 503 "degraded" with
    per-component detail, not a blanket 200 (that was the old, static
    behavior this test used to encode).
    """
    health_response = await client.get("/healthz")
    ready_response = await client.get("/readyz")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert health_response.headers["x-content-type-options"] == "nosniff"
    assert health_response.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    assert ready_response.status_code == 503
    body = ready_response.json()
    assert body["status"] == "degraded"
    assert set(body["checks"]) == {"database", "nats", "orchestrator"}
    assert body["checks"]["nats"] is False
    assert ready_response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_db_session_uses_migrated_schema(db_session):
    result = await db_session.execute(
        text(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename IN (
                'accounts',
                'audit_logs',
                'issue_reports',
                'ledger_entries',
                'metrics_samples',
                'pod_sessions',
                'ssh_keys',
                'transfers',
                'users'
              )
            """
        )
    )

    table_names = {row[0] for row in result}

    assert table_names == {
        "accounts",
        "audit_logs",
        "issue_reports",
        "ledger_entries",
        "metrics_samples",
        "pod_sessions",
        "ssh_keys",
        "transfers",
        "users",
    }


def test_nats_url_exposes_nats_scheme_and_port(nats_url):
    parsed = urlparse(nats_url)

    assert parsed.scheme == "nats"
    assert parsed.hostname
    assert parsed.port
