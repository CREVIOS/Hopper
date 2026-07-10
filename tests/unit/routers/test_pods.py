from datetime import datetime

import pytest
from fastapi import HTTPException

from app.models.session import PodSession
from app.routers.pods import (
    _session_to_response,
    create_pod,
    get_pod,
    list_plans,
    list_pods,
    terminate_pod,
)
from app.schemas.pod import CreatePodRequest, VmPlan
from app.schemas.user import TokenPayload


def _payload() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="Test User",
        role="student",
        exp=1234567890,
    )


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        if isinstance(self._rows, list):
            return self._rows[0] if self._rows else None
        return self._rows


class FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one_or_none(self):
        if isinstance(self._rows, list):
            return self._rows[0] if self._rows else None
        return self._rows


class FakeDB:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])
        self.added = []
        self.commits = 0
        self.refreshed = []

    async def execute(self, stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return FakeExecuteResult(self.execute_results.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


def test_session_to_response_hides_connection_details_for_non_running_pod():
    session = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="hopper/vm-ubuntu:22.04",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="terminated",
        ssh_port=30022,
        vscode_port=30080,
        ssh_password="secret",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 5, 0),
    )

    response = _session_to_response(session)

    assert response.ssh_port is None
    assert response.vscode_port is None
    assert response.ssh_password is None


def test_session_to_response_keeps_connection_details_for_running_pod():
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
        ssh_port=30022,
        vscode_port=30080,
        ssh_password="secret",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 5, 0),
    )

    response = _session_to_response(session)

    assert response.ssh_port == 30022
    assert response.vscode_port == 30080
    assert response.ssh_password == "secret"


async def test_list_plans_returns_all_vm_plans():
    result = await list_plans()

    assert set(result) == {"small", "medium", "large"}
    assert result["small"]["credits_per_hour"] == 1.0


async def test_list_pods_returns_sessions_for_current_user():
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
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 5, 0),
    )
    db = FakeDB(execute_results=[[session]])

    result = await list_pods(current_user=_payload(), db=db)

    assert len(result) == 1
    assert result[0].id == "pod-1"


async def test_create_pod_rejects_insufficient_credits(monkeypatch):
    async def fake_get_balance(db, user_id):
        return 0.0

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)

    with pytest.raises(HTTPException) as exc_info:
        await create_pod(
            request=None,
            response=None,
            body=CreatePodRequest(plan=VmPlan.SMALL),
            current_user=_payload(),
            db=FakeDB(),
        )

    assert exc_info.value.status_code == 402
    assert "Insufficient credits" in exc_info.value.detail


async def test_create_pod_rejects_more_than_three_active_pods(monkeypatch):
    async def fake_get_balance(db, user_id):
        return 100.0

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)
    db = FakeDB(execute_results=[[object(), object(), object()]])

    with pytest.raises(HTTPException) as exc_info:
        await create_pod(
            request=None,
            response=None,
            body=CreatePodRequest(plan=VmPlan.SMALL),
            current_user=_payload(),
            db=db,
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "Maximum 3 concurrent VMs allowed"


async def test_create_pod_updates_session_from_orchestrator_response(monkeypatch):
    async def fake_get_balance(db, user_id):
        return 100.0

    class FakeOrchestratorResponse:
        id = "vm-real-name"
        state = "running"
        ssh_port = 30022
        vscode_port = 30080
        ssh_password = "secret"

    async def fake_create_pod(**kwargs):
        return FakeOrchestratorResponse()

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)
    monkeypatch.setattr("app.routers.pods.orchestrator_client.create_pod", fake_create_pod)

    db = FakeDB(execute_results=[[]])

    result = await create_pod(
        request=None,
        response=None,
        body=CreatePodRequest(plan=VmPlan.SMALL),
        current_user=_payload(),
        db=db,
    )

    assert db.commits == 2
    assert result.state.value == "running"
    assert result.ssh_port == 30022
    assert db.added[0].pod_name == "vm-real-name"


async def test_create_pod_marks_session_failed_when_orchestrator_raises(monkeypatch):
    async def fake_get_balance(db, user_id):
        return 100.0

    async def fake_create_pod(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)
    monkeypatch.setattr("app.routers.pods.orchestrator_client.create_pod", fake_create_pod)

    db = FakeDB(execute_results=[[]])

    result = await create_pod(
        request=None,
        response=None,
        body=CreatePodRequest(plan=VmPlan.SMALL),
        current_user=_payload(),
        db=db,
    )

    assert result.state.value == "failed"
    assert db.added[0].state == "failed"


async def test_get_pod_rejects_missing_pod():
    db = FakeDB(execute_results=[None])

    with pytest.raises(HTTPException) as exc_info:
        await get_pod("missing", current_user=_payload(), db=db)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "VM not found"


async def test_get_pod_rejects_other_users_pod():
    session = PodSession(
        id="pod-1",
        user_id="other-user",
        plan="small",
        image="hopper/vm-ubuntu:22.04",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="running",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 5, 0),
    )
    db = FakeDB(execute_results=[session])

    with pytest.raises(HTTPException) as exc_info:
        await get_pod("pod-1", current_user=_payload(), db=db)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not your VM"


async def test_terminate_pod_sets_state_and_stops_port_forward(monkeypatch):
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
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 5, 0),
    )
    db = FakeDB(execute_results=[session])
    calls = {}

    async def fake_terminate_pod(pod_name):
        calls["terminated"] = pod_name

    async def fake_stop(pod_name):
        calls["stopped"] = pod_name

    monkeypatch.setattr("app.routers.pods.orchestrator_client.terminate_pod", fake_terminate_pod)
    monkeypatch.setattr("app.routers.pods.port_forward.stop", fake_stop)

    result = await terminate_pod("pod-1", current_user=_payload(), db=db)

    assert result == {"message": "terminated", "pod_id": "pod-1"}
    assert calls == {"terminated": "vm-pod-1", "stopped": "vm-pod-1"}
    assert session.state == "terminated"
    assert db.commits == 1


def _admin() -> TokenPayload:
    return TokenPayload(
        sub="admin-1", email="admin@example.com", name="Admin", role="admin", exp=1234567890,
    )


async def test_terminate_pod_admin_can_force_terminate_any_vm(monkeypatch):
    # FR-HC-20: an admin may terminate a VM they don't own (runaway/abuse).
    session = PodSession(
        id="pod-9", user_id="other-user", plan="small", image="hopper/vm-ubuntu:22.04",
        cpu="1", memory="2Gi", namespace="hopper", pod_name="vm-pod-9", state="running",
        started_at=datetime(2026, 1, 1, 12, 0, 0), updated_at=datetime(2026, 1, 1, 12, 5, 0),
    )
    db = FakeDB(execute_results=[session])
    calls = {}

    async def fake_terminate_pod(pod_name):
        calls["terminated"] = pod_name

    async def fake_stop(pod_name):
        calls["stopped"] = pod_name

    monkeypatch.setattr("app.routers.pods.orchestrator_client.terminate_pod", fake_terminate_pod)
    monkeypatch.setattr("app.routers.pods.port_forward.stop", fake_stop)

    result = await terminate_pod("pod-9", current_user=_admin(), db=db)

    assert result == {"message": "terminated", "pod_id": "pod-9"}
    assert session.state == "terminated"
    assert calls["terminated"] == "vm-pod-9"


async def test_terminate_pod_rejects_non_owner_non_admin():
    session = PodSession(
        id="pod-9", user_id="other-user", plan="small", image="hopper/vm-ubuntu:22.04",
        cpu="1", memory="2Gi", namespace="hopper", pod_name="vm-pod-9", state="running",
        started_at=datetime(2026, 1, 1, 12, 0, 0), updated_at=datetime(2026, 1, 1, 12, 5, 0),
    )
    db = FakeDB(execute_results=[session])

    with pytest.raises(HTTPException) as exc_info:
        await terminate_pod("pod-9", current_user=_payload(), db=db)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not your VM"
