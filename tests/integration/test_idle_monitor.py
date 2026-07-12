"""Idle auto-shutdown against a real database.

The unit tests stub out the metrics query; this exercises it for real, including
the detail that metrics_samples may be keyed by either the session UUID or the
K8s pod name depending on whether the pod has been reconciled.
"""

from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest
import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.models import MetricsSample, PodSession, User
from app.services import idle_monitor


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


NOW = datetime(2026, 7, 13, 12, 0)


@pytest_asyncio.fixture
async def student(db_session):
    db_session.add(User(id="stu-1", email="stu1@cs.du.ac.bd", name="Student", role="student"))
    await db_session.commit()


@pytest_asyncio.fixture
async def pod(db_session, student):
    session = PodSession(
        id="pod-1",
        user_id="stu-1",
        plan="small",
        image="hopper/vm-ubuntu:22.04",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-123",
        state="running",
        started_at=NOW - timedelta(hours=5),   # old enough to judge
        expires_at=NOW + timedelta(hours=3),   # the session TTL
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


async def _sample(db, pod_id: str, cpu: float, minutes_ago: int):
    db.add(
        MetricsSample(
            time=NOW - timedelta(minutes=minutes_ago),
            pod_id=pod_id,
            user_id="stu-1",
            cpu_percent=cpu,
            memory_used_bytes=1000,
            memory_limit_bytes=2000,
        )
    )
    await db.commit()


@pytest.fixture(autouse=True)
def no_orchestrator(monkeypatch):
    """There is no orchestrator in the test harness — record kills instead."""
    killed = []

    async def fake_terminate(session):
        killed.append(session.pod_name)
        session.state = "terminated"

    monkeypatch.setattr(idle_monitor, "_terminate", fake_terminate)
    return killed


async def test_quiet_samples_make_the_vm_idle(db_session, pod):
    for minutes_ago in (25, 15, 5):
        await _sample(db_session, "vm-123", cpu=0.4, minutes_ago=minutes_ago)

    assert await idle_monitor.is_idle(db_session, pod, NOW) is True


async def test_one_busy_sample_in_the_window_keeps_it_alive(db_session, pod):
    await _sample(db_session, "vm-123", cpu=0.4, minutes_ago=25)
    await _sample(db_session, "vm-123", cpu=70.0, minutes_ago=12)  # real work
    await _sample(db_session, "vm-123", cpu=0.4, minutes_ago=2)

    assert await idle_monitor.is_idle(db_session, pod, NOW) is False


async def test_activity_older_than_the_window_does_not_count(db_session, pod):
    """Busy two hours ago, silent since — that is exactly what idle looks like."""
    await _sample(db_session, "vm-123", cpu=90.0, minutes_ago=120)
    await _sample(db_session, "vm-123", cpu=0.2, minutes_ago=10)

    assert await idle_monitor.is_idle(db_session, pod, NOW) is True


async def test_metrics_keyed_by_the_session_uuid_are_found_too(db_session, pod):
    """Reconciled pods report under the UUID rather than the K8s name."""
    await _sample(db_session, "pod-1", cpu=88.0, minutes_ago=10)

    assert await idle_monitor.is_idle(db_session, pod, NOW) is False


async def test_a_vm_with_no_samples_at_all_is_never_idle(db_session, pod):
    assert await idle_monitor.is_idle(db_session, pod, NOW) is False


async def test_full_lifecycle_warn_then_shutdown(db_session, pod, no_orchestrator):
    for minutes_ago in (25, 15, 5):
        await _sample(db_session, "vm-123", cpu=0.3, minutes_ago=minutes_ago)

    # First pass: warned, not killed.
    first = await idle_monitor.process_idle_sessions(db_session, now=NOW)
    assert first["warned"] == 1
    assert no_orchestrator == []
    await db_session.refresh(pod)
    assert pod.idle_shutdown_at is not None
    assert pod.expires_at == NOW + timedelta(hours=3)  # session TTL untouched

    # Still idle when the deadline passes: killed.
    later = NOW + timedelta(minutes=11)
    second = await idle_monitor.process_idle_sessions(db_session, now=later)

    assert second["shutdown"] == 1
    assert no_orchestrator == ["vm-123"]
    await db_session.refresh(pod)
    assert pod.state == "terminated"
    assert pod.idle_shutdown_at is None


async def test_coming_back_to_work_cancels_the_shutdown(db_session, pod, no_orchestrator):
    for minutes_ago in (25, 15, 5):
        await _sample(db_session, "vm-123", cpu=0.3, minutes_ago=minutes_ago)

    await idle_monitor.process_idle_sessions(db_session, now=NOW)
    await db_session.refresh(pod)
    assert pod.idle_shutdown_at is not None

    # The student comes back and starts working within the grace window.
    later = NOW + timedelta(minutes=5)
    db_session.add(
        MetricsSample(
            time=later - timedelta(minutes=1),
            pod_id="vm-123",
            user_id="stu-1",
            cpu_percent=75.0,
            memory_used_bytes=1000,
            memory_limit_bytes=2000,
        )
    )
    await db_session.commit()

    result = await idle_monitor.process_idle_sessions(db_session, now=later)

    assert result["reprieved"] == 1
    assert no_orchestrator == []  # VM saved
    await db_session.refresh(pod)
    assert pod.state == "running"
    assert pod.idle_shutdown_at is None


async def test_terminated_pods_are_ignored(db_session, pod, no_orchestrator):
    pod.state = "terminated"
    await db_session.commit()
    await _sample(db_session, "vm-123", cpu=0.0, minutes_ago=10)

    result = await idle_monitor.process_idle_sessions(db_session, now=NOW)

    assert result == {"warned": 0, "shutdown": 0, "reprieved": 0}
