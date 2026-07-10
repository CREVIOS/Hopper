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


class FakeProc:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


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
async def test_list_directory_parses_entries_and_sorts_results(client, db_session, monkeypatch):
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
            ssh_password="secret",
            state="running",
        )
    )
    await db_session.commit()

    async def fake_ssh_endpoint(session):
        return ("127.0.0.1", 51000)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc(
            stdout=(
                b"total 8\n-rw-r--r-- 1 root root 12 2026-01-01 12:00 file.txt\n"
                b"drwxr-xr-x 2 root root 4096 2026-01-01 11:00 data\n"
            )
        )

    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    response = await client.get("/files/pod-1/list", params={"path": "/home"})

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "/home"
    assert body["entries"][0]["name"] == "data"
    assert body["entries"][1]["name"] == "file.txt"


@pytest.mark.asyncio
async def test_upload_file_returns_uploaded_metadata(client, db_session, monkeypatch):
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
            ssh_password="secret",
            state="running",
        )
    )
    await db_session.commit()

    async def fake_ssh_endpoint(session):
        return ("127.0.0.1", 51000)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    response = await client.post(
        "/files/pod-1/upload",
        params={"dest_path": "/home"},
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "uploaded",
        "path": "/home/notes.txt",
        "size": 11,
    }


@pytest.mark.asyncio
async def test_download_file_streams_downloaded_content(client, db_session, monkeypatch):
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
            ssh_password="secret",
            state="running",
        )
    )
    await db_session.commit()

    async def fake_ssh_endpoint(session):
        return ("127.0.0.1", 51000)

    async def fake_create_subprocess_exec(*args, **kwargs):
        destination = args[-1]
        with open(destination, "wb") as handle:
            handle.write(b"downloaded content")
        return FakeProc()

    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    response = await client.get("/files/pod-1/download", params={"path": "/home/file.txt"})

    assert response.status_code == 200
    assert response.content == b"downloaded content"
    assert response.headers["content-disposition"] == 'attachment; filename="file.txt"'


@pytest.mark.asyncio
async def test_list_directory_rejects_invalid_path(client):
    response = await client.get("/files/pod-1/list", params={"path": "bad\npath"})

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid path"}


@pytest.mark.asyncio
async def test_download_file_rejects_other_users_pod(client, db_session):
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
            ssh_password="secret",
            state="running",
        )
    )
    await db_session.commit()

    response = await client.get("/files/pod-1/download", params={"path": "/home/file.txt"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Not your pod"}


# --- mkdir / rename / delete --------------------------------------------------

def _seed_running_pod(db_session):
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
            ssh_password="secret",
            state="running",
        )
    )


@pytest.mark.asyncio
async def test_mkdir_creates_directory(client, db_session, monkeypatch):
    _seed_running_pod(db_session)
    await db_session.commit()

    async def fake_ssh_endpoint(session):
        return ("127.0.0.1", 51000)

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_exec)

    response = await client.post("/files/pod-1/mkdir", json={"path": "/home/newdir"})

    assert response.status_code == 200
    assert response.json() == {"message": "created", "path": "/home/newdir"}


@pytest.mark.asyncio
async def test_mkdir_existing_returns_409(client, db_session, monkeypatch):
    _seed_running_pod(db_session)
    await db_session.commit()

    async def fake_ssh_endpoint(session):
        return ("127.0.0.1", 51000)

    async def fake_exec(*args, **kwargs):
        return FakeProc(stderr=b"mkdir: cannot create directory '/home/x': File exists", returncode=1)

    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_exec)

    response = await client.post("/files/pod-1/mkdir", json={"path": "/home/x"})

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_rename_moves_entry(client, db_session, monkeypatch):
    _seed_running_pod(db_session)
    await db_session.commit()

    async def fake_ssh_endpoint(session):
        return ("127.0.0.1", 51000)

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_exec)

    response = await client.post(
        "/files/pod-1/rename", json={"path": "/home/a.txt", "new_path": "/home/b.txt"}
    )

    assert response.status_code == 200
    assert response.json() == {"message": "renamed", "path": "/home/a.txt", "new_path": "/home/b.txt"}


@pytest.mark.asyncio
async def test_delete_removes_entry(client, db_session, monkeypatch):
    _seed_running_pod(db_session)
    await db_session.commit()

    async def fake_ssh_endpoint(session):
        return ("127.0.0.1", 51000)

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_exec)

    response = await client.post("/files/pod-1/delete", json={"path": "/home/data"})

    assert response.status_code == 200
    assert response.json() == {"message": "deleted", "path": "/home/data"}


@pytest.mark.asyncio
async def test_delete_refuses_filesystem_root(client, db_session, monkeypatch):
    _seed_running_pod(db_session)
    await db_session.commit()

    called = {"exec": False}

    async def fake_ssh_endpoint(session):
        return ("127.0.0.1", 51000)

    async def fake_exec(*args, **kwargs):
        called["exec"] = True
        return FakeProc()

    monkeypatch.setattr("app.routers.files._ssh_endpoint", fake_ssh_endpoint)
    monkeypatch.setattr("app.routers.files.asyncio.create_subprocess_exec", fake_exec)

    response = await client.post("/files/pod-1/delete", json={"path": "/"})

    assert response.status_code == 400
    assert called["exec"] is False  # guard fired before any ssh


@pytest.mark.asyncio
async def test_delete_rejects_other_users_pod(client, db_session):
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
            ssh_password="secret",
            state="running",
        )
    )
    await db_session.commit()

    response = await client.post("/files/pod-1/delete", json={"path": "/home/x"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Not your pod"}
