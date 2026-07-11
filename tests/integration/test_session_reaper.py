"""Integration tests for the session-expiry reaper (FR-HC-27)."""

from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest
from sqlalchemy import select


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


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

from app.models import PodSession
from app.services import session_reaper


def _pod(pod_id, state, expires_at):
    return PodSession(
        id=pod_id, user_id="u1", plan="small", image="img", cpu="1", memory="2Gi",
        namespace="hopper", pod_name=f"vm-{pod_id}", state=state, expires_at=expires_at,
    )


async def test_reaper_terminates_only_expired_live_pods(db_session, monkeypatch):
    now = datetime.utcnow()
    db_session.add_all([
        _pod("expired-run", "running", now - timedelta(minutes=5)),
        _pod("expired-pending", "pending", now - timedelta(hours=1)),
        _pod("future-run", "running", now + timedelta(hours=1)),
        _pod("already-term", "terminated", now - timedelta(hours=2)),
        _pod("no-ttl", "running", None),
    ])
    await db_session.commit()

    terminated = []

    async def fake_terminate_pod(pod_name):
        terminated.append(pod_name)
        return True

    async def fake_stop(pod_name):
        pass

    monkeypatch.setattr(session_reaper.orchestrator_client, "terminate_pod", fake_terminate_pod)
    monkeypatch.setattr(session_reaper.port_forward, "stop", fake_stop)

    count = await session_reaper.reap_expired_sessions(db_session, now=now)

    assert count == 2
    assert set(terminated) == {"vm-expired-run", "vm-expired-pending"}

    db_session.expire_all()
    states = {
        p.id: p.state
        for p in (await db_session.execute(select(PodSession))).scalars().all()
    }
    assert states["expired-run"] == "terminated"
    assert states["expired-pending"] == "terminated"
    assert states["future-run"] == "running"      # not past TTL
    assert states["already-term"] == "terminated"  # untouched
    assert states["no-ttl"] == "running"           # no TTL set → never reaped
