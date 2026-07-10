from pathlib import Path
import sys

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.dependencies import get_current_user, get_db
from app.main import create_app
from app.middleware import audit as audit_middleware
from app.models import IssueReport
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
async def client(db_session, current_user_payload):
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
async def test_create_issue_and_list_my_issues(client, db_session):
    create_response = await client.post(
        "/issues/",
        json={"pod_id": "pod-1", "description": " GPU session froze unexpectedly "},
    )

    assert create_response.status_code == 201
    created_issue = create_response.json()
    assert created_issue["user_id"] == "student-1"
    assert created_issue["pod_id"] == "pod-1"
    assert created_issue["description"] == "GPU session froze unexpectedly"
    assert created_issue["status"] == "open"

    issue = await db_session.get(IssueReport, created_issue["id"])
    assert issue is not None
    assert issue.description == "GPU session froze unexpectedly"

    list_response = await client.get("/issues/me")

    assert list_response.status_code == 200
    issues = list_response.json()
    assert len(issues) == 1
    assert issues[0]["id"] == created_issue["id"]


@pytest.mark.asyncio
async def test_admin_can_filter_and_resolve_issue(client, db_session, current_user_payload):
    current_user_payload.role = "admin"
    db_session.add(
        IssueReport(
            id="issue-1",
            user_id="student-1",
            pod_id="pod-1",
            description="Disk is full",
            status="open",
        )
    )
    await db_session.commit()

    list_response = await client.get("/issues/admin", params={"status": "open"})

    assert list_response.status_code == 200
    issues = list_response.json()
    assert len(issues) == 1
    assert issues[0]["id"] == "issue-1"

    resolve_response = await client.post("/issues/admin/issue-1/resolve")

    assert resolve_response.status_code == 200
    resolved = resolve_response.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None

    issue = await db_session.get(IssueReport, "issue-1")
    assert issue is not None
    assert issue.status == "resolved"


@pytest.mark.asyncio
async def test_issue_admin_endpoint_requires_admin_role(client, db_session):
    db_session.add(
        IssueReport(
            id="issue-1",
            user_id="student-1",
            pod_id="pod-1",
            description="Disk is full",
            status="open",
        )
    )
    await db_session.commit()

    response = await client.get("/issues/admin")

    assert response.status_code == 403
    assert response.json() == {"detail": "Admin only"}
