from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.pods import stop_pod
from app.schemas.user import TokenPayload


def _payload(sub="stu-1", role="student") -> TokenPayload:
    return TokenPayload(
        sub=sub, email="s@cs.du.ac.bd", name="Student", role=role, exp=4_102_444_800
    )


def _session(**overrides) -> SimpleNamespace:
    defaults = dict(
        id="pod-1",
        user_id="stu-1",
        plan="small",
        image="hopper/vm-ubuntu:22.04",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        updated_at=datetime(2026, 7, 13, 9, 0),
        pod_name="vm-123",
        state="running",
        ssh_port=30001,
        vscode_port=30002,
        ssh_password="secret",
        started_at=datetime(2026, 7, 13, 8, 0),
        expires_at=datetime(2026, 7, 13, 12, 0),
        extension_count=2,
        credit_grace_until=datetime(2026, 7, 13, 11, 0),
        idle_shutdown_at=datetime(2026, 7, 13, 11, 30),
    )
    return SimpleNamespace(**{**defaults, **overrides})


class FakeDB:
    def __init__(self, session=None, active_count=0):
        self.session = session
        self.active_count = active_count
        self.commits = 0

    async def execute(self, stmt):
        # First call resolves the pod; later calls are the concurrent-VM query.
        # Distinguish by what the caller does with the result.
        return SimpleNamespace(
            scalar_one_or_none=lambda: self.session,
            scalars=lambda: SimpleNamespace(
                all=lambda: [object()] * self.active_count
            ),
        )

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass


@pytest.fixture
def orchestrator(monkeypatch):
    calls = {"terminated": [], "created": []}

    async def fake_terminate(pod_name):
        calls["terminated"].append(pod_name)

    async def fake_stop(pod_name):
        pass

    monkeypatch.setattr("app.routers.pods.orchestrator_client.terminate_pod", fake_terminate)
    monkeypatch.setattr("app.routers.pods.port_forward.stop", fake_stop)
    return calls


# --- stop --------------------------------------------------------------------


async def test_stop_keeps_the_session_and_clears_stale_connection_details(orchestrator):
    session = _session()
    db = FakeDB(session)

    await stop_pod("pod-1", current_user=_payload(), db=db)

    assert session.state == "stopped"          # not terminated — resumable
    assert orchestrator["terminated"] == ["vm-123"]
    # The pod is gone: its NodePorts are released and could be reassigned to
    # someone else's VM, so serving them would point the user at a stranger's box.
    assert session.ssh_port is None
    assert session.vscode_port is None
    assert session.ssh_password is None


async def test_stop_clears_both_countdowns(orchestrator):
    """Neither the credit grace nor the idle shutdown applies to a stopped VM."""
    session = _session()

    await stop_pod("pod-1", current_user=_payload(), db=FakeDB(session))

    assert session.credit_grace_until is None
    assert session.idle_shutdown_at is None


async def test_only_a_running_vm_can_be_stopped(orchestrator):
    session = _session(state="stopped")

    with pytest.raises(HTTPException) as exc:
        await stop_pod("pod-1", current_user=_payload(), db=FakeDB(session))

    assert exc.value.status_code == 400


async def test_another_student_cannot_stop_your_vm(orchestrator):
    session = _session(user_id="stu-1")

    with pytest.raises(HTTPException) as exc:
        await stop_pod("pod-1", current_user=_payload(sub="stu-2"), db=FakeDB(session))

    assert exc.value.status_code == 403


async def test_an_admin_can_stop_any_vm(orchestrator):
    session = _session(user_id="stu-1")

    await stop_pod("pod-1", current_user=_payload(sub="admin-1", role="admin"), db=FakeDB(session))

    assert session.state == "stopped"


async def test_a_failed_teardown_does_not_report_the_vm_as_stopped(monkeypatch):
    """If the orchestrator can't kill the pod, the row must not claim 'stopped' —
    that would strand a VM that is still running and still billing."""
    session = _session()

    async def boom(pod_name):
        raise RuntimeError("orchestrator down")

    monkeypatch.setattr("app.routers.pods.orchestrator_client.terminate_pod", boom)

    with pytest.raises(HTTPException) as exc:
        await stop_pod("pod-1", current_user=_payload(), db=FakeDB(session))

    assert exc.value.status_code == 502
    assert session.state == "running"  # unchanged
