"""Stop / resume against the real app + database.

Resume is rate-limited, so it can't be called as a plain function (slowapi needs
a real Request) — it is exercised here through the ASGI app instead.

The orchestrator is stubbed: there is no K8s cluster in the harness. What is
real is the DB state machine, which is where the traps are (TTL resets, quota
accounting, stale ports).
"""

from datetime import datetime, timedelta
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
from app.models import PodSession, User
from app.models.vm_plan import VmPlanRow
from app.routers import pods as pods_router
from app.schemas.user import TokenPayload
from app.services.credit_service import add_credits


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


def _payload(sub="stu-1", role="student") -> TokenPayload:
    return TokenPayload(
        sub=sub, email=f"{sub}@cs.du.ac.bd", name="Student", role=role,
        exp=4_102_444_800, email_verified=True,
    )


@pytest.fixture
def auth() -> dict:
    return {"user": _payload()}


@pytest_asyncio.fixture
async def client(db_session, auth):
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    app = create_app()
    original_async_session = audit_middleware.async_session

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def override_get_current_user():
        return auth["user"]

    audit_middleware.async_session = session_factory
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c

    app.dependency_overrides.clear()
    audit_middleware.async_session = original_async_session


@pytest.fixture(autouse=True)
def fake_orchestrator(monkeypatch):
    """No cluster here — record the calls and hand back a plausible pod."""
    calls = {"created": [], "terminated": []}

    async def fake_create(**kwargs):
        calls["created"].append(kwargs)
        from types import SimpleNamespace

        return SimpleNamespace(
            id="vm-resumed",
            state="running",
            ssh_port=31001,
            vscode_port=31002,
            ssh_password="fresh-secret",
        )

    async def fake_terminate(pod_name):
        calls["terminated"].append(pod_name)

    async def fake_pf_stop(pod_name):
        pass

    monkeypatch.setattr(pods_router.orchestrator_client, "create_pod", fake_create)
    monkeypatch.setattr(pods_router.orchestrator_client, "terminate_pod", fake_terminate)
    monkeypatch.setattr(pods_router.port_forward, "stop", fake_pf_stop)
    return calls


@pytest_asyncio.fixture
async def student(db_session):
    # The "small" plan is seeded by the vm_plans migration — reuse it rather than
    # inserting a duplicate.
    db_session.add(User(id="stu-1", email="stu1@cs.du.ac.bd", name="Student", role="student"))
    await db_session.commit()
    await add_credits(db_session, "stu-1", 100.0, "admin_grant")

    plan = await db_session.get(VmPlanRow, "small")
    assert plan is not None, "expected the seeded 'small' plan"
    return plan


@pytest_asyncio.fixture
async def running_pod(db_session, student):
    session = PodSession(
        id="pod-1",
        user_id="stu-1",
        plan="small",
        image="hopper/vm-ubuntu:22.04",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-original",
        state="running",
        ssh_port=30001,
        vscode_port=30002,
        ssh_password="old-secret",
        started_at=datetime.utcnow() - timedelta(hours=1),
        expires_at=datetime.utcnow() + timedelta(hours=3),
        extension_count=2,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


async def test_stop_then_resume_round_trip(client, running_pod, db_session, fake_orchestrator):
    stopped = await client.post("/pods/pod-1/stop")

    assert stopped.status_code == 200
    assert stopped.json()["state"] == "stopped"
    assert fake_orchestrator["terminated"] == ["vm-original"]
    # The dead pod's ports must not be advertised — they get reassigned.
    assert stopped.json()["ssh_port"] is None
    assert stopped.json()["ssh_password"] is None

    resumed = await client.post("/pods/pod-1/resume")

    assert resumed.status_code == 200
    body = resumed.json()
    assert body["id"] == "pod-1"        # same session, not a new VM
    assert body["state"] == "running"
    assert body["ssh_port"] == 31001    # fresh connection details
    assert body["ssh_password"] == "fresh-secret"


async def test_resume_remounts_the_same_workspace(client, running_pod, fake_orchestrator):
    """This is the whole point: /workspace comes back with the files in it."""
    await client.post("/pods/pod-1/stop")
    await client.post("/pods/pod-1/resume")

    created = fake_orchestrator["created"][-1]
    # The per-user workspace PVC is deterministic, so the resumed pod mounts the
    # exact volume the stopped one was using.
    assert created["workspace_pvc_name"] == "ws-user-stu-1"


async def test_a_stopped_vm_does_not_count_against_the_concurrent_quota(
    client, running_pod, db_session
):
    """A stopped VM burns no CPU, so it must not hold a VM slot hostage."""
    await client.post("/pods/pod-1/stop")

    # Default quota is 3 concurrent VMs. Fill all 3 with genuinely live pods.
    for i in range(3):
        db_session.add(
            PodSession(
                id=f"other-{i}", user_id="stu-1", plan="small",
                image="hopper/vm-ubuntu:22.04", cpu="1", memory="2Gi",
                namespace="hopper", pod_name=f"vm-other-{i}", state="running",
            )
        )
    await db_session.commit()

    # The stopped VM didn't stop them being launched — but resuming it now would
    # be a 4th live VM, so the quota has to bite here.
    blocked = await client.post("/pods/pod-1/resume")
    assert blocked.status_code == 429


async def test_resume_grants_a_fresh_ttl_so_the_reaper_does_not_kill_it(
    client, running_pod, db_session
):
    """A VM stopped past its old expiry would otherwise be reaped the moment it
    came back — the session reaper skips it only while it is stopped."""
    await client.post("/pods/pod-1/stop")

    await db_session.refresh(running_pod)
    running_pod.expires_at = datetime.utcnow() - timedelta(hours=2)  # long expired
    await db_session.commit()

    resumed = await client.post("/pods/pod-1/resume")

    assert resumed.status_code == 200
    await db_session.refresh(running_pod)
    assert running_pod.expires_at > datetime.utcnow()
    assert running_pod.extension_count == 0  # a fresh sitting


async def test_resume_is_refused_when_the_owner_is_out_of_credits(
    client, running_pod, db_session
):
    await client.post("/pods/pod-1/stop")

    # Drain the account below one hour of the plan.
    from app.services.credit_service import deduct_credits

    await deduct_credits(db_session, "stu-1", 99.5, "vm_usage", tx_id="drain-1")

    refused = await client.post("/pods/pod-1/resume")

    assert refused.status_code == 402
    await db_session.refresh(running_pod)
    assert running_pod.state == "stopped"  # still there to resume once funded


async def test_a_stopped_vm_can_still_be_terminated_for_good(client, running_pod, db_session):
    await client.post("/pods/pod-1/stop")

    gone = await client.delete("/pods/pod-1")

    assert gone.status_code == 200
    await db_session.refresh(running_pod)
    assert running_pod.state == "terminated"

    # And a terminated VM is not resumable.
    assert (await client.post("/pods/pod-1/resume")).status_code == 400


async def test_another_student_cannot_stop_or_resume_your_vm(client, running_pod, auth):
    auth["user"] = _payload(sub="stu-2")

    assert (await client.post("/pods/pod-1/stop")).status_code == 403
    assert (await client.post("/pods/pod-1/resume")).status_code == 403
