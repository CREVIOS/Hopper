from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.session import PodSession
from app.models.user import User
from app.routers.admin import (
    _require_admin,
    admin_create_image,
    admin_create_plan,
    admin_delete_image,
    admin_delete_plan,
    admin_list_images,
    admin_list_plans,
    admin_update_image,
    admin_update_plan,
    approve_teacher,
    change_user_role,
    get_stats,
    list_active_vms,
    list_courses,
    list_nodes,
    reject_teacher,
)
from app.schemas.image import ImageCreateRequest, ImageUpdateRequest
from app.schemas.plan import PlanCreateRequest, PlanUpdateRequest
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


@pytest.mark.parametrize("role", ["student", "professor"])
def test_require_admin_rejects_non_admin_roles(role):
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


async def test_list_courses_returns_empty_list_for_admin():
    result = await list_courses(current_user=_payload("admin"))

    assert result == []


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


# --- VM plan catalogue (admin CRUD) -----------------------------------------


def _plan_row(name="small", **over):
    base = dict(
        name=name,
        display_name=name.title(),
        cpu="1",
        memory="2Gi",
        disk="5Gi",
        credits_per_hour=1.0,
        workspace_gb=20,
        is_active=True,
    )
    base.update(over)
    return SimpleNamespace(**base)


async def test_admin_list_plans_includes_inactive(monkeypatch):
    async def fake_list_plans(db, *, include_inactive=False):
        assert include_inactive is True
        return [_plan_row("small"), _plan_row("large", is_active=False)]

    monkeypatch.setattr("app.routers.admin.plan_service.list_plans", fake_list_plans)

    result = await admin_list_plans(current_user=_payload("admin"), db=FakeDB())

    assert [p.name for p in result] == ["small", "large"]
    assert result[1].is_active is False


async def test_admin_create_plan_conflicts_when_exists(monkeypatch):
    async def fake_get_plan(db, name, *, active_only=False):
        return _plan_row(name)

    monkeypatch.setattr("app.routers.admin.plan_service.get_plan", fake_get_plan)

    body = PlanCreateRequest(
        name="small", display_name="Small", cpu="1", memory="2Gi",
        disk="5Gi", credits_per_hour=1.0, workspace_gb=20,
    )
    with pytest.raises(HTTPException) as exc_info:
        await admin_create_plan(body, current_user=_payload("admin"), db=FakeDB())

    assert exc_info.value.status_code == 409


async def test_admin_create_plan_creates_new(monkeypatch):
    created = {}

    async def fake_get_plan(db, name, *, active_only=False):
        return None

    async def fake_create_plan(db, **fields):
        created.update(fields)
        return _plan_row(**fields)

    monkeypatch.setattr("app.routers.admin.plan_service.get_plan", fake_get_plan)
    monkeypatch.setattr("app.routers.admin.plan_service.create_plan", fake_create_plan)

    body = PlanCreateRequest(
        name="gpu", display_name="GPU", cpu="8", memory="32Gi",
        disk="100Gi", credits_per_hour=10.0, workspace_gb=200,
    )
    result = await admin_create_plan(body, current_user=_payload("admin"), db=FakeDB())

    assert result.name == "gpu"
    assert created["credits_per_hour"] == 10.0


async def test_admin_update_plan_404_when_missing(monkeypatch):
    async def fake_get_plan(db, name, *, active_only=False):
        return None

    monkeypatch.setattr("app.routers.admin.plan_service.get_plan", fake_get_plan)

    with pytest.raises(HTTPException) as exc_info:
        await admin_update_plan(
            "ghost", PlanUpdateRequest(credits_per_hour=2.0),
            current_user=_payload("admin"), db=FakeDB(),
        )

    assert exc_info.value.status_code == 404


async def test_admin_update_plan_applies_only_provided_fields(monkeypatch):
    plan = _plan_row("small")

    async def fake_get_plan(db, name, *, active_only=False):
        return plan

    async def fake_update_plan(db, existing, fields):
        # router must pass exclude_unset so untouched fields aren't overwritten
        assert fields == {"credits_per_hour": 3.0}
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing

    monkeypatch.setattr("app.routers.admin.plan_service.get_plan", fake_get_plan)
    monkeypatch.setattr("app.routers.admin.plan_service.update_plan", fake_update_plan)

    result = await admin_update_plan(
        "small", PlanUpdateRequest(credits_per_hour=3.0),
        current_user=_payload("admin"), db=FakeDB(),
    )

    assert result.credits_per_hour == 3.0
    assert result.cpu == "1"  # unchanged


async def test_admin_delete_plan_404_when_missing(monkeypatch):
    async def fake_get_plan(db, name, *, active_only=False):
        return None

    monkeypatch.setattr("app.routers.admin.plan_service.get_plan", fake_get_plan)

    with pytest.raises(HTTPException) as exc_info:
        await admin_delete_plan("ghost", current_user=_payload("admin"), db=FakeDB())

    assert exc_info.value.status_code == 404


async def test_admin_delete_plan_deactivates(monkeypatch):
    plan = _plan_row("small")
    calls = {}

    async def fake_get_plan(db, name, *, active_only=False):
        return plan

    async def fake_deactivate_plan(db, existing):
        calls["deactivated"] = existing.name
        existing.is_active = False
        return existing

    monkeypatch.setattr("app.routers.admin.plan_service.get_plan", fake_get_plan)
    monkeypatch.setattr("app.routers.admin.plan_service.deactivate_plan", fake_deactivate_plan)

    result = await admin_delete_plan("small", current_user=_payload("admin"), db=FakeDB())

    assert result == {"message": "deactivated", "name": "small"}
    assert calls["deactivated"] == "small"


# --- VM image / template catalogue (admin CRUD) -----------------------------


def _image_row(template="ubuntu", **over):
    base = dict(
        template=template,
        display_name=template.title(),
        image=f"hopper/vm-{template}:22.04",
        description="",
        is_active=True,
        is_default=template == "ubuntu",
    )
    base.update(over)
    return SimpleNamespace(**base)


async def test_admin_list_images_includes_inactive(monkeypatch):
    async def fake_list_images(db, *, include_inactive=False):
        assert include_inactive is True
        return [_image_row("ubuntu"), _image_row("rust", is_active=False)]

    monkeypatch.setattr("app.routers.admin.image_service.list_images", fake_list_images)

    result = await admin_list_images(current_user=_payload("admin"), db=FakeDB())

    assert [i.template for i in result] == ["ubuntu", "rust"]
    assert result[1].is_active is False


async def test_admin_create_image_conflicts_when_exists(monkeypatch):
    async def fake_get_image(db, template, *, active_only=False):
        return _image_row(template)

    monkeypatch.setattr("app.routers.admin.image_service.get_image", fake_get_image)

    body = ImageCreateRequest(template="ubuntu", display_name="Ubuntu", image="hopper/vm-ubuntu:22.04")
    with pytest.raises(HTTPException) as exc_info:
        await admin_create_image(body, current_user=_payload("admin"), db=FakeDB())

    assert exc_info.value.status_code == 409


async def test_admin_create_image_creates_new(monkeypatch):
    created = {}

    async def fake_get_image(db, template, *, active_only=False):
        return None

    async def fake_create_image(db, **fields):
        created.update(fields)
        return _image_row(**fields)

    monkeypatch.setattr("app.routers.admin.image_service.get_image", fake_get_image)
    monkeypatch.setattr("app.routers.admin.image_service.create_image", fake_create_image)

    body = ImageCreateRequest(
        template="rust", display_name="Rust", image="hopper/vm-rust:1.0",
        description="Cargo", is_default=True,
    )
    result = await admin_create_image(body, current_user=_payload("admin"), db=FakeDB())

    assert result.template == "rust"
    assert created["image"] == "hopper/vm-rust:1.0"
    assert created["is_default"] is True


async def test_admin_update_image_404_when_missing(monkeypatch):
    async def fake_get_image(db, template, *, active_only=False):
        return None

    monkeypatch.setattr("app.routers.admin.image_service.get_image", fake_get_image)

    with pytest.raises(HTTPException) as exc_info:
        await admin_update_image(
            "ghost", ImageUpdateRequest(image="x/y:1"),
            current_user=_payload("admin"), db=FakeDB(),
        )

    assert exc_info.value.status_code == 404


async def test_admin_update_image_applies_only_provided_fields(monkeypatch):
    row = _image_row("ubuntu")

    async def fake_get_image(db, template, *, active_only=False):
        return row

    async def fake_update_image(db, existing, fields):
        assert fields == {"description": "Now with docs"}
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing

    monkeypatch.setattr("app.routers.admin.image_service.get_image", fake_get_image)
    monkeypatch.setattr("app.routers.admin.image_service.update_image", fake_update_image)

    result = await admin_update_image(
        "ubuntu", ImageUpdateRequest(description="Now with docs"),
        current_user=_payload("admin"), db=FakeDB(),
    )

    assert result.description == "Now with docs"
    assert result.image == "hopper/vm-ubuntu:22.04"  # unchanged


async def test_admin_delete_image_404_when_missing(monkeypatch):
    async def fake_get_image(db, template, *, active_only=False):
        return None

    monkeypatch.setattr("app.routers.admin.image_service.get_image", fake_get_image)

    with pytest.raises(HTTPException) as exc_info:
        await admin_delete_image("ghost", current_user=_payload("admin"), db=FakeDB())

    assert exc_info.value.status_code == 404


async def test_admin_delete_image_deactivates(monkeypatch):
    row = _image_row("rust")
    calls = {}

    async def fake_get_image(db, template, *, active_only=False):
        return row

    async def fake_deactivate_image(db, existing):
        calls["deactivated"] = existing.template
        existing.is_active = False
        return existing

    monkeypatch.setattr("app.routers.admin.image_service.get_image", fake_get_image)
    monkeypatch.setattr("app.routers.admin.image_service.deactivate_image", fake_deactivate_image)

    result = await admin_delete_image("rust", current_user=_payload("admin"), db=FakeDB())

    assert result == {"message": "deactivated", "template": "rust"}
    assert calls["deactivated"] == "rust"
