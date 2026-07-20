from io import BytesIO

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.models.session import PodSession
from app.routers.files import (
    DeleteRequest,
    MkdirRequest,
    RenameRequest,
    _get_user_pod,
    _reject_root_delete,
    _safe_path,
    _ssh_endpoint,
    _ssh_exec,
    delete_entry,
    download_file,
    list_directory,
    make_directory,
    rename_entry,
    upload_file,
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


async def test_get_user_pod_rejects_non_running_pod():
    session = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="img",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="creating",
    )

    with pytest.raises(HTTPException) as exc_info:
        await _get_user_pod("pod-1", _payload(), FakeDB(session))

    assert exc_info.value.status_code == 400


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


async def test_ssh_endpoint_raises_when_no_port_forward_or_nodeport(monkeypatch):
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
        state="running",
    )

    monkeypatch.setattr("app.routers.files.port_forward.get_local_port", lambda pod_name, port: None)

    async def fail_start(pod_name, namespace, port):
        raise RuntimeError("no pf")

    monkeypatch.setattr("app.routers.files.port_forward.start", fail_start)

    with pytest.raises(HTTPException) as exc_info:
        await _ssh_endpoint(session)

    assert exc_info.value.status_code == 503


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


async def test_list_directory_maps_common_errors(monkeypatch):
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

    class NotFoundProc:
        returncode = 1

        async def communicate(self):
            return (b"", b"No such file or directory")

    monkeypatch.setattr("app.routers.files._get_user_pod", fake_get_user_pod)
    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    async def fake_create_subprocess_exec(*args, **kwargs):
        return NotFoundProc()

    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(HTTPException) as exc_info:
        await list_directory("pod-1", "/missing", _payload(), FakeDB(session))

    assert exc_info.value.status_code == 404


async def test_upload_file_success_and_error_mapping(monkeypatch):
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

    class SuccessProc:
        returncode = 0

        async def communicate(self):
            return (b"", b"")

    monkeypatch.setattr("app.routers.files._get_user_pod", fake_get_user_pod)
    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    async def fake_create_subprocess_exec(*args, **kwargs):
        return SuccessProc()

    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    file = UploadFile(filename="notes.txt", file=BytesIO(b"hello"))
    result = await upload_file("pod-1", "/home", file, _payload(), FakeDB(session))

    assert result == {"message": "uploaded", "path": "/home/notes.txt", "size": 5}

    class ForbiddenProc:
        returncode = 1

        async def communicate(self):
            return (b"", b"Permission denied")

    async def fake_forbidden_exec(*args, **kwargs):
        return ForbiddenProc()

    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_forbidden_exec)
    file = UploadFile(filename="notes.txt", file=BytesIO(b"hello"))

    with pytest.raises(HTTPException) as exc_info:
        await upload_file("pod-1", "/home", file, _payload(), FakeDB(session))

    assert exc_info.value.status_code == 403


async def test_download_file_success_and_error_mapping(monkeypatch, tmp_path):
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

    class SuccessProc:
        returncode = 0

        async def communicate(self):
            return (b"", b"")

    target_path = tmp_path / "download.bin"

    class TempFileCtx:
        def __init__(self, path):
            self.name = str(path)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_tempfile(*args, **kwargs):
        return TempFileCtx(target_path)

    async def fake_create_subprocess_exec(*args, **kwargs):
        target_path.write_bytes(b"payload")
        return SuccessProc()

    monkeypatch.setattr("app.routers.files._get_user_pod", fake_get_user_pod)
    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    monkeypatch.setattr("app.routers.files.tempfile.NamedTemporaryFile", fake_tempfile)
    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    response = await download_file("pod-1", "/home/data.bin", _payload(), FakeDB(session))
    body = b""
    async for chunk in response.body_iterator:
        body += chunk

    assert body == b"payload"
    assert response.headers["Content-Disposition"] == 'attachment; filename="data.bin"'

    class NotFoundProc:
        returncode = 1

        async def communicate(self):
            return (b"", b"No such file")

    async def fake_not_found_exec(*args, **kwargs):
        return NotFoundProc()

    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_not_found_exec)

    with pytest.raises(HTTPException) as exc_info:
        await download_file("pod-1", "/home/missing.bin", _payload(), FakeDB(session))

    assert exc_info.value.status_code == 404


# --- mkdir / rename / delete (command-style ops via _ssh_exec) ---


def _running_session() -> PodSession:
    return PodSession(
        id="pod-1", user_id="user-1", plan="small", image="img", cpu="1",
        memory="2Gi", namespace="hopper", pod_name="vm-pod-1",
        ssh_password="secret", state="running",
    )


@pytest.mark.parametrize("path", ["/", "//", "/home/.."])
def test_reject_root_delete_blocks_root(path):
    with pytest.raises(HTTPException) as exc_info:
        _reject_root_delete(path)
    assert exc_info.value.status_code == 400


def test_reject_root_delete_allows_normal_path():
    _reject_root_delete("/home/student/file.txt")  # must not raise


def _spy_ssh_exec(monkeypatch, returncode, stderr=b""):
    async def fake_ssh_exec(session, remote_cmd):
        fake_ssh_exec.cmd = remote_cmd
        return (returncode, b"", stderr)
    monkeypatch.setattr("app.routers.files._ssh_exec", fake_ssh_exec)
    return fake_ssh_exec


def _patch_pod(monkeypatch, session):
    async def fake_get_user_pod(pod_id, user, db):
        return session
    monkeypatch.setattr("app.routers.files._get_user_pod", fake_get_user_pod)


async def test_make_directory_success(monkeypatch):
    session = _running_session()
    _patch_pod(monkeypatch, session)
    spy = _spy_ssh_exec(monkeypatch, 0)

    result = await make_directory("pod-1", MkdirRequest(path="/home/newdir"), _payload(), FakeDB(session))

    assert result == {"message": "created", "path": "/home/newdir"}
    assert spy.cmd.startswith("mkdir") and "/home/newdir" in spy.cmd


async def test_make_directory_conflict_on_existing(monkeypatch):
    session = _running_session()
    _patch_pod(monkeypatch, session)
    _spy_ssh_exec(monkeypatch, 1, b"mkdir: cannot create directory '/home/x': File exists")

    with pytest.raises(HTTPException) as exc_info:
        await make_directory("pod-1", MkdirRequest(path="/home/x"), _payload(), FakeDB(session))
    assert exc_info.value.status_code == 409


async def test_rename_entry_success(monkeypatch):
    session = _running_session()
    _patch_pod(monkeypatch, session)
    spy = _spy_ssh_exec(monkeypatch, 0)

    result = await rename_entry(
        "pod-1", RenameRequest(path="/home/a", new_path="/home/b"), _payload(), FakeDB(session)
    )

    assert result == {"message": "renamed", "path": "/home/a", "new_path": "/home/b"}
    assert spy.cmd.startswith("mv")


async def test_delete_entry_success(monkeypatch):
    session = _running_session()
    _patch_pod(monkeypatch, session)
    spy = _spy_ssh_exec(monkeypatch, 0)

    result = await delete_entry("pod-1", DeleteRequest(path="/home/junk"), _payload(), FakeDB(session))

    assert result == {"message": "deleted", "path": "/home/junk"}
    assert spy.cmd.startswith("rm -r")


async def test_delete_entry_rejects_root(monkeypatch):
    session = _running_session()
    _patch_pod(monkeypatch, session)

    async def boom(*a, **k):
        raise AssertionError("_ssh_exec must not run for a root delete")
    monkeypatch.setattr("app.routers.files._ssh_exec", boom)

    with pytest.raises(HTTPException) as exc_info:
        await delete_entry("pod-1", DeleteRequest(path="/"), _payload(), FakeDB(session))
    assert exc_info.value.status_code == 400
