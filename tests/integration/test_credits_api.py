from pathlib import Path
import sys

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
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
from app.services.credit_service import add_credits, get_balance, get_or_create_account


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
async def test_get_credit_balance_returns_zero_for_new_user(client, db_session):
    response = await client.get("/credits/balance")

    assert response.status_code == 200
    body = response.json()
    assert body["balance"] == 0.0
    assert body["account_id"]

    account = await get_or_create_account(db_session, "student-1")
    assert body["account_id"] == account.id


@pytest.mark.asyncio
async def test_get_credit_history_returns_ledger_entries(client, db_session):
    await add_credits(db_session, "student-1", 25.0, "initial_grant")

    response = await client.get("/credits/history")

    assert response.status_code == 200
    history = response.json()
    assert len(history) == 1
    assert history[0]["amount"] == 25.0
    assert history[0]["direction"] == "credit"
    assert history[0]["type"] == "initial_grant"


@pytest.mark.asyncio
async def test_admin_allocate_credits_updates_student_balance(client, db_session, current_user_payload):
    current_user_payload.sub = "admin-1"
    current_user_payload.role = "admin"
    current_user_payload.email = "admin@cs.du.ac.bd"
    db_session.add_all(
        [
            User(id="admin-1", email="admin@cs.du.ac.bd", name="Admin", role="admin"),
            User(id="student-2", email="student2@cs.du.ac.bd", name="Student Two", role="student"),
        ]
    )
    await db_session.commit()

    response = await client.post(
        "/credits/allocate",
        json={"user_id": "student-2", "amount": 15.0, "description": "seed_fund"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "granted"
    assert body["transfer_id"]
    assert await get_balance(db_session, "student-2") == 15.0


@pytest.mark.asyncio
async def test_professor_can_allocate_credits_to_student(client, db_session, current_user_payload):
    current_user_payload.sub = "prof-1"
    current_user_payload.role = "professor"
    current_user_payload.email = "prof@cs.du.ac.bd"
    db_session.add_all(
        [
            User(id="prof-1", email="prof@cs.du.ac.bd", name="Professor", role="professor"),
            User(id="student-2", email="student2@cs.du.ac.bd", name="Student Two", role="student"),
        ]
    )
    await db_session.commit()
    await add_credits(db_session, "prof-1", 40.0, "admin_grant")

    response = await client.post(
        "/credits/allocate",
        json={"user_id": "student-2", "amount": 12.5, "description": "lab_time"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "allocated"
    assert body["transfer_id"]
    assert await get_balance(db_session, "prof-1") == 27.5
    assert await get_balance(db_session, "student-2") == 12.5


@pytest.mark.asyncio
async def test_student_cannot_list_students_or_allocate_credits(client, db_session):
    db_session.add(User(id="student-2", email="student2@cs.du.ac.bd", name="Student Two", role="student"))
    await db_session.commit()

    students_response = await client.get("/credits/students")
    allocate_response = await client.post(
        "/credits/allocate",
        json={"user_id": "student-2", "amount": 5.0, "description": "not_allowed"},
    )

    assert students_response.status_code == 403
    assert students_response.json() == {"detail": "Teachers only"}
    assert allocate_response.status_code == 403
    assert allocate_response.json() == {"detail": "Only admins and teachers can allocate credits"}
