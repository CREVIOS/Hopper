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
        "university_id": None,
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


@pytest.mark.asyncio
async def test_delete_account_removes_user_but_preserves_ledger(client, db_session, monkeypatch):
    from datetime import datetime

    from app.models import (
        Account,
        EmailCode,
        LedgerEntry,
        PodSession,
        SSHKey,
        Transfer,
        UserSetting,
        UserWorkspace,
    )

    # Seed the user + all their operational data.
    db_session.add(User(id="student-1", email="student1@cs.du.ac.bd", name="Student One", role="student"))
    db_session.add(SSHKey(id="k1", user_id="student-1", name="laptop", public_key="ssh-ed25519 AAAA", fingerprint="fp1"))
    db_session.add(UserSetting(id="s1", user_id="student-1", vscode={"theme": "dark"}))
    db_session.add(UserWorkspace(id="w1", user_id="student-1", pvc_name="ws-student-1", capacity_gb=20))
    db_session.add(EmailCode(id="e1", email="student1@cs.du.ac.bd", purpose="verify_email", code_hash="h", expires_at=datetime(2999, 1, 1)))
    db_session.add(PodSession(
        id="pod-1", user_id="student-1", plan="small", image="img", cpu="1", memory="2Gi",
        namespace="hopper", pod_name="vm-pod-1", state="running",
    ))
    # Seed an immutable ledger record that must survive deletion.
    db_session.add(Account(id="acct-1", name="student-1 wallet", type="asset", owner_id="student-1", owner_type="user"))
    db_session.add(Transfer(id="t1", type="grant", metadata_={}, event_at=datetime(2026, 1, 1)))
    db_session.add(LedgerEntry(
        id="le1", transfer_id="t1", account_id="acct-1", direction=-1, amount=10,
        previous_balance=0, current_balance=10, event_at=datetime(2026, 1, 1),
    ))
    await db_session.commit()

    terminated = {}

    async def fake_terminate_pod(pod_name):
        terminated["pod"] = pod_name
        return True

    async def fake_delete_user(uid):
        terminated["kc"] = uid

    async def fake_stop(pod_name):
        pass

    monkeypatch.setattr("app.routers.auth.orchestrator_client.terminate_pod", fake_terminate_pod)
    monkeypatch.setattr("app.routers.auth.keycloak_admin.delete_user", fake_delete_user)
    monkeypatch.setattr("app.routers.auth.port_forward.stop", fake_stop)

    response = await client.request(
        "DELETE", "/auth/me", json={"confirm_email": "student1@cs.du.ac.bd"}
    )

    assert response.status_code == 200
    assert terminated == {"pod": "vm-pod-1", "kc": "student-1"}

    db_session.expire_all()

    # User + operational rows are gone.
    assert (await db_session.execute(select(User).where(User.id == "student-1"))).scalar_one_or_none() is None
    assert (await db_session.execute(select(SSHKey).where(SSHKey.user_id == "student-1"))).scalars().all() == []
    assert (await db_session.execute(select(UserSetting).where(UserSetting.user_id == "student-1"))).scalars().all() == []
    assert (await db_session.execute(select(UserWorkspace).where(UserWorkspace.user_id == "student-1"))).scalars().all() == []
    assert (await db_session.execute(select(EmailCode).where(EmailCode.email == "student1@cs.du.ac.bd"))).scalars().all() == []

    # The VM session is marked terminated.
    pod = (await db_session.execute(select(PodSession).where(PodSession.id == "pod-1"))).scalar_one()
    assert pod.state == "terminated"

    # The immutable ledger is preserved.
    assert (await db_session.execute(select(LedgerEntry).where(LedgerEntry.id == "le1"))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(Account).where(Account.id == "acct-1"))).scalar_one_or_none() is not None

    # An account.delete audit row was written.
    audit = (await db_session.execute(
        select(AuditLog).where(AuditLog.user_id == "student-1", AuditLog.action == "account.delete")
    )).scalar_one()
    assert audit.resource_type == "user"


@pytest.mark.asyncio
async def test_delete_account_rejects_email_mismatch(client, db_session, monkeypatch):
    db_session.add(User(id="student-1", email="student1@cs.du.ac.bd", name="Student One", role="student"))
    await db_session.commit()

    called = {"kc": False}

    async def fake_delete_user(uid):
        called["kc"] = True

    monkeypatch.setattr("app.routers.auth.keycloak_admin.delete_user", fake_delete_user)

    response = await client.request("DELETE", "/auth/me", json={"confirm_email": "wrong@e.com"})

    assert response.status_code == 400
    assert called["kc"] is False
    db_session.expire_all()
    assert (await db_session.execute(select(User).where(User.id == "student-1"))).scalar_one_or_none() is not None
