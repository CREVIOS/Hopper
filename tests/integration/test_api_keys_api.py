"""Integration tests for API keys (HOP-19 18.1).

Unlike most integration suites, these do NOT override get_current_user for
the key-authenticated requests — exercising the real X-API-Key resolution
path (hash lookup, scope enforcement, session-only key management) against a
real Postgres is the point.
"""
from pathlib import Path
import sys

import httpx
import pytest
import pytest_asyncio
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import app.dependencies as dependencies_module
from app.dependencies import get_current_user, get_db
from app.main import create_app
from app.middleware import audit as audit_middleware
from app.models import ApiKey, User
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


SESSION_USER = TokenPayload(
    sub="student-1",
    email="student1@example.com",
    name="Student One",
    role="student",
    exp=4_102_444_800,
    email_verified=True,
)


@pytest_asyncio.fixture
async def client(db_session):
    """App client where COOKIE auth is stubbed to SESSION_USER but API-key
    headers hit the real resolution path against the test database."""
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    app = create_app()

    original_audit_session = audit_middleware.async_session
    original_dep_session = dependencies_module.async_session

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def hybrid_get_current_user(request: Request):
        # Real path for API keys; stubbed session identity otherwise (no
        # Keycloak in the test rig).
        api_key = dependencies_module._api_key_from_request(request)
        if api_key:
            return await dependencies_module._user_from_api_key(request, api_key)
        return SESSION_USER

    audit_middleware.async_session = session_factory
    dependencies_module.async_session = session_factory
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = hybrid_get_current_user

    # The key's owner must exist — _user_from_api_key resolves role/email
    # from the users row.
    db_session.add(
        User(id=SESSION_USER.sub, email=SESSION_USER.email, name=SESSION_USER.name, role="student")
    )
    await db_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    audit_middleware.async_session = original_audit_session
    dependencies_module.async_session = original_dep_session


@pytest.mark.asyncio
async def test_create_key_returns_secret_once_and_stores_only_hash(client, db_session):
    response = await client.post(
        "/auth/api-keys", json={"name": "ci-bot", "scope": "read_only"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["key"].startswith("hop_")
    assert body["scope"] == "read_only"
    assert body["prefix"] == body["key"][: len(body["prefix"])]

    row = (await db_session.execute(select(ApiKey))).scalar_one()
    assert row.key_hash != body["key"]
    assert body["key"] not in (row.key_hash, row.prefix)

    # The list view never exposes the secret.
    listing = await client.get("/auth/api-keys")
    assert listing.status_code == 200
    assert "key" not in listing.json()[0]


@pytest.mark.asyncio
async def test_read_only_key_reads_but_cannot_mutate(client):
    created = (
        await client.post("/auth/api-keys", json={"name": "ro", "scope": "read_only"})
    ).json()
    headers = {"X-API-Key": created["key"]}

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == SESSION_USER.email

    denied = await client.post(
        "/pods/", json={"plan": "small"}, headers=headers
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "This API key is read-only"


@pytest.mark.asyncio
async def test_api_key_cannot_manage_api_keys(client):
    created = (
        await client.post("/auth/api-keys", json={"name": "fa", "scope": "full_access"})
    ).json()
    headers = {"X-API-Key": created["key"]}

    minted = await client.post(
        "/auth/api-keys", json={"name": "evil", "scope": "full_access"}, headers=headers
    )
    assert minted.status_code == 403

    revoked = await client.delete(f"/auth/api-keys/{created['id']}", headers=headers)
    assert revoked.status_code == 403


@pytest.mark.asyncio
async def test_revoked_key_stops_authenticating(client):
    created = (
        await client.post("/auth/api-keys", json={"name": "temp", "scope": "read_only"})
    ).json()
    headers = {"X-API-Key": created["key"]}

    assert (await client.get("/auth/me", headers=headers)).status_code == 200

    # Revoke via session auth (no API-key header).
    assert (await client.delete(f"/auth/api-keys/{created['id']}")).status_code == 204

    rejected = await client.get("/auth/me", headers=headers)
    assert rejected.status_code == 401
    assert rejected.json()["detail"] == "Invalid or revoked API key"


@pytest.mark.asyncio
async def test_garbage_key_rejected(client):
    response = await client.get("/auth/me", headers={"X-API-Key": "hop_not-a-real-key"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_scope_rejected(client):
    response = await client.post(
        "/auth/api-keys", json={"name": "bad", "scope": "superuser"}
    )
    assert response.status_code == 422
