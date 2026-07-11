from datetime import datetime

from app.models.session import PodSession
from app.services import session_reaper


class FakeDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def _session(pod_name="vm-1", state="running") -> PodSession:
    return PodSession(
        id="pod-1", user_id="u1", plan="small", image="img", cpu="1", memory="2Gi",
        namespace="hopper", pod_name=pod_name, state=state,
    )


async def test_reap_terminates_each_expired_and_marks_terminated(monkeypatch):
    s1, s2 = _session("vm-1"), _session("vm-2")
    terminated = []

    async def fake_find(db, now):
        return [s1, s2]

    async def fake_terminate_pod(pod_name):
        terminated.append(pod_name)
        return True

    async def fake_stop(pod_name):
        pass

    monkeypatch.setattr(session_reaper, "find_expired_sessions", fake_find)
    monkeypatch.setattr(session_reaper.orchestrator_client, "terminate_pod", fake_terminate_pod)
    monkeypatch.setattr(session_reaper.port_forward, "stop", fake_stop)

    db = FakeDB()
    count = await session_reaper.reap_expired_sessions(db, now=datetime(2026, 1, 1))

    assert count == 2
    assert terminated == ["vm-1", "vm-2"]
    assert s1.state == "terminated" and s2.state == "terminated"
    assert db.commits == 1


async def test_reap_noop_when_nothing_expired(monkeypatch):
    async def fake_find(db, now):
        return []

    monkeypatch.setattr(session_reaper, "find_expired_sessions", fake_find)

    db = FakeDB()
    count = await session_reaper.reap_expired_sessions(db, now=datetime(2026, 1, 1))

    assert count == 0
    assert db.commits == 0  # no work → no commit


async def test_reap_survives_orchestrator_failure(monkeypatch):
    s1 = _session("vm-1")

    async def fake_find(db, now):
        return [s1]

    async def boom(pod_name):
        raise RuntimeError("orchestrator down")

    async def fake_stop(pod_name):
        pass

    monkeypatch.setattr(session_reaper, "find_expired_sessions", fake_find)
    monkeypatch.setattr(session_reaper.orchestrator_client, "terminate_pod", boom)
    monkeypatch.setattr(session_reaper.port_forward, "stop", fake_stop)

    db = FakeDB()
    count = await session_reaper.reap_expired_sessions(db, now=datetime(2026, 1, 1))

    # Best-effort: DB is still marked terminated even if the orchestrator call failed.
    assert count == 1
    assert s1.state == "terminated"
