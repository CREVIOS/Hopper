from pathlib import Path
import sys
from types import SimpleNamespace

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
from app.models import AuditLog, PodSession, User
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
        sub="admin-1",
        email="admin@cs.du.ac.bd",
        name="Admin",
        role="admin",
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
async def test_admin_stats_and_active_vms_reflect_database_state(client, db_session):
    db_session.add_all(
        [
            User(id="admin-1", email="admin@cs.du.ac.bd", name="Admin", role="admin"),
            User(id="student-1", email="student1@cs.du.ac.bd", name="Student One", role="student"),
            User(id="student-2", email="student2@cs.du.ac.bd", name="Student Two", role="student"),
            PodSession(
                id="pod-1",
                user_id="student-1",
                plan="small",
                image="hopper/vm-ubuntu:22.04",
                cpu="1",
                memory="2Gi",
                namespace="hopper",
                pod_name="vm-pod-1",
                state="running",
            ),
            PodSession(
                id="pod-2",
                user_id="student-2",
                plan="medium",
                image="hopper/vm-python-ml:22.04",
                cpu="2",
                memory="4Gi",
                namespace="hopper",
                pod_name="vm-pod-2",
                state="terminated",
            ),
        ]
    )
    await db_session.commit()

    stats_response = await client.get("/admin/stats")
    active_response = await client.get("/admin/active-vms")

    assert stats_response.status_code == 200
    assert stats_response.json() == {
        "total_users": 3,
        "active_vms": 1,
        "total_vms_created": 2,
    }

    assert active_response.status_code == 200
    active = active_response.json()
    assert len(active) == 1
    assert active[0]["id"] == "pod-1"
    assert active[0]["user_email"] == "student1@cs.du.ac.bd"


@pytest.mark.asyncio
async def test_admin_can_approve_teacher_request(client, db_session, monkeypatch):
    db_session.add_all(
        [
            User(id="admin-1", email="admin@cs.du.ac.bd", name="Admin", role="admin"),
            User(
                id="teacher-1",
                email="teacher1@cs.du.ac.bd",
                name="Teacher One",
                role="student",
                pending_teacher=True,
            ),
        ]
    )
    await db_session.commit()

    assigned_roles = []
    logged_out = []

    async def fake_set_user_role(user_id, role):
        assigned_roles.append((user_id, role))

    async def fake_logout_user(user_id):
        logged_out.append(user_id)

    monkeypatch.setattr("app.routers.admin.keycloak_admin.set_user_role", fake_set_user_role)
    monkeypatch.setattr("app.routers.admin.keycloak_admin.logout_user", fake_logout_user)

    response = await client.post("/admin/teacher-requests/teacher-1/approve")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "user_id": "teacher-1", "role": "professor"}
    assert assigned_roles == [("teacher-1", "professor")]
    assert logged_out == ["teacher-1"]


@pytest.mark.asyncio
async def test_admin_lists_users_teacher_requests_and_courses(client, db_session):
    db_session.add_all(
        [
            User(id="student-1", email="student1@cs.du.ac.bd", name="Student One", role="student"),
            User(
                id="teacher-1",
                email="teacher1@cs.du.ac.bd",
                name="Teacher One",
                role="student",
                pending_teacher=True,
            ),
        ]
    )
    await db_session.commit()

    users_response = await client.get("/admin/users")
    requests_response = await client.get("/admin/teacher-requests")
    courses_response = await client.get("/admin/courses")

    assert users_response.status_code == 200
    assert len(users_response.json()) == 2
    assert requests_response.status_code == 200
    assert requests_response.json()[0]["id"] == "teacher-1"
    assert courses_response.status_code == 200
    assert courses_response.json() == []


@pytest.mark.asyncio
async def test_admin_can_reject_teacher_request(client, db_session):
    db_session.add(
        User(
            id="teacher-1",
            email="teacher1@cs.du.ac.bd",
            name="Teacher One",
            role="student",
            pending_teacher=True,
        )
    )
    await db_session.commit()

    response = await client.post("/admin/teacher-requests/teacher-1/reject")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "user_id": "teacher-1", "role": "student"}

    user = await db_session.get(User, "teacher-1")
    assert user is not None
    assert user.pending_teacher is False


@pytest.mark.asyncio
async def test_admin_nodes_and_audit_logs_use_mocked_dependencies(client, db_session, monkeypatch):
    db_session.add(
        AuditLog(
            id="audit-1",
            user_id="admin-1",
            action="login",
            resource_type="auth",
            resource_id="admin-1",
            ip_address="127.0.0.1",
            status_code=200,
        )
    )
    await db_session.commit()

    async def fake_list_nodes():
        return [
            SimpleNamespace(
                name="worker-1",
                cpu_capacity="8",
                memory_capacity="16Gi",
                cpu_allocatable="7",
                memory_allocatable="14Gi",
                pod_count=3,
                ready=True,
            )
        ]

    monkeypatch.setattr("app.routers.admin.orchestrator_client.list_nodes", fake_list_nodes)

    nodes_response = await client.get("/admin/nodes")
    audit_response = await client.get("/admin/audit-logs")

    assert nodes_response.status_code == 200
    assert nodes_response.json() == [
        {
            "name": "worker-1",
            "cpu_capacity": "8",
            "memory_capacity": "16Gi",
            "cpu_allocatable": "7",
            "memory_allocatable": "14Gi",
            "pod_count": 3,
            "ready": True,
        }
    ]

    assert audit_response.status_code == 200
    logs = audit_response.json()
    assert len(logs) == 1
    assert logs[0]["action"] == "login"


@pytest.mark.asyncio
async def test_admin_can_change_user_role(client, db_session, monkeypatch):
    db_session.add_all(
        [
            User(id="admin-1", email="admin@cs.du.ac.bd", name="Admin", role="admin"),
            User(id="student-1", email="student1@cs.du.ac.bd", name="Student One", role="student"),
        ]
    )
    await db_session.commit()

    role_changes = []
    logout_calls = []

    async def fake_set_user_role(user_id, role):
        role_changes.append((user_id, role))

    async def fake_logout_user(user_id):
        logout_calls.append(user_id)

    monkeypatch.setattr("app.routers.admin.keycloak_admin.set_user_role", fake_set_user_role)
    monkeypatch.setattr("app.routers.admin.keycloak_admin.logout_user", fake_logout_user)

    response = await client.patch("/admin/users/student-1/role", json={"role": "professor"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "user_id": "student-1",
        "old_role": "student",
        "new_role": "professor",
    }
    assert role_changes == [("student-1", "professor")]
    assert logout_calls == ["student-1"]


@pytest.mark.asyncio
async def test_professor_can_access_read_only_admin_endpoints_but_not_mutations(
    client,
    db_session,
    current_user_payload,
):
    # Professors can reach read-only admin endpoints only if the router allows it,
    # but mutating admin actions must still be rejected.
    current_user_payload.sub = "prof-1"
    current_user_payload.role = "professor"
    current_user_payload.email = "prof@cs.du.ac.bd"
    db_session.add(User(id="prof-1", email="prof@cs.du.ac.bd", name="Professor", role="professor"))
    await db_session.commit()

    stats_response = await client.get("/admin/stats")
    change_role_response = await client.patch("/admin/users/prof-1/role", json={"role": "student"})

    assert stats_response.status_code == 403
    assert stats_response.json() == {"detail": "Admin access required"}
    assert change_role_response.status_code == 403
    assert change_role_response.json() == {"detail": "Admin access required"}


# --- VM plan catalogue CRUD ---------------------------------------------------

async def _delete_plan_rows(db_session, *names):
    """Hard-delete throwaway plans so CRUD tests don't leak into the seeded set."""
    from sqlalchemy import delete as sa_delete

    from app.models import VmPlanRow

    for name in names:
        await db_session.execute(sa_delete(VmPlanRow).where(VmPlanRow.name == name))
    await db_session.commit()


@pytest.mark.asyncio
async def test_admin_list_plans_returns_seeded_defaults(client):
    response = await client.get("/admin/plans")

    assert response.status_code == 200
    by_name = {p["name"]: p for p in response.json()}
    assert {"small", "medium", "large"} <= set(by_name)
    assert by_name["small"]["credits_per_hour"] == 1.0
    assert by_name["medium"]["credits_per_hour"] == 2.0
    assert by_name["large"]["credits_per_hour"] == 4.0
    assert by_name["large"]["workspace_gb"] == 100
    assert by_name["small"]["is_active"] is True


@pytest.mark.asyncio
async def test_admin_plan_create_update_soft_delete_lifecycle(client, db_session):
    try:
        # Create
        create = await client.post("/admin/plans", json={
            "name": "test-xl", "display_name": "Test XL", "cpu": "8", "memory": "16Gi",
            "disk": "40Gi", "credits_per_hour": 8.0, "workspace_gb": 200,
        })
        assert create.status_code == 201
        assert create.json()["credits_per_hour"] == 8.0

        # Duplicate → 409
        dup = await client.post("/admin/plans", json={
            "name": "test-xl", "display_name": "dup", "cpu": "1", "memory": "1Gi",
            "disk": "1Gi", "credits_per_hour": 1.0, "workspace_gb": 1,
        })
        assert dup.status_code == 409

        # Update price only
        upd = await client.put("/admin/plans/test-xl", json={"credits_per_hour": 9.5})
        assert upd.status_code == 200
        assert upd.json()["credits_per_hour"] == 9.5
        assert upd.json()["cpu"] == "8"  # unchanged field preserved

        # Soft-delete → hidden from the student catalogue but row remains inactive
        delete = await client.delete("/admin/plans/test-xl")
        assert delete.status_code == 200

        admin_list = {p["name"]: p for p in (await client.get("/admin/plans")).json()}
        assert admin_list["test-xl"]["is_active"] is False

        student_catalog = (await client.get("/pods/plans")).json()
        assert "test-xl" not in student_catalog  # inactive plans excluded
    finally:
        await _delete_plan_rows(db_session, "test-xl")


@pytest.mark.asyncio
async def test_admin_update_missing_plan_returns_404(client):
    response = await client.put("/admin/plans/does-not-exist", json={"credits_per_hour": 2.0})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_plans_forbidden_for_non_admin(client, db_session, current_user_payload):
    current_user_payload.sub = "prof-1"
    current_user_payload.role = "professor"
    current_user_payload.email = "prof@cs.du.ac.bd"

    listing = await client.get("/admin/plans")
    creating = await client.post("/admin/plans", json={
        "name": "sneaky", "display_name": "x", "cpu": "1", "memory": "1Gi",
        "disk": "1Gi", "credits_per_hour": 1.0, "workspace_gb": 1,
    })

    assert listing.status_code == 403
    assert creating.status_code == 403
