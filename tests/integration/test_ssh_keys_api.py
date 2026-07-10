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
from app.models import SSHKey
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
async def test_add_and_list_ssh_key(client):
    public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"

    add_response = await client.post(
        "/ssh-keys/",
        json={"name": "Laptop", "public_key": public_key},
    )

    assert add_response.status_code == 201
    fingerprint = add_response.json()["fingerprint"]
    assert fingerprint.startswith("SHA256:")

    list_response = await client.get("/ssh-keys/")

    assert list_response.status_code == 200
    keys = list_response.json()
    assert len(keys) == 1
    assert keys[0]["name"] == "Laptop"
    assert keys[0]["fingerprint"] == fingerprint
    assert keys[0]["public_key"].endswith("...")


@pytest.mark.asyncio
async def test_add_ssh_key_rejects_duplicate_for_same_user(client):
    public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"

    first_response = await client.post(
        "/ssh-keys/",
        json={"name": "Laptop", "public_key": public_key},
    )
    second_response = await client.post(
        "/ssh-keys/",
        json={"name": "Laptop Copy", "public_key": public_key},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "This SSH key is already on your account"}


@pytest.mark.asyncio
async def test_delete_ssh_key_removes_it(client, db_session):
    db_session.add(
        SSHKey(
            id="key-1",
            user_id="student-1",
            name="Laptop",
            public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
            fingerprint="SHA256:abc",
        )
    )
    await db_session.commit()

    response = await client.delete("/ssh-keys/key-1")

    assert response.status_code == 200
    assert response.json() == {"message": "deleted"}
    assert await db_session.get(SSHKey, "key-1") is None
