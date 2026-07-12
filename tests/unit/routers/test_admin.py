import pytest
from fastapi import HTTPException

from app.models.session import PodSession
from app.models.user import User
from app.routers.admin import (
    _require_admin,
    approve_teacher,
    change_user_role,
    get_stats,
    list_active_vms,
    list_courses,
    list_nodes,
    reject_teacher,
)
from app.schemas.user import TokenPayload


def _payload(role: str) -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="Test User",
        role=role,
        exp=1234567890,
    )


def test_require_admin_allows_admin():
    assert _require_admin(_payload("admin")) is None


def test_require_admin_rejects_professor_and_student():
    # Admin endpoints are admin-only; professors use the Teaching console
    # (RBAC tightening, commit a6a9c48), so professors are rejected here too.
    for role in ("professor", "student"):
        with pytest.raises(HTTPException) as exc_info:
            _require_admin(_payload(role))

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Admin access required"


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, *, user=None, execute_rows=None, scalar_values=None):
        self.user = user
        self.execute_rows = list(execute_rows or [])
        self.scalar_values = list(scalar_values or [])
        self.added = []
        self.committed = False

    async def get(self, model, user_id):
        return self.user

    async def execute(self, stmt):
        return FakeExecuteResult(self.execute_rows.pop(0))

    async def scalar(self, stmt):
        return self.scalar_values.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


async def test_list_courses_rejects_non_admin():
    with pytest.raises(HTTPException) as exc:
        await list_courses(current_user=_payload("professor"), db=None)

    assert exc.value.status_code == 403


async def test_list_nodes_formats_orchestrator_nodes(monkeypatch):
    node = type(
        "Node",
        (),
        {
            "name": "node-1",
            "cpu_capacity": "8",
            "memory_capacity": "32Gi",
            "cpu_allocatable": "6",
            "memory_allocatable": "24Gi",
            "pod_count": 4,
            "ready": True,
        },
    )()

    async def fake_list_nodes():
        return [node]

    monkeypatch.setattr("app.routers.admin.orchestrator_client.list_nodes", fake_list_nodes)

    result = await list_nodes(current_user=_payload("admin"))

    assert result == [
        {
            "name": "node-1",
            "cpu_capacity": "8",
            "memory_capacity": "32Gi",
            "cpu_allocatable": "6",
            "memory_allocatable": "24Gi",
            "pod_count": 4,
            "ready": True,
        }
    ]


async def test_get_stats_uses_zero_defaults():
    db = FakeDB(scalar_values=[None, None, None])

    result = await get_stats(current_user=_payload("admin"), db=db)

    assert result == {"total_users": 0, "active_vms": 0, "total_vms_created": 0}


async def test_list_active_vms_formats_rows():
    session = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="hopper/vm-ubuntu:22.04",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="running",
        started_at=None,
        updated_at=None,
    )
    db = FakeDB(execute_rows=[[(session, "user@example.com", "Test User")]])

    result = await list_active_vms(current_user=_payload("admin"), db=db)

    assert result[0]["id"] == "pod-1"
    assert result[0]["user_email"] == "user@example.com"


async def test_approve_teacher_updates_role_and_pending_flag(monkeypatch):
    user = User(
        id="user-2",
        email="teacher@example.com",
        name="Teacher",
        role="student",
        pending_teacher=True,
    )
    db = FakeDB(user=user)
    calls = {}

    async def fake_set_user_role(user_id, role):
        calls["set_role"] = (user_id, role)

    async def fake_logout_user(user_id):
        calls["logout"] = user_id

    monkeypatch.setattr("app.routers.admin.keycloak_admin.set_user_role", fake_set_user_role)
    monkeypatch.setattr("app.routers.admin.keycloak_admin.logout_user", fake_logout_user)

    result = await approve_teacher("user-2", current_user=_payload("admin"), db=db)

    assert result == {"status": "ok", "user_id": "user-2", "role": "professor"}
    assert user.role == "professor"
    assert user.pending_teacher is False
    assert db.committed is True
    assert calls["set_role"] == ("user-2", "professor")
    assert calls["logout"] == "user-2"


async def test_reject_teacher_clears_pending_flag():
    user = User(
        id="user-2",
        email="teacher@example.com",
        name="Teacher",
        role="student",
        pending_teacher=True,
    )
    db = FakeDB(user=user)

    result = await reject_teacher("user-2", current_user=_payload("admin"), db=db)

    assert result == {"status": "ok", "user_id": "user-2", "role": "student"}
    assert user.pending_teacher is False
    assert db.committed is True


async def test_change_user_role_rejects_invalid_role():
    db = FakeDB(user=User(id="user-2", email="u@example.com", name="U", role="student"))

    with pytest.raises(HTTPException) as exc_info:
        await change_user_role("user-2", type("Body", (), {"role": "ta"})(), current_user=_payload("admin"), db=db)

    assert exc_info.value.status_code == 400


async def test_change_user_role_returns_noop_when_role_unchanged():
    db = FakeDB(user=User(id="user-2", email="u@example.com", name="U", role="student"))

    result = await change_user_role(
        "user-2",
        type("Body", (), {"role": "student"})(),
        current_user=_payload("admin"),
        db=db,
    )

    assert result == {"status": "noop", "user_id": "user-2", "role": "student"}


async def test_change_user_role_updates_user_role(monkeypatch):
    user = User(id="user-2", email="u@example.com", name="U", role="student")
    db = FakeDB(user=user)
    calls = {}

    async def fake_set_user_role(user_id, role):
        calls["set_role"] = (user_id, role)

    async def fake_logout_user(user_id):
        calls["logout"] = user_id

    monkeypatch.setattr("app.routers.admin.keycloak_admin.set_user_role", fake_set_user_role)
    monkeypatch.setattr("app.routers.admin.keycloak_admin.logout_user", fake_logout_user)

    result = await change_user_role(
        "user-2",
        type("Body", (), {"role": "admin"})(),
        current_user=_payload("admin"),
        db=db,
    )

    assert result == {"status": "ok", "user_id": "user-2", "old_role": "student", "new_role": "admin"}
    assert user.role == "admin"
    assert db.committed is True


def _fake_audit_log(log_id="a1", action="login"):
    from datetime import datetime
    from types import SimpleNamespace

    return SimpleNamespace(
        id=log_id, user_id="user-1", action=action, resource_type="user",
        resource_id="user-1", ip_address="1.2.3.4", status_code=200,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )


def _fake_request():
    from types import SimpleNamespace

    return SimpleNamespace(client=SimpleNamespace(host="9.9.9.9"))


async def test_get_audit_logs_accepts_action_and_user_filters():
    from app.routers.admin import get_audit_logs

    db = FakeDB(execute_rows=[[_fake_audit_log("a1", action="login")]])
    result = await get_audit_logs(
        current_user=_payload("admin"), db=db, action="login", user_id="user-1"
    )

    assert result[0]["action"] == "login"


async def test_export_audit_logs_json_records_export_event():
    from app.routers.admin import export_audit_logs

    db = FakeDB(execute_rows=[[_fake_audit_log("a1"), _fake_audit_log("a2")]])
    result = await export_audit_logs(
        request=_fake_request(), current_user=_payload("admin"), db=db, from_=None, to=None
    )

    assert [r["id"] for r in result] == ["a1", "a2"]
    assert any(getattr(o, "action", None) == "audit.export" for o in db.added)
    assert db.committed is True


async def test_export_audit_logs_csv_returns_csv_body():
    from app.routers.admin import export_audit_logs

    db = FakeDB(execute_rows=[[_fake_audit_log("a1")]])
    resp = await export_audit_logs(
        request=_fake_request(), current_user=_payload("admin"), db=db, format="csv", from_=None, to=None
    )

    assert resp.media_type == "text/csv"
    body = resp.body.decode() if isinstance(resp.body, bytes) else resp.body
    assert "action" in body and "a1" in body


async def test_export_audit_logs_rejects_bad_format():
    from app.routers.admin import export_audit_logs

    with pytest.raises(HTTPException) as exc:
        await export_audit_logs(
            request=_fake_request(), current_user=_payload("admin"), db=FakeDB(), format="xml"
        )

    assert exc.value.status_code == 400
