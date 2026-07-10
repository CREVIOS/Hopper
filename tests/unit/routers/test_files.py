import pytest
from fastapi import HTTPException

from app.models.session import PodSession
from app.routers.files import (
    DeleteRequest,
    MkdirRequest,
    RenameRequest,
    _get_user_pod,
    _reject_root_delete,
    _safe_path,
    _ssh_endpoint,
    delete_entry,
    list_directory,
    make_directory,
    rename_entry,
)
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


# --- delete / rename / mkdir --------------------------------------------------

def _running_session() -> PodSession:
    return PodSession(
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


class _CmdCapture:
    """Monkeypatch target that records the remote command and returns a fake proc."""

    def __init__(self, returncode: int = 0, stderr: bytes = b""):
        self.returncode = returncode
        self.stderr = stderr
        self.remote_cmd: str | None = None

    def install(self, monkeypatch):
        async def fake_get_user_pod(pod_id, user, db):
            return _running_session()

        async def fake_ssh_endpoint(sess):
            return ("127.0.0.1", 51000)

        outer = self

        class FakeProc:
            returncode = self.returncode

            async def communicate(self):
                return (b"", outer.stderr)

        async def fake_exec(*args, **kwargs):
            outer.remote_cmd = args[-1]
            return FakeProc()

        monkeypatch.setattr("app.routers.files._get_user_pod", fake_get_user_pod)
        monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
        monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_exec)
        return self


@pytest.mark.parametrize("path", ["/", "//", "/.", "/home/.."])
def test_reject_root_delete_blocks_filesystem_root(path):
    with pytest.raises(HTTPException) as exc:
        _reject_root_delete(path)
    assert exc.value.status_code == 400


def test_reject_root_delete_allows_normal_paths():
    for path in ("/home/student/file.txt", "/workspace/data", "/root/x"):
        _reject_root_delete(path)  # must not raise


async def test_mkdir_builds_quoted_command_and_succeeds(monkeypatch):
    cap = _CmdCapture().install(monkeypatch)
    result = await make_directory(
        "pod-1", MkdirRequest(path="/home/new dir"), _payload(), FakeDB(_running_session())
    )
    assert result == {"message": "created", "path": "/home/new dir"}
    assert cap.remote_cmd == "mkdir -- '/home/new dir'"


async def test_mkdir_maps_existing_to_409(monkeypatch):
    _CmdCapture(returncode=1, stderr=b"mkdir: cannot create directory '/home/x': File exists").install(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await make_directory("pod-1", MkdirRequest(path="/home/x"), _payload(), FakeDB(_running_session()))
    assert exc.value.status_code == 409


async def test_rename_builds_mv_command(monkeypatch):
    cap = _CmdCapture().install(monkeypatch)
    result = await rename_entry(
        "pod-1", RenameRequest(path="/home/a.txt", new_path="/home/b.txt"),
        _payload(), FakeDB(_running_session()),
    )
    assert result == {"message": "renamed", "path": "/home/a.txt", "new_path": "/home/b.txt"}
    # shlex.quote leaves special-char-free paths unquoted.
    assert cap.remote_cmd == "mv -- /home/a.txt /home/b.txt"


async def test_rename_maps_missing_to_404(monkeypatch):
    _CmdCapture(returncode=1, stderr=b"mv: cannot stat '/home/a.txt': No such file or directory").install(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await rename_entry(
            "pod-1", RenameRequest(path="/home/a.txt", new_path="/home/b.txt"),
            _payload(), FakeDB(_running_session()),
        )
    assert exc.value.status_code == 404


async def test_delete_builds_recursive_rm(monkeypatch):
    cap = _CmdCapture().install(monkeypatch)
    result = await delete_entry(
        "pod-1", DeleteRequest(path="/home/data"), _payload(), FakeDB(_running_session())
    )
    assert result == {"message": "deleted", "path": "/home/data"}
    assert cap.remote_cmd == "rm -r -- /home/data"


async def test_delete_rejects_root_before_ssh(monkeypatch):
    cap = _CmdCapture().install(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await delete_entry("pod-1", DeleteRequest(path="/"), _payload(), FakeDB(_running_session()))
    assert exc.value.status_code == 400
    assert cap.remote_cmd is None  # guard fired before any ssh call


async def test_delete_quotes_injection_attempt(monkeypatch):
    # A path crafted to break out of the command must be fully single-quoted,
    # so the whole thing is passed to rm as one literal argument.
    cap = _CmdCapture().install(monkeypatch)
    evil = "/home/x'; rm -rf / #"
    await delete_entry("pod-1", DeleteRequest(path=evil), _payload(), FakeDB(_running_session()))
    assert cap.remote_cmd == "rm -r -- " + __import__("shlex").quote(evil)
    # The dangerous substring is inside quotes, not a second command.
    assert "rm -rf /" not in cap.remote_cmd.replace(__import__("shlex").quote(evil), "")


async def test_delete_maps_permission_denied_to_403(monkeypatch):
    _CmdCapture(returncode=1, stderr=b"rm: cannot remove '/root/x': Permission denied").install(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await delete_entry("pod-1", DeleteRequest(path="/root/x"), _payload(), FakeDB(_running_session()))
    assert exc.value.status_code == 403
