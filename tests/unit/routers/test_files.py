import pytest
from fastapi import HTTPException

from app.models.session import PodSession
from app.routers.files import _get_user_pod, _safe_path, _ssh_endpoint, list_directory
from app.schemas.user import TokenPayload


def test_safe_path_accepts_normal_path():
    assert _safe_path("/home/student") == "/home/student"


@pytest.mark.parametrize("path", ["", "bad\x00path", "bad\npath"])
def test_safe_path_rejects_invalid_path(path):
    with pytest.raises(HTTPException) as exc_info:
        _safe_path(path)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "invalid path"


def _payload() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="Test User",
        role="student",
        exp=1234567890,
    )


class FakeExecuteResult:
    def __init__(self, session):
        self.session = session

    def scalar_one_or_none(self):
        return self.session


class FakeDB:
    def __init__(self, session):
        self.session = session

    async def execute(self, stmt):
        return FakeExecuteResult(self.session)


async def test_get_user_pod_rejects_missing_pod():
    with pytest.raises(HTTPException) as exc_info:
        await _get_user_pod("pod-1", _payload(), FakeDB(None))

    assert exc_info.value.status_code == 404


async def test_get_user_pod_rejects_other_users_pod():
    session = PodSession(
        id="pod-1",
        user_id="other-user",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="running",
    )

    with pytest.raises(HTTPException) as exc_info:
        await _get_user_pod("pod-1", _payload(), FakeDB(session))

    assert exc_info.value.status_code == 403


async def test_ssh_endpoint_uses_existing_port_forward(monkeypatch):
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
    )
    monkeypatch.setattr("app.routers.files.port_forward.get_local_port", lambda pod_name, port: 51000)

    assert await _ssh_endpoint(session) == ("127.0.0.1", 51000)


async def test_ssh_endpoint_falls_back_to_nodeport(monkeypatch):
    session = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        ssh_port=30022,
        state="running",
    )

    monkeypatch.setattr("app.routers.files.port_forward.get_local_port", lambda pod_name, port: None)

    async def fail_start(pod_name, namespace, port):
        raise RuntimeError("no pf")

    monkeypatch.setattr("app.routers.files.port_forward.start", fail_start)
    monkeypatch.setattr("app.config.settings.node_ip", "127.0.0.1")

    assert await _ssh_endpoint(session) == ("127.0.0.1", 30022)


async def test_list_directory_parses_and_sorts_entries(monkeypatch):
    session = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        ssh_password="secret",
        state="running",
    )

    async def fake_get_user_pod(pod_id, user, db):
        return session

    async def fake_ssh_endpoint(sess):
        return ("127.0.0.1", 51000)

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return (
                b"total 8\n-rw-r--r-- 1 root root 12 2026-01-01 12:00 file.txt\n"
                b"drwxr-xr-x 2 root root 4096 2026-01-01 11:00 data\n",
                b"",
            )

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr("app.routers.files._get_user_pod", fake_get_user_pod)
    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    result = await list_directory("pod-1", "/home", _payload(), FakeDB(session))

    assert result["path"] == "/home"
    assert result["entries"][0]["name"] == "data"
    assert result["entries"][1]["name"] == "file.txt"
