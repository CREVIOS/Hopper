from pathlib import Path
import sys

import httpx
import pytest
import pytest_asyncio
from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.dependencies import get_current_user, get_db
from app.main import create_app
from app.middleware import audit as audit_middleware
from app.models import AuditLog, User
from app.schemas.user import TokenPayload


class FakeHTTPResponse:
    def __init__(self, *, status_code: int, json_body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text

    def json(self) -> dict:
        return self._json_body


class FakeAsyncClient:
    def __init__(self, response: FakeHTTPResponse):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, data=None):
        self.calls.append((url, data))
        return self.response


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
async def test_auth_login_redirect_sets_pkce_and_state_cookies(client):
    response = await client.get("/auth/login")

    assert response.status_code in (302, 307)
    assert "openid+email+profile" in response.headers["location"]
    cookies = response.headers.get_list("set-cookie")
    assert any(cookie.startswith("oauth_state=") for cookie in cookies)
    assert any(cookie.startswith("oauth_pkce=") for cookie in cookies)


@pytest.mark.asyncio
async def test_auth_signup_creates_pending_teacher_user_and_audit_log(client, db_session, monkeypatch):
    async def fake_create_user(email, name, password, role, email_verified):
        assert email == "teacher@cs.du.ac.bd"
        assert role == "student"
        return "teacher-1"

    async def fake_password_grant(email, password):
        assert email == "teacher@cs.du.ac.bd"
        return {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 300,
            "refresh_expires_in": 1800,
        }

    monkeypatch.setattr("app.routers.auth.keycloak_admin.create_user", fake_create_user)
    monkeypatch.setattr("app.routers.auth._password_grant", fake_password_grant)

    response = await client.post(
        "/auth/signup",
        json={
            "email": "teacher@cs.du.ac.bd",
            "password": "strongpass123",
            "name": "Teacher One",
            "role": "teacher",
        },
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    body = response.json()
    assert body["id"] == "teacher-1"
    assert body["role"] == "student"
    assert body["pending_teacher"] is True

    user = await db_session.get(User, "teacher-1")
    assert user is not None
    assert user.pending_teacher is True

    audit_log = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.user_id == "teacher-1", AuditLog.action == "signup")
        )
    ).scalar_one()
    assert audit_log.resource_type == "user"


@pytest.mark.asyncio
async def test_auth_login_direct_upserts_user_and_sets_session_cookies(client, db_session, monkeypatch):
    async def fake_password_grant(email, password):
        assert email == "student1@cs.du.ac.bd"
        assert password == "strongpass123"
        return {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 300,
            "refresh_expires_in": 1800,
            "id_token": "id-1",
        }

    async def fake_verify_token(token):
        assert token == "access-1"
        return TokenPayload(
            sub="student-1",
            email="student1@cs.du.ac.bd",
            name="Student One",
            role="student",
            exp=4_102_444_800,
            email_verified=True,
        )

    monkeypatch.setattr("app.routers.auth._password_grant", fake_password_grant)
    monkeypatch.setattr("app.routers.auth.verify_token", fake_verify_token)

    response = await client.post(
        "/auth/login",
        json={"email": "student1@cs.du.ac.bd", "password": "strongpass123"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": "student-1",
        "email": "student1@cs.du.ac.bd",
        "name": "Student One",
        "role": "student",
    }
    cookies = response.headers.get_list("set-cookie")
    assert any(cookie.startswith("session_token=access-1") for cookie in cookies)
    assert any(cookie.startswith("refresh_token=refresh-1") for cookie in cookies)

    user = await db_session.get(User, "student-1")
    assert user is not None
    assert user.email == "student1@cs.du.ac.bd"


@pytest.mark.asyncio
async def test_auth_me_returns_pending_teacher_flag(client, db_session):
    db_session.add(
        User(
            id="student-1",
            email="student1@cs.du.ac.bd",
            name="Student One",
            role="student",
            pending_teacher=True,
        )
    )
    await db_session.commit()

    response = await client.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": "student-1",
        "email": "student1@cs.du.ac.bd",
        "name": "Student One",
        "role": "student",
        "pending_teacher": True,
    }


@pytest.mark.asyncio
async def test_auth_callback_rejects_state_mismatch(client):
    response = await client.get(
        "/auth/callback",
        params={"code": "code-1", "state": "wrong-state"},
        cookies={"oauth_state": "expected-state.nonce-1", "oauth_pkce": "pkce-verifier"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "state mismatch"}


@pytest.mark.asyncio
async def test_auth_refresh_rejects_forbidden_origin(client):
    response = await client.post(
        "/auth/refresh",
        headers={"origin": "http://evil.example.com"},
        cookies={"refresh_token": "refresh-1"},
    )

    assert response.status_code == 403
    assert response.text == '{"detail":"forbidden origin"}'


@pytest.mark.asyncio
async def test_auth_refresh_uses_refresh_cookie_and_returns_new_session(client, monkeypatch):
    fake_client = FakeAsyncClient(
        FakeHTTPResponse(
            status_code=200,
            json_body={
                "access_token": "access-2",
                "refresh_token": "refresh-2",
                "expires_in": 300,
                "refresh_expires_in": 1800,
            },
        )
    )
    monkeypatch.setattr("app.routers.auth.httpx.AsyncClient", lambda timeout: fake_client)

    response = await client.post(
        "/auth/refresh",
        headers={"origin": "http://localhost:5173"},
        cookies={"refresh_token": "refresh-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "refreshed"}
    cookies = response.headers.get_list("set-cookie")
    assert any(cookie.startswith("session_token=access-2") for cookie in cookies)
    assert any(cookie.startswith("refresh_token=refresh-2") for cookie in cookies)


@pytest.mark.asyncio
async def test_auth_logout_revokes_refresh_token_and_redirects(client, monkeypatch):
    fake_client = FakeAsyncClient(FakeHTTPResponse(status_code=200))
    monkeypatch.setattr("app.routers.auth.httpx.AsyncClient", lambda timeout: fake_client)

    response = await client.post(
        "/auth/logout",
        cookies={"refresh_token": "refresh-1", "id_token": "id-token-1"},
    )

    assert response.status_code == 302
    assert "post_logout_redirect_uri=" in response.headers["location"]
    assert "id_token_hint=id-token-1" in response.headers["location"]
    assert fake_client.calls
