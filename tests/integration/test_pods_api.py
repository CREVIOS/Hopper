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
from app.models import PodSession
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
async def test_list_plans_returns_vm_plan_catalog(client):
    response = await client.get("/pods/plans")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"small", "medium", "large"}
    assert body["small"]["credits_per_hour"] == 1.0


@pytest.mark.asyncio
async def test_create_pod_requires_sufficient_credits(client):
    response = await client.post("/pods/", json={"plan": "small"})

    assert response.status_code == 402
    assert "Insufficient credits" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_pod_persists_running_session_details(client, monkeypatch):
    async def fake_get_balance(db, user_id):
        return 10.0

    async def fake_create_pod(**kwargs):
        return SimpleNamespace(
            id="vm-real-name",
            state="running",
            ssh_port=30022,
            vscode_port=30080,
            ssh_password="secret",
        )

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)
    monkeypatch.setattr("app.routers.pods.orchestrator_client.create_pod", fake_create_pod)

    response = await client.post("/pods/", json={"plan": "small"})

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "running"
    assert body["ssh_port"] == 30022
    assert body["vscode_port"] == 30080
    assert body["ssh_password"] == "secret"


@pytest.mark.asyncio
async def test_terminate_pod_marks_session_terminated(client, db_session, monkeypatch):
    db_session.add(
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
        )
    )
    await db_session.commit()

    terminated = []
    stopped = []

    async def fake_terminate_pod(pod_name):
        terminated.append(pod_name)

    async def fake_stop(pod_name):
        stopped.append(pod_name)

    monkeypatch.setattr("app.routers.pods.orchestrator_client.terminate_pod", fake_terminate_pod)
    monkeypatch.setattr("app.routers.pods.port_forward.stop", fake_stop)

    response = await client.delete("/pods/pod-1")

    assert response.status_code == 200
    assert response.json() == {"message": "terminated", "pod_id": "pod-1"}
    assert terminated == ["vm-pod-1"]
    assert stopped == ["vm-pod-1"]


@pytest.mark.asyncio
async def test_list_pods_returns_only_current_users_sessions(client, db_session):
    db_session.add_all(
        [
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
                user_id="other-user",
                plan="medium",
                image="hopper/vm-python-ml:22.04",
                cpu="2",
                memory="4Gi",
                namespace="hopper",
                pod_name="vm-pod-2",
                state="running",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get("/pods/")

    assert response.status_code == 200
    pods = response.json()
    assert len(pods) == 1
    assert pods[0]["id"] == "pod-1"


@pytest.mark.asyncio
async def test_get_pod_returns_running_session_details(client, db_session):
    db_session.add(
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
            ssh_port=30022,
            vscode_port=30080,
            ssh_password="secret",
        )
    )
    await db_session.commit()

    response = await client.get("/pods/pod-1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "pod-1"
    assert body["state"] == "running"
    assert body["ssh_port"] == 30022
    assert body["vscode_port"] == 30080


@pytest.mark.asyncio
async def test_get_pod_rejects_other_users_session(client, db_session):
    db_session.add(
        PodSession(
            id="pod-1",
            user_id="other-user",
            plan="small",
            image="hopper/vm-ubuntu:22.04",
            cpu="1",
            memory="2Gi",
            namespace="hopper",
            pod_name="vm-pod-1",
            state="running",
        )
    )
    await db_session.commit()

    response = await client.get("/pods/pod-1")

    assert response.status_code == 403
    assert response.json() == {"detail": "Not your VM"}


@pytest.mark.asyncio
async def test_create_pod_enforces_max_concurrent_limit(client, db_session, monkeypatch):
    async def fake_get_balance(db, user_id):
        return 10.0

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)
    db_session.add_all(
        [
            PodSession(
                id=f"pod-{i}",
                user_id="student-1",
                plan="small",
                image="hopper/vm-ubuntu:22.04",
                cpu="1",
                memory="2Gi",
                namespace="hopper",
                pod_name=f"vm-pod-{i}",
                state="running",
            )
            for i in range(1, 4)
        ]
    )
    await db_session.commit()

    response = await client.post("/pods/", json={"plan": "small"})

    assert response.status_code == 429
    assert response.json() == {"detail": "Maximum 3 concurrent VMs allowed"}


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_not_found_for_missing_vm(client):
    response = await client.get("/pods/missing/metrics")

    assert response.status_code == 404
    assert response.json() == {"detail": "VM not found"}


@pytest.mark.asyncio
async def test_vscode_proxy_redirects_html_requests_without_session(client):
    response = await client.get(
        "/pods/pod-1/vscode/",
        headers={"accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/login?return_to=" in response.headers["location"]


@pytest.mark.asyncio
async def test_vscode_proxy_returns_401_for_non_html_without_session(client):
    response = await client.get(
        "/pods/pod-1/vscode/",
        headers={"accept": "application/json"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_vscode_proxy_returns_503_when_vm_not_running(client, db_session, monkeypatch):
    db_session.add(
        PodSession(
            id="pod-1",
            user_id="student-1",
            plan="small",
            image="hopper/vm-ubuntu:22.04",
            cpu="1",
            memory="2Gi",
            namespace="hopper",
            pod_name="vm-pod-1",
            state="creating",
        )
    )
    await db_session.commit()

    async def fake_verify_token(token):
        return TokenPayload(
            sub="student-1",
            email="student1@cs.du.ac.bd",
            name="Student One",
            role="student",
            exp=4_102_444_800,
            email_verified=True,
        )

    monkeypatch.setattr("app.routers.pods.verify_token", fake_verify_token)

    response = await client.get(
        "/pods/pod-1/vscode/",
        headers={"accept": "application/json"},
        cookies={"session_token": "valid-token"},
    )

    assert response.status_code == 503
    assert "VM is creating" in response.json()["detail"]


# --- DB-backed plan pricing flows to the orchestrator -------------------------

@pytest.mark.asyncio
async def test_create_pod_uses_db_plan_and_forwards_rate(
    client, db_session, current_user_payload, monkeypatch
):
    from sqlalchemy import delete as sa_delete

    from app.models import VmPlanRow

    # Use a dedicated user so the persistent workspace (idempotent per user and
    # not truncated between tests) is created fresh from this plan's workspace_gb.
    current_user_payload.sub = "gpu-user"

    # An admin-created custom plan with a distinct rate/resources.
    db_session.add(VmPlanRow(
        name="gpu-x", display_name="GPU X", cpu="16", memory="32Gi", disk="80Gi",
        credits_per_hour=5.0, workspace_gb=64, is_active=True,
    ))
    await db_session.commit()

    captured = {}

    async def fake_get_balance(db, user_id):
        return 100.0

    async def fake_create_pod(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="vm-real", state="running", ssh_port=1, vscode_port=2, ssh_password="p")

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)
    monkeypatch.setattr("app.routers.pods.orchestrator_client.create_pod", fake_create_pod)

    try:
        response = await client.post("/pods/", json={"plan": "gpu-x"})

        assert response.status_code == 201
        # The custom plan's resources + rate reached the orchestrator.
        assert captured["plan"] == "gpu-x"
        assert captured["cpu"] == "16"
        assert captured["memory"] == "32Gi"
        assert captured["credits_per_hour"] == 5.0
        assert captured["workspace_capacity_gb"] == 64
    finally:
        await db_session.execute(sa_delete(VmPlanRow).where(VmPlanRow.name == "gpu-x"))
        await db_session.commit()


@pytest.mark.asyncio
async def test_create_pod_rejects_unknown_plan(client, monkeypatch):
    async def fake_get_balance(db, user_id):
        return 100.0

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)

    response = await client.post("/pods/", json={"plan": "no-such-plan"})

    assert response.status_code == 400
    assert "Unknown or unavailable plan" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_pod_rejects_inactive_plan(client, db_session, monkeypatch):
    from sqlalchemy import delete as sa_delete

    from app.models import VmPlanRow

    db_session.add(VmPlanRow(
        name="retired", display_name="Retired", cpu="1", memory="2Gi", disk="5Gi",
        credits_per_hour=1.0, workspace_gb=20, is_active=False,
    ))
    await db_session.commit()

    async def fake_get_balance(db, user_id):
        return 100.0

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)

    try:
        response = await client.post("/pods/", json={"plan": "retired"})
        assert response.status_code == 400
    finally:
        await db_session.execute(sa_delete(VmPlanRow).where(VmPlanRow.name == "retired"))
        await db_session.commit()


# --- DB-backed template/image resolution -------------------------------------

@pytest.mark.asyncio
async def test_list_templates_returns_seeded_catalog(client):
    response = await client.get("/pods/templates")
    assert response.status_code == 200
    body = response.json()
    assert {"ubuntu", "python-ml", "cpp", "java"} <= set(body)
    assert body["ubuntu"]["image"] == "hopper/vm-ubuntu:22.04"
    assert body["ubuntu"]["is_default"] is True


@pytest.mark.asyncio
async def test_create_pod_resolves_image_from_db_template(client, db_session, current_user_payload, monkeypatch):
    from sqlalchemy import delete as sa_delete

    from app.models import VmImageRow

    current_user_payload.sub = "tmpl-user"
    # An admin-added template with a distinct image tag.
    db_session.add(VmImageRow(
        template="rust", display_name="Rust", image="hopper/vm-rust:1.2",
        description="", is_active=True, is_default=False,
    ))
    await db_session.commit()

    captured = {}

    async def fake_get_balance(db, user_id):
        return 100.0

    async def fake_create_pod(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="vm-real", state="running", ssh_port=1, vscode_port=2, ssh_password="p")

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)
    monkeypatch.setattr("app.routers.pods.orchestrator_client.create_pod", fake_create_pod)

    try:
        response = await client.post("/pods/", json={"plan": "small", "template": "rust"})
        assert response.status_code == 201
        assert captured["image"] == "hopper/vm-rust:1.2"
    finally:
        await db_session.execute(sa_delete(VmImageRow).where(VmImageRow.template == "rust"))
        await db_session.commit()


# --- Quota enforcement --------------------------------------------------------

@pytest.mark.asyncio
async def test_create_pod_blocks_when_over_storage_quota(client, db_session, current_user_payload, monkeypatch):
    from sqlalchemy import delete as sa_delete

    from app.models import UserQuota

    current_user_payload.sub = "quota-user"
    # 10 GB storage quota, but 'small' needs a 20 GB workspace.
    db_session.add(UserQuota(user_id="quota-user", max_concurrent_vms=3, max_workspace_gb=10))
    await db_session.commit()

    async def fake_get_balance(db, user_id):
        return 100.0

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)

    try:
        response = await client.post("/pods/", json={"plan": "small"})
        assert response.status_code == 403
        assert "storage quota" in response.json()["detail"]
    finally:
        await db_session.execute(sa_delete(UserQuota).where(UserQuota.user_id == "quota-user"))
        await db_session.commit()


@pytest.mark.asyncio
async def test_create_pod_blocks_when_over_concurrent_quota(client, db_session, current_user_payload, monkeypatch):
    from sqlalchemy import delete as sa_delete

    from app.models import PodSession as PS
    from app.models import UserQuota

    current_user_payload.sub = "cc-user"
    # Concurrent limit of 1, and the user already has a running VM.
    db_session.add(UserQuota(user_id="cc-user", max_concurrent_vms=1, max_workspace_gb=1000))
    db_session.add(PS(
        id="existing", user_id="cc-user", plan="small", image="img", cpu="1", memory="2Gi",
        namespace="hopper", pod_name="vm-existing", state="running",
    ))
    await db_session.commit()

    async def fake_get_balance(db, user_id):
        return 100.0

    monkeypatch.setattr("app.routers.pods.get_balance", fake_get_balance)

    try:
        response = await client.post("/pods/", json={"plan": "small"})
        assert response.status_code == 429
        assert "Maximum 1 concurrent VM allowed" in response.json()["detail"]
    finally:
        await db_session.execute(sa_delete(UserQuota).where(UserQuota.user_id == "cc-user"))
        await db_session.commit()
