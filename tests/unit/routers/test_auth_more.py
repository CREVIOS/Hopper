from datetime import datetime

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from app.models.api_key import ApiKey
from app.models.user import User
from app.routers import auth as auth_router
from app.schemas.api_key import CreateApiKeyRequest
from app.schemas.user import (
    ForgotPasswordRequest,
    LoginRequest,
    ResendCodeRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenPayload,
    VerifyEmailRequest,
)


def _payload() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="User One",
        role="student",
        exp=1234567890,
        email_verified=True,
    )


def _request(*, cookies=None, client_host="127.0.0.1"):
    headers = []
    if cookies:
        headers.append((b"cookie", cookies.encode()))
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/test",
            "headers": headers,
            "client": (client_host, 12345),
        }
    )
    req.state.api_key_auth = False
    return req


class FakeResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class FakeDB:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])
        self.added = []
        self.commits = 0

    async def execute(self, stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        row = self.execute_results.pop(0)
        return FakeResult(row)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


async def test_signup_student_and_teacher_paths(monkeypatch):
    async def fake_create_user(**kwargs):
        return "user-1"

    async def fake_issue_code(db, email, purpose):
        return "123456"

    async def fake_get_or_create_account(db, user_id):
        return None

    sent = {}

    async def fake_send_code_email(email, purpose, code):
        sent["email"] = email
        sent["purpose"] = purpose
        sent["code"] = code

    monkeypatch.setattr("app.routers.auth.keycloak_admin.create_user", fake_create_user)
    monkeypatch.setattr("app.routers.auth.verification.issue_code", fake_issue_code)
    monkeypatch.setattr("app.routers.auth.get_or_create_account", fake_get_or_create_account)
    monkeypatch.setattr("app.routers.auth.send_code_email", fake_send_code_email)
    monkeypatch.setattr("app.routers.auth._check_password", lambda password, email: None)
    monkeypatch.setattr("app.routers.auth._domain_allowed", lambda email: True)

    db = FakeDB()
    response = await auth_router.signup.__wrapped__(
        _request(),
        SignupRequest(email="Student@Example.com", password="StrongPass123", name="Student", role="student"),
        db,
    )
    assert response.status_code == 200
    assert db.commits == 1
    assert sent["email"] == "student@example.com"

    db = FakeDB()
    response = await auth_router.signup.__wrapped__(
        _request(),
        SignupRequest(email="Teacher@Example.com", password="StrongPass123", name="Teacher", role="teacher"),
        db,
    )
    assert response.status_code == 202


async def test_signup_rejects_bad_role_domain_and_keycloak_errors(monkeypatch):
    with pytest.raises(HTTPException) as exc_info:
        await auth_router.signup.__wrapped__(
            _request(),
            SignupRequest(email="user@example.com", password="StrongPass123", name="User", role="admin"),
            FakeDB(),
        )
    assert exc_info.value.status_code == 400

    monkeypatch.setattr("app.routers.auth._domain_allowed", lambda email: False)
    with pytest.raises(HTTPException) as exc_info:
        await auth_router.signup.__wrapped__(
            _request(),
            SignupRequest(email="user@example.com", password="StrongPass123", name="User", role="student"),
            FakeDB(),
        )
    assert exc_info.value.status_code == 403


async def test_verify_email_paths(monkeypatch):
    async def fake_verify_code(db, email, purpose, code):
        return True

    async def fake_set_verified(user_id, value):
        return None

    monkeypatch.setattr("app.routers.auth.verification.verify_code", fake_verify_code)
    monkeypatch.setattr("app.routers.auth.keycloak_admin.set_email_verified", fake_set_verified)

    user = User(id="user-1", email="user@example.com", name="User", role="student")
    db = FakeDB(execute_results=[user])
    response = await auth_router.verify_email.__wrapped__(
        _request(), VerifyEmailRequest(email="USER@example.com", code="123456"), db
    )
    assert response.status_code == 200
    assert db.commits == 1

    async def fake_verify_bad(db, email, purpose, code):
        return False

    monkeypatch.setattr("app.routers.auth.verification.verify_code", fake_verify_bad)
    db = FakeDB()
    with pytest.raises(HTTPException) as exc_info:
        await auth_router.verify_email.__wrapped__(_request(), VerifyEmailRequest(email="user@example.com", code="123456"), db)
    assert exc_info.value.status_code == 400


async def test_resend_and_forgot_password_are_enumeration_safe(monkeypatch):
    async def fake_get_user_by_email(email):
        return {"id": "user-1", "emailVerified": False}

    async def fake_issue_code(db, email, purpose):
        return "123456"

    async def fake_send_code_email(email, purpose, code):
        return None

    monkeypatch.setattr("app.routers.auth.keycloak_admin.get_user_by_email", fake_get_user_by_email)
    monkeypatch.setattr("app.routers.auth.verification.issue_code", fake_issue_code)
    monkeypatch.setattr("app.routers.auth.send_code_email", fake_send_code_email)

    db = FakeDB()
    response = await auth_router.resend_code.__wrapped__(_request(), ResendCodeRequest(email="user@example.com"), db)
    assert response.status_code == 200
    assert db.commits == 1

    db = FakeDB()
    response = await auth_router.forgot_password.__wrapped__(_request(), ForgotPasswordRequest(email="user@example.com"), db)
    assert response.status_code == 200
    assert db.commits == 1


async def test_reset_password_paths(monkeypatch):
    monkeypatch.setattr("app.routers.auth._check_password", lambda password, email: None)

    async def fake_verify_code(db, email, purpose, code):
        return True

    async def fake_get_user_by_email(email):
        return {"id": "user-1", "emailVerified": False}

    async def fake_reset_password(user_id, password):
        return None

    async def fake_set_verified(user_id, value):
        return None

    monkeypatch.setattr("app.routers.auth.verification.verify_code", fake_verify_code)
    monkeypatch.setattr("app.routers.auth.keycloak_admin.get_user_by_email", fake_get_user_by_email)
    monkeypatch.setattr("app.routers.auth.keycloak_admin.reset_password", fake_reset_password)
    monkeypatch.setattr("app.routers.auth.keycloak_admin.set_email_verified", fake_set_verified)

    db = FakeDB()
    response = await auth_router.reset_password.__wrapped__(
        _request(),
        ResetPasswordRequest(email="user@example.com", code="123456", password="StrongPass123"),
        db,
    )
    assert response.status_code == 200
    assert db.commits == 1

    async def fake_verify_bad(db, email, purpose, code):
        return False

    monkeypatch.setattr("app.routers.auth.verification.verify_code", fake_verify_bad)
    db = FakeDB()
    with pytest.raises(HTTPException) as exc_info:
        await auth_router.reset_password.__wrapped__(
            _request(),
            ResetPasswordRequest(email="user@example.com", code="123456", password="StrongPass123"),
            db,
        )
    assert exc_info.value.status_code == 400


async def test_login_direct_me_and_logout_paths(monkeypatch):
    async def fake_password_grant(email, password):
        return {"access_token": "access", "refresh_token": "refresh", "expires_in": 300, "refresh_expires_in": 1800}

    monkeypatch.setattr("app.routers.auth._password_grant", fake_password_grant)
    async def fake_verify_token(token):
        return _payload()

    monkeypatch.setattr("app.routers.auth.verify_token", fake_verify_token)
    monkeypatch.setattr("app.routers.auth._domain_allowed", lambda email: True)
    monkeypatch.setattr("app.routers.auth.clear_login_failures", lambda ip, email: None)
    monkeypatch.setattr("app.routers.auth.login_blocked", lambda ip, email: False)
    monkeypatch.setattr("app.routers.auth.get_remote_address", lambda request: "127.0.0.1")
    async def fake_upsert(db, payload):
        return None

    monkeypatch.setattr("app.routers.auth._upsert_user_row", fake_upsert)
    monkeypatch.setattr("app.routers.auth.settings.require_email_verified", True)

    response = await auth_router.login_direct.__wrapped__(
        _request(),
        LoginRequest(email="user@example.com", password="pw"),
        FakeDB(),
    )
    assert response.status_code == 200

    user = User(id="user-1", email="user@example.com", name="User", role="student", pending_teacher=True)
    response = await auth_router.me(current_user=_payload(), db=FakeDB(execute_results=[user]))
    assert response.pending_teacher is True

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data):
            return Response(status_code=200)

    monkeypatch.setattr("app.routers.auth.httpx.AsyncClient", lambda timeout: FakeClient())
    monkeypatch.setattr("app.routers.auth.settings.frontend_url", "http://frontend.test")
    request = _request(cookies="refresh_token=ref; id_token=id")
    response = await auth_router.logout(request)
    assert response.status_code == 302
    assert response.headers["location"].startswith(auth_router.KEYCLOAK_LOGOUT_URL)


async def test_callback_and_api_key_routes(monkeypatch):
    request = _request(cookies="oauth_state=expected.nonce; oauth_pkce=verifier")
    request._url = request.url.replace(path="/auth/callback")

    class FakeHTTPResponse:
        def __init__(self, status_code=200, json_body=None, text=""):
            self.status_code = status_code
            self._json_body = json_body or {}
            self.text = text

        def json(self):
            return self._json_body

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data):
            return FakeHTTPResponse(
                200,
                {
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "id_token": "id-token",
                    "expires_in": 300,
                    "refresh_expires_in": 1800,
                },
            )

    monkeypatch.setattr("app.routers.auth.httpx.AsyncClient", lambda timeout: FakeClient())
    async def fake_verify_token(token):
        return _payload()

    monkeypatch.setattr("app.routers.auth.verify_token", fake_verify_token)
    monkeypatch.setattr("app.routers.auth._domain_allowed", lambda email: True)
    monkeypatch.setattr("app.routers.auth.settings.require_email_verified", True)
    monkeypatch.setattr("app.routers.auth.settings.frontend_url", "http://frontend.test")
    async def fake_account(db, user_id):
        return None

    monkeypatch.setattr("app.routers.auth.get_or_create_account", fake_account)

    db = FakeDB(execute_results=[None])
    response = await auth_router.callback.__wrapped__(request, code="abc", state="expected", error=None, db=db)
    assert response.status_code == 307 or response.status_code == 302

    req = _request()
    req.state.api_key_auth = True
    with pytest.raises(HTTPException) as exc_info:
        await auth_router.create_api_key.__wrapped__(
            req,
            Response(),
            CreateApiKeyRequest(name="CLI", scope="read_only"),
            _payload(),
            FakeDB(),
        )
    assert exc_info.value.status_code == 403

    req = _request()
    req.state.api_key_auth = False

    async def fake_create_key(db, user_id, name, scope):
        return (
            ApiKey(
                id="key-1",
                user_id=user_id,
                name=name,
                prefix="hop_prefix",
                key_hash="hash",
                scope=scope,
                created_at=datetime(2026, 1, 1, 12, 0, 0),
            ),
            "hop_secret",
        )

    monkeypatch.setattr("app.routers.auth.api_key_service.create_key", fake_create_key)
    db = FakeDB()
    response = await auth_router.create_api_key.__wrapped__(
        req,
        Response(),
        CreateApiKeyRequest(name="CLI", scope="read_only"),
        _payload(),
        db,
    )
    assert response.key == "hop_secret"
    assert db.commits == 1

    async def fake_list_keys(db, user_id):
        return [
            ApiKey(
                id="key-1",
                user_id=user_id,
                name="CLI",
                prefix="hop_prefix",
                key_hash="hash",
                scope="read_only",
                created_at=datetime(2026, 1, 1, 12, 0, 0),
            )
        ]

    monkeypatch.setattr("app.routers.auth.api_key_service.list_keys", fake_list_keys)
    rows = await auth_router.list_api_keys(current_user=_payload(), db=FakeDB())
    assert rows[0].id == "key-1"

    async def fake_revoke_key(db, user_id, key_id):
        return key_id == "key-1"

    monkeypatch.setattr("app.routers.auth.api_key_service.revoke_key", fake_revoke_key)
    response = await auth_router.revoke_api_key("key-1", req, _payload(), FakeDB())
    assert response.status_code == 204
