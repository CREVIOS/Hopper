"""Course CRUD, roster management, and course-scoped bulk credit allocation.

Exercised against a real Postgres so the ledger maths (and the all-or-nothing
guarantee on bulk allocation) is verified end-to-end, not against fakes.
"""

from pathlib import Path
import sys

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.dependencies import get_current_user, get_db
from app.main import create_app
from app.middleware import audit as audit_middleware
from app.models import User
from app.schemas.user import TokenPayload
from app.services.credit_service import add_credits, get_balance


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


def _payload(sub: str, role: str, name: str = "Test User") -> TokenPayload:
    return TokenPayload(
        sub=sub,
        email=f"{sub}@cs.du.ac.bd",
        name=name,
        role=role,
        exp=4_102_444_800,
        email_verified=True,
    )


@pytest.fixture
def auth() -> dict:
    """The identity the client authenticates as. Tests reassign ``auth["user"]``
    to switch roles mid-test (admin → professor → an unrelated professor)."""
    return {"user": _payload("admin-1", "admin", "Admin")}


@pytest_asyncio.fixture
async def client(db_session, auth):
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    app = create_app()
    original_async_session = audit_middleware.async_session

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def override_get_current_user():
        return auth["user"]  # read per-request, so tests can switch identity

    audit_middleware.async_session = session_factory
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    audit_middleware.async_session = original_async_session


@pytest_asyncio.fixture
async def people(db_session):
    """One professor, one other professor, three students."""
    db_session.add_all([
        User(id="admin-1", email="admin@cs.du.ac.bd", name="Admin", role="admin"),
        User(id="prof-1", email="prof1@cs.du.ac.bd", name="Prof One", role="professor"),
        User(id="prof-2", email="prof2@cs.du.ac.bd", name="Prof Two", role="professor"),
        User(id="stu-1", email="stu1@cs.du.ac.bd", name="Student One", role="student"),
        User(id="stu-2", email="stu2@cs.du.ac.bd", name="Student Two", role="student"),
        User(id="stu-3", email="stu3@cs.du.ac.bd", name="Student Three", role="student"),
    ])
    await db_session.commit()


async def _make_course(client, code="CSE-4108", professor_id="prof-1") -> str:
    response = await client.post(
        "/admin/courses",
        json={
            "code": code,
            "name": "Operating Systems",
            "description": "OS lab",
            "professor_id": professor_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- Admin CRUD ---------------------------------------------------------------


async def test_admin_creates_course_and_it_appears_in_the_catalogue(client, people):
    course_id = await _make_course(client)

    listing = await client.get("/admin/courses")
    assert listing.status_code == 200
    courses = listing.json()
    assert len(courses) == 1
    assert courses[0]["id"] == course_id
    assert courses[0]["code"] == "CSE-4108"
    assert courses[0]["professor_name"] == "Prof One"  # denormalised for the UI
    assert courses[0]["enrolled_count"] == 0


async def test_duplicate_course_code_is_rejected(client, people):
    await _make_course(client, code="CSE-4108")

    duplicate = await client.post(
        "/admin/courses",
        json={"code": "CSE-4108", "name": "Another", "description": "",
              "professor_id": "prof-1"},
    )

    assert duplicate.status_code == 409


async def test_course_cannot_be_owned_by_a_non_professor(client, people):
    response = await client.post(
        "/admin/courses",
        json={"code": "CSE-9999", "name": "Bad", "description": "",
              "professor_id": "stu-1"},
    )

    assert response.status_code == 400


async def test_deactivating_a_course_keeps_it_in_the_admin_view(client, people):
    course_id = await _make_course(client)

    deleted = await client.delete(f"/admin/courses/{course_id}")
    assert deleted.status_code == 200

    courses = (await client.get("/admin/courses")).json()
    assert len(courses) == 1  # soft-delete: still listed for the admin
    assert courses[0]["is_active"] is False


async def test_non_admin_cannot_create_a_course(client, people, auth):
    auth["user"] = _payload("prof-1", "professor")

    response = await client.post(
        "/admin/courses",
        json={"code": "CSE-1", "name": "X", "description": "", "professor_id": "prof-1"},
    )

    assert response.status_code == 403


# --- Roster -------------------------------------------------------------------


async def test_owning_professor_manages_roster_and_sees_only_their_courses(
    client, people, auth
):
    course_id = await _make_course(client, professor_id="prof-1")
    await _make_course(client, code="CSE-2201", professor_id="prof-2")

    auth["user"] = _payload("prof-1", "professor", "Prof One")

    mine = await client.get("/courses/mine")
    assert mine.status_code == 200
    assert [c["code"] for c in mine.json()] == ["CSE-4108"]  # not prof-2's course

    enrolled = await client.post(
        f"/courses/{course_id}/enrollments", json={"user_id": "stu-1"}
    )
    assert enrolled.status_code == 201

    roster = await client.get(f"/courses/{course_id}/roster")
    assert roster.status_code == 200
    assert [s["id"] for s in roster.json()] == ["stu-1"]


async def test_enrolling_the_same_student_twice_is_idempotent(client, people, auth):
    course_id = await _make_course(client)
    auth["user"] = _payload("prof-1", "professor")

    first = await client.post(f"/courses/{course_id}/enrollments", json={"user_id": "stu-1"})
    second = await client.post(f"/courses/{course_id}/enrollments", json={"user_id": "stu-1"})

    assert first.json()["message"] == "enrolled"
    assert second.json()["message"] == "already_enrolled"

    roster = (await client.get(f"/courses/{course_id}/roster")).json()
    assert len(roster) == 1  # no duplicate row


async def test_only_students_can_be_enrolled(client, people, auth):
    course_id = await _make_course(client)
    auth["user"] = _payload("prof-1", "professor")

    response = await client.post(
        f"/courses/{course_id}/enrollments", json={"user_id": "prof-2"}
    )

    assert response.status_code == 400


async def test_a_professor_cannot_touch_another_professors_roster(client, people, auth):
    course_id = await _make_course(client, professor_id="prof-1")

    auth["user"] = _payload("prof-2", "professor")

    enroll = await client.post(
        f"/courses/{course_id}/enrollments", json={"user_id": "stu-1"}
    )
    roster = await client.get(f"/courses/{course_id}/roster")

    assert enroll.status_code == 403
    assert roster.status_code == 403


async def test_unenroll_removes_the_student(client, people, auth):
    course_id = await _make_course(client)
    auth["user"] = _payload("prof-1", "professor")
    await client.post(f"/courses/{course_id}/enrollments", json={"user_id": "stu-1"})

    removed = await client.delete(f"/courses/{course_id}/enrollments/stu-1")
    assert removed.status_code == 200

    assert (await client.get(f"/courses/{course_id}/roster")).json() == []

    # Removing someone who isn't on the roster is a 404, not a silent success.
    again = await client.delete(f"/courses/{course_id}/enrollments/stu-1")
    assert again.status_code == 404


# --- Bulk allocation ----------------------------------------------------------


async def test_bulk_allocation_funds_every_student_and_debits_the_professor_once(
    client, people, auth, db_session
):
    course_id = await _make_course(client)
    await add_credits(db_session, "prof-1", 100.0, "admin_grant")

    auth["user"] = _payload("prof-1", "professor")
    for student in ("stu-1", "stu-2", "stu-3"):
        await client.post(f"/courses/{course_id}/enrollments", json={"user_id": student})

    response = await client.post(f"/courses/{course_id}/allocate", json={"amount": 10})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["students"] == 3
    assert body["total"] == 30

    # Every student funded, professor debited exactly the total.
    for student in ("stu-1", "stu-2", "stu-3"):
        assert await get_balance(db_session, student) == 10.0
    assert await get_balance(db_session, "prof-1") == 70.0


async def test_underfunded_bulk_allocation_funds_nobody(client, people, auth, db_session):
    """All-or-nothing. A partial allocation would be worse than none at all."""
    course_id = await _make_course(client)
    await add_credits(db_session, "prof-1", 25.0, "admin_grant")

    auth["user"] = _payload("prof-1", "professor")
    for student in ("stu-1", "stu-2", "stu-3"):
        await client.post(f"/courses/{course_id}/enrollments", json={"user_id": student})

    # 3 students × 10 = 30 needed, only 25 available.
    response = await client.post(f"/courses/{course_id}/allocate", json={"amount": 10})

    assert response.status_code == 402
    for student in ("stu-1", "stu-2", "stu-3"):
        assert await get_balance(db_session, student) == 0.0
    assert await get_balance(db_session, "prof-1") == 25.0  # untouched


async def test_bulk_allocation_on_an_empty_roster_is_rejected(client, people, auth, db_session):
    course_id = await _make_course(client)
    await add_credits(db_session, "prof-1", 100.0, "admin_grant")
    auth["user"] = _payload("prof-1", "professor")

    response = await client.post(f"/courses/{course_id}/allocate", json={"amount": 10})

    assert response.status_code == 400
    assert await get_balance(db_session, "prof-1") == 100.0


async def test_repeated_bulk_allocations_accumulate_correctly(
    client, people, auth, db_session
):
    """Guards the balance-read ambiguity: consecutive allocations in the same
    course must each see the previous one's balance, not a stale row."""
    course_id = await _make_course(client)
    await add_credits(db_session, "prof-1", 100.0, "admin_grant")

    auth["user"] = _payload("prof-1", "professor")
    for student in ("stu-1", "stu-2"):
        await client.post(f"/courses/{course_id}/enrollments", json={"user_id": student})

    first = await client.post(f"/courses/{course_id}/allocate", json={"amount": 10})
    second = await client.post(f"/courses/{course_id}/allocate", json={"amount": 5})

    assert first.status_code == 200
    assert second.status_code == 200

    for student in ("stu-1", "stu-2"):
        assert await get_balance(db_session, student) == 15.0
    assert await get_balance(db_session, "prof-1") == 70.0  # 100 - 20 - 10
