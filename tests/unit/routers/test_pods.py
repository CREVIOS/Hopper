from datetime import datetime

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.models.session import PodSession
from app.routers.pods import (
    _safe_send,
    cancel_queue_entry,
    _session_to_response,
    create_pod,
    get_availability,
    get_pod,
    list_queue,
    list_plans,
    list_pods,
    terminate_pod,
    stream_metrics,
    vscode_proxy,
    vscode_ws_proxy,
    websocket_terminal,
)
from app.models.vm_queue_entry import VmQueueEntry
from app.schemas.pod import CreatePodRequest, VmPlan
from app.schemas.user import TokenPayload


@pytest.fixture(autouse=True)
def _no_cluster_capacity(monkeypatch):
    """Keep these router unit tests hermetic: create_pod's admission
    fast-path starts with a real gRPC ListNodes attempt (vm_scheduler.
    fetch_nodes). Force the fail-open path (None → synchronous create, the
    behavior these tests were written against). This also stops the real
    proto modules from being imported mid-suite, which would bypass the
    sys.modules fakes test_orchestrator_client.py installs.
    """

    async def fake_fetch_nodes(orch):
        return None

    monkeypatch.setattr("app.routers.pods.vm_scheduler.fetch_nodes", fake_fetch_nodes)

    # _reconcile_state shells `kubectl` (via _k8s_phase) to sync a session's
    # stored state with its real pod phase. There's no cluster in unit tests, so
    # kubectl exits non-zero and the pod reads as "gone" -> "terminated", which
    # would flip these tests' "running" fixtures and trip the proxy's 503 guard.
    # Return None = the documented "phase unreadable, leave the row" no-op, so a
    # session's fixture state stays authoritative (matches a healthy running pod,
    # which is what the proxy/terminal tests set up).
    async def fake_k8s_phase(pod_name, namespace):
        return None

    monkeypatch.setattr("app.routers.pods._k8s_phase", fake_k8s_phase)


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
        if getattr(obj, "started_at", None) is None:
            obj.started_at = datetime(2026, 1, 1, 12, 0, 0)
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime(2026, 1, 1, 12, 0, 0)
        self.refreshed.append(obj)


class FakeWebSocket:
    def __init__(self, *, cookies=None, headers=None, query=""):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.url = type("URL", (), {"query": query})()
        self.closed = []
        self.accepted = False
        self.sent_text = []
        self.sent_bytes = []

    async def close(self, code=None, reason=None):
        self.closed.append((code, reason))

    async def accept(self):
        self.accepted = True

    async def send_text(self, text):
        self.sent_text.append(text)

    async def send_bytes(self, data):
        self.sent_bytes.append(data)

    async def receive(self):
        return {"type": "websocket.disconnect"}

    async def receive_text(self):
        raise RuntimeError("closed")


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
        await create_pod.__wrapped__(
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
        await create_pod.__wrapped__(
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

    result = await create_pod.__wrapped__(
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

    result = await create_pod.__wrapped__(
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


async def test_stream_metrics_rejects_missing_or_foreign_pod():
    with pytest.raises(HTTPException) as exc_info:
        await stream_metrics("missing", current_user=_payload(), db=FakeDB(execute_results=[None]))

    assert exc_info.value.status_code == 404

    foreign = PodSession(
        id="pod-1",
        user_id="other-user",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="running",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    with pytest.raises(HTTPException) as exc_info:
        await stream_metrics("pod-1", current_user=_payload(), db=FakeDB(execute_results=[foreign]))

    assert exc_info.value.status_code == 404


def _request(method="GET", *, cookie=None, accept="application/json", path="/pods/pod-1/vscode/", query=""):
    headers = []
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    if accept:
        headers.append((b"accept", accept.encode()))
    if query:
        raw_path = f"{path}?{query}".encode()
    else:
        raw_path = path.encode()
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "raw_path": raw_path,
            "query_string": query.encode(),
            "headers": headers,
        }
    )


async def test_vscode_proxy_redirects_html_navigation_when_missing_session(monkeypatch):
    monkeypatch.setattr("app.routers.pods.settings.frontend_url", "http://frontend.test")

    response = await vscode_proxy("pod-1", "", _request(accept="text/html"), FakeDB())

    assert response.status_code == 302
    assert response.headers["location"].startswith("http://frontend.test/login?return_to=")


async def test_vscode_proxy_rejects_api_request_when_missing_session():
    with pytest.raises(HTTPException) as exc_info:
        await vscode_proxy("pod-1", "", _request(), FakeDB())

    assert exc_info.value.status_code == 401


async def test_vscode_proxy_rejects_missing_foreign_and_non_running_pods(monkeypatch):
    async def fake_verify_token(token):
        return _payload()

    monkeypatch.setattr("app.routers.pods.verify_token", fake_verify_token)

    with pytest.raises(HTTPException) as exc_info:
        await vscode_proxy("missing", "", _request(cookie="session_token=tok"), FakeDB(execute_results=[None]))
    assert exc_info.value.status_code == 404

    foreign = PodSession(
        id="pod-1",
        user_id="other-user",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="running",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    with pytest.raises(HTTPException) as exc_info:
        await vscode_proxy("pod-1", "", _request(cookie="session_token=tok"), FakeDB(execute_results=[foreign]))
    assert exc_info.value.status_code == 403

    starting = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="creating",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    with pytest.raises(HTTPException) as exc_info:
        await vscode_proxy("pod-1", "", _request(cookie="session_token=tok"), FakeDB(execute_results=[starting]))
    assert exc_info.value.status_code == 503
    assert exc_info.value.headers["Retry-After"] == "5"


async def test_vscode_proxy_returns_503_when_port_forward_unavailable(monkeypatch):
    async def fake_verify_token(token):
        return _payload()

    monkeypatch.setattr("app.routers.pods.verify_token", fake_verify_token)
    monkeypatch.setattr("app.routers.pods.port_forward.get_local_port", lambda pod_name: None)

    async def fail_start(pod_name, namespace):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routers.pods.port_forward.start", fail_start)
    session = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="running",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )

    with pytest.raises(HTTPException) as exc_info:
        await vscode_proxy("pod-1", "index.html", _request(cookie="session_token=tok"), FakeDB(execute_results=[session]))

    assert exc_info.value.status_code == 503


async def test_vscode_proxy_passthrough_preserves_set_cookie(monkeypatch):
    import httpx

    async def fake_verify_token(token):
        return _payload()

    monkeypatch.setattr("app.routers.pods.verify_token", fake_verify_token)
    monkeypatch.setattr("app.routers.pods.port_forward.get_local_port", lambda pod_name: 41000)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, **kwargs):
            return type(
                "Resp",
                (),
                {
                    "content": b"ok",
                    "status_code": 200,
                    "headers": httpx.Headers(
                        [
                            ("content-type", "text/plain"),
                            ("set-cookie", "a=1; Path=/"),
                            ("set-cookie", "b=2; Path=/"),
                        ]
                    ),
                },
            )()

    monkeypatch.setattr("app.routers.pods.httpx.AsyncClient", lambda timeout: FakeClient())
    session = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="running",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    request = _request(cookie="session_token=tok", query="folder=/home")

    async def fake_body():
        return b""

    request.body = fake_body
    response = await vscode_proxy("pod-1", "index.html", request, FakeDB(execute_results=[session]))

    assert response.status_code == 200
    assert response.body == b"ok"
    cookies = response.headers.getlist("set-cookie")
    assert "a=1; Path=/" in cookies
    assert "b=2; Path=/" in cookies


async def test_vscode_ws_proxy_rejects_auth_origin_and_state(monkeypatch):
    ws = FakeWebSocket()
    await vscode_ws_proxy("pod-1", "", ws, FakeDB())
    assert ws.closed[0][0] == 1008

    async def fake_verify_none(token):
        return None

    monkeypatch.setattr("app.routers.pods.verify_token", fake_verify_none)
    ws = FakeWebSocket(cookies={"session_token": "tok"})
    await vscode_ws_proxy("pod-1", "", ws, FakeDB())
    assert ws.closed[0][0] == 1008

    async def fake_verify_token(token):
        return _payload()

    monkeypatch.setattr("app.routers.pods.verify_token", fake_verify_token)
    monkeypatch.setattr("app.routers.pods.settings.cors_origins", ["http://good"])
    ws = FakeWebSocket(cookies={"session_token": "tok"}, headers={"origin": "http://bad"})
    await vscode_ws_proxy("pod-1", "", ws, FakeDB())
    assert ws.closed[0][0] == 1008

    running = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="running",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    monkeypatch.setattr("app.routers.pods.port_forward.get_local_port", lambda pod_name: None)

    async def fail_start(pod_name, namespace):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routers.pods.port_forward.start", fail_start)
    ws = FakeWebSocket(cookies={"session_token": "tok"}, headers={"origin": "http://good"})
    await vscode_ws_proxy("pod-1", "", ws, FakeDB(execute_results=[running]))
    assert ws.accepted is False
    assert ws.closed[-1][0] == 1011


async def test_websocket_terminal_rejects_invalid_requests(monkeypatch):
    ws = FakeWebSocket()
    await websocket_terminal(ws, "pod-1", FakeDB())
    assert ws.closed[0][0] == 1008

    async def fake_verify_none(token):
        return None

    monkeypatch.setattr("app.routers.pods.verify_token", fake_verify_none)
    ws = FakeWebSocket(cookies={"session_token": "tok"})
    await websocket_terminal(ws, "pod-1", FakeDB())
    assert ws.closed[0][0] == 1008

    async def fake_verify_token(token):
        return _payload()

    monkeypatch.setattr("app.routers.pods.verify_token", fake_verify_token)
    monkeypatch.setattr("app.routers.pods.settings.cors_origins", ["http://good"])
    ws = FakeWebSocket(cookies={"session_token": "tok"}, headers={"origin": "http://bad"})
    await websocket_terminal(ws, "pod-1", FakeDB())
    assert ws.closed[0][0] == 1008

    session = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        ssh_port=None,
        ssh_password=None,
        state="running",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    monkeypatch.setattr("app.routers.pods.settings.node_ip", "127.0.0.1")
    monkeypatch.setattr("app.routers.pods.port_forward.get_local_port", lambda pod_name, port=22: None)

    async def fail_start(pod_name, namespace, port=22):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routers.pods.port_forward.start", fail_start)
    ws = FakeWebSocket(cookies={"session_token": "tok"}, headers={"origin": "http://good"})
    await websocket_terminal(ws, "pod-1", FakeDB(execute_results=[session]))
    assert any("SSH is not available" in text for text in ws.sent_text)


# ---------------------------------------------------------------------------
# Network isolation groups (HOP-19 18.3)
# ---------------------------------------------------------------------------

def _teacher_payload() -> TokenPayload:
    return TokenPayload(
        sub="prof-1",
        email="prof@example.com",
        name="Professor One",
        role="professor",
        exp=1234567890,
    )


async def test_create_pod_network_group_requires_teacher_role():
    # No course-membership model exists, so students must not be able to
    # self-select a group (they could join anyone's and defeat isolation).
    with pytest.raises(HTTPException) as exc_info:
        await create_pod.__wrapped__(
            request=None,
            response=None,
            body=CreatePodRequest(plan=VmPlan.SMALL, network_group="cse101"),
            current_user=_payload(),  # role=student
            db=FakeDB(),
        )

    assert exc_info.value.status_code == 403
    assert "network group" in exc_info.value.detail


async def test_create_pod_network_group_flows_to_orchestrator_and_session(monkeypatch):
    async def fake_get_balance(db, user_id):
        return 100.0

    class FakeOrchestratorResponse:
        id = "vm-real-name"
        state = "running"
        ssh_port = 30022
        vscode_port = 30080
        ssh_password = "secret"

    orchestrator_calls = []

    async def fake_create_pod(**kwargs):
        orchestrator_calls.append(kwargs)
        return FakeOrchestratorResponse()

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)
    monkeypatch.setattr("app.routers.pods.orchestrator_client.create_pod", fake_create_pod)

    db = FakeDB(execute_results=[[]])

    result = await create_pod.__wrapped__(
        request=None,
        response=None,
        body=CreatePodRequest(plan=VmPlan.SMALL, network_group="cse101-team1"),
        current_user=_teacher_payload(),
        db=db,
    )

    assert orchestrator_calls[0]["network_group"] == "cse101-team1"
    assert db.added[0].network_group == "cse101-team1"
    assert result.network_group == "cse101-team1"


def test_create_pod_request_rejects_bad_group_names():
    for bad in ("UPPER", "has_underscore", "-lead", "trail-", "a" * 33):
        with pytest.raises(ValueError):
            CreatePodRequest(plan=VmPlan.SMALL, network_group=bad)


async def test_create_pod_returns_queued_response_when_capacity_full(monkeypatch):
    async def fake_get_balance(db, user_id):
        return 100.0

    async def fake_fetch_nodes(_orch):
        return [object()]

    async def fake_reserve_sync_slot(*args, **kwargs):
        return None

    class EnqueueResult:
        id = "queue-1"
        state = "queued"
        plan = "small"

    async def fake_enqueue(*args, **kwargs):
        return EnqueueResult()

    async def fake_queue_position(db, entry):
        return 2

    nudged = {}

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)
    monkeypatch.setattr("app.routers.pods.vm_scheduler.fetch_nodes", fake_fetch_nodes)
    monkeypatch.setattr("app.routers.pods.vm_scheduler.reserve_sync_slot", fake_reserve_sync_slot)
    monkeypatch.setattr("app.routers.pods.vm_queue.enqueue_vm_request", fake_enqueue)
    monkeypatch.setattr("app.routers.pods.vm_queue.queue_position", fake_queue_position)
    monkeypatch.setattr("app.routers.pods.vm_scheduler.nudge", lambda: nudged.setdefault("called", True))

    result = await create_pod.__wrapped__(
        request=None,
        response=None,
        body=CreatePodRequest(plan=VmPlan.SMALL),
        current_user=_payload(),
        db=FakeDB(execute_results=[[]]),
    )

    assert result.status_code == 202
    assert b'"queued":true' in result.body
    assert nudged["called"] is True


async def test_get_availability_returns_null_capacity_when_orchestrator_fails(monkeypatch):
    async def fake_live_queue_count(db):
        return 4

    async def fake_list_nodes():
        raise RuntimeError("down")

    async def fake_current_capacity(db, orch):
        return None

    monkeypatch.setattr("app.routers.pods.vm_queue.live_queue_count", fake_live_queue_count)
    monkeypatch.setattr("app.routers.pods.orchestrator_client.list_nodes", fake_list_nodes)
    monkeypatch.setattr("app.routers.pods.vm_scheduler.current_capacity", fake_current_capacity)

    result = await get_availability(current_user=_payload(), db=FakeDB())

    assert result["queue_length"] == 4
    assert result["nodes_ready"] is None
    assert result["cpu"]["total_cores"] is None


async def test_get_availability_returns_reconciled_capacity(monkeypatch):
    class FakeNode:
        def __init__(self, name, ready):
            self.name = name
            self.ready = ready

    class FakeCapacity:
        total_cpu_m = 4000
        total_mem_b = 8 * 1024**3
        total_storage_b = 100 * 1024**3

        def free_cpu_m(self):
            return 2500

        def free_mem_b(self):
            return 5 * 1024**3

        def free_storage_b(self):
            return 70 * 1024**3

    async def fake_live_queue_count(db):
        return 1

    async def fake_list_nodes():
        return [
            FakeNode("node-a", True),
            FakeNode("node-b", False),
        ]

    async def fake_current_capacity(db, orch):
        return FakeCapacity()

    monkeypatch.setattr("app.routers.pods.vm_queue.live_queue_count", fake_live_queue_count)
    monkeypatch.setattr("app.routers.pods.orchestrator_client.list_nodes", fake_list_nodes)
    monkeypatch.setattr("app.routers.pods.vm_scheduler.current_capacity", fake_current_capacity)

    result = await get_availability(current_user=_payload(), db=FakeDB())

    assert result["nodes_ready"] == 1
    assert result["cpu"]["total_cores"] == 4.0
    assert result["cpu"]["free_cores"] == 2.5
    assert result["storage"]["free_gib"] == 70.0


async def test_list_queue_returns_positions_for_live_entries(monkeypatch):
    first = VmQueueEntry(
        id="q1", user_id="user-1", plan="small", template="ubuntu", image="img",
        cpu="1", memory="2Gi", state="queued", network_group=None, seq=1
    )
    second = VmQueueEntry(
        id="q2", user_id="user-1", plan="medium", template="pytorch", image="img",
        cpu="2", memory="4Gi", state="admitting", network_group=None, seq=2
    )
    db = FakeDB(execute_results=[[first, second]])

    async def fake_queue_position(db_obj, entry):
        return {"q1": 1, "q2": 2}[entry.id]

    monkeypatch.setattr("app.routers.pods.vm_queue.queue_position", fake_queue_position)

    result = await list_queue(current_user=_payload(), db=db)

    assert [item["position"] for item in result] == [1, 2]
    assert result[0]["id"] == "q1"


async def test_cancel_queue_entry_rejects_wrong_owner():
    entry = VmQueueEntry(
        id="q1", user_id="other-user", plan="small", template="ubuntu", image="img",
        cpu="1", memory="2Gi", state="queued", network_group=None, seq=1
    )
    db = FakeDB(execute_results=[entry])

    with pytest.raises(HTTPException) as exc_info:
        await cancel_queue_entry("q1", current_user=_payload(), db=db)

    assert exc_info.value.status_code == 403


async def test_cancel_queue_entry_rejects_non_queued_state():
    entry = VmQueueEntry(
        id="q1", user_id="user-1", plan="small", template="ubuntu", image="img",
        cpu="1", memory="2Gi", state="admitting", network_group=None, seq=1
    )
    db = FakeDB(execute_results=[entry])

    with pytest.raises(HTTPException) as exc_info:
        await cancel_queue_entry("q1", current_user=_payload(), db=db)

    assert exc_info.value.status_code == 409


async def test_cancel_queue_entry_marks_cancelled_and_nudges(monkeypatch):
    entry = VmQueueEntry(
        id="q1", user_id="user-1", plan="small", template="ubuntu", image="img",
        cpu="1", memory="2Gi", state="queued", network_group=None, seq=1
    )
    db = FakeDB(execute_results=[entry])
    nudged = {}
    monkeypatch.setattr("app.routers.pods.vm_scheduler.nudge", lambda: nudged.setdefault("called", True))

    result = await cancel_queue_entry("q1", current_user=_payload(), db=db)

    assert result == {"message": "cancelled", "id": "q1"}
    assert entry.state == "cancelled"
    assert db.commits == 1
    assert nudged["called"] is True


async def test_safe_send_ignores_runtime_error():
    class FakeWebSocket:
        async def send_text(self, text):
            raise RuntimeError("closed")

    await _safe_send(FakeWebSocket(), "hello")
