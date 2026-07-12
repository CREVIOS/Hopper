from fastapi import HTTPException, Response
from starlette.requests import Request

from app.routers import auth as auth_router
from app.schemas.user import TokenPayload


class FakeHTTPResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text

    def json(self):
        return self._json_body


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, data):
        self.calls.append((url, data))
        return self.response


def test_b64url_strips_padding():
    assert auth_router._b64url(b"\xfb\xef") == "--8"


def test_new_pkce_pair_uses_sha256_challenge(monkeypatch):
    monkeypatch.setattr("app.routers.auth.os.urandom", lambda n: b"a" * n)

    verifier, challenge = auth_router._new_pkce_pair()

    assert verifier
    assert challenge
    assert verifier != challenge


def test_domain_allowed_matches_exact_domain(monkeypatch):
    monkeypatch.setattr("app.routers.auth.settings.allowed_email_domains", ["cs.du.ac.bd"])

    assert auth_router._domain_allowed("student@cs.du.ac.bd") is True
    assert auth_router._domain_allowed("student@evil.cs.du.ac.bd") is False
    assert auth_router._domain_allowed("invalid-email") is False


def test_domain_allowed_accepts_any_domain_when_empty_allowlist(monkeypatch):
    monkeypatch.setattr("app.routers.auth.settings.allowed_email_domains", [])

    assert auth_router._domain_allowed("student@example.com") is True


def test_set_session_cookies_sets_access_and_refresh_tokens():
    response = Response()

    auth_router._set_session_cookies(
        response,
        access_token="access-token",
        access_ttl=300,
        refresh_token="refresh-token",
        refresh_ttl=1800,
    )

    set_cookie = response.headers.getlist("set-cookie")
    assert any("session_token=access-token" in value for value in set_cookie)
    assert any("refresh_token=refresh-token" in value for value in set_cookie)


def test_clear_session_cookies_deletes_expected_cookies():
    response = Response()

    auth_router._clear_session_cookies(response)

    set_cookie = response.headers.getlist("set-cookie")
    assert any("session_token=" in value for value in set_cookie)
    assert any("refresh_token=" in value for value in set_cookie)
    assert any("oauth_state=" in value for value in set_cookie)
    assert any("oauth_pkce=" in value for value in set_cookie)


def test_issue_session_sets_cookies_and_returns_json_body():
    response = auth_router._issue_session(
        {"message": "ok"},
        {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": "id-token",
            "expires_in": 300,
            "refresh_expires_in": 1800,
        },
    )

    assert response.body == b'{"message":"ok"}'
    set_cookie = response.headers.getlist("set-cookie")
    assert any("session_token=access-token" in value for value in set_cookie)
    assert any("refresh_token=refresh-token" in value for value in set_cookie)
    assert any("id_token=id-token" in value for value in set_cookie)


async def test_password_grant_returns_token_payload(monkeypatch):
    fake_client = FakeAsyncClient(
        FakeHTTPResponse(
            status_code=200,
            json_body={"access_token": "token-1", "refresh_token": "refresh-1"},
        )
    )
    monkeypatch.setattr("app.routers.auth.httpx.AsyncClient", lambda timeout: fake_client)

    result = await auth_router._password_grant("student@example.com", "password123")

    assert result == {"access_token": "token-1", "refresh_token": "refresh-1"}
    assert fake_client.calls[0][1]["username"] == "student@example.com"
    assert fake_client.calls[0][1]["password"] == "password123"


async def test_password_grant_raises_401_on_invalid_credentials(monkeypatch):
    fake_client = FakeAsyncClient(FakeHTTPResponse(status_code=401, text="bad creds"))
    monkeypatch.setattr("app.routers.auth.httpx.AsyncClient", lambda timeout: fake_client)

    try:
        await auth_router._password_grant("student@example.com", "wrong")
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "Invalid email or password"
    else:
        raise AssertionError("expected HTTPException")


async def test_password_grant_raises_401_on_non_success_response(monkeypatch):
    fake_client = FakeAsyncClient(FakeHTTPResponse(status_code=500, text="boom"))
    monkeypatch.setattr("app.routers.auth.httpx.AsyncClient", lambda timeout: fake_client)

    try:
        await auth_router._password_grant("student@example.com", "password123")
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "Login failed"
    else:
        raise AssertionError("expected HTTPException")


async def test_upsert_user_row_updates_existing_user(monkeypatch):
    user = type(
        "UserRow",
        (),
        {"email": "old@example.com", "name": "Old Name", "role": "student"},
    )()
    payload = TokenPayload(
        sub="user-1",
        email="new@example.com",
        name="New Name",
        role="admin",
        exp=1234567890,
    )
    committed = {}

    class FakeResult:
        def scalar_one_or_none(self):
            return user

    class FakeDB:
        async def execute(self, stmt):
            return FakeResult()

        async def commit(self):
            committed["called"] = True

        def add(self, obj):
            raise AssertionError("should not add a new user")

    async def fake_get_or_create_account(db, user_id):
        committed["account_for"] = user_id

    monkeypatch.setattr("app.routers.auth.get_or_create_account", fake_get_or_create_account)

    await auth_router._upsert_user_row(FakeDB(), payload)

    assert user.email == "new@example.com"
    assert user.name == "New Name"
    assert user.role == "admin"
    assert committed["called"] is True
    assert committed["account_for"] == "user-1"


async def test_refresh_rejects_disallowed_origin(monkeypatch):
    monkeypatch.setattr("app.routers.auth.settings.cors_origins", ["http://localhost:5173"])
    request = Request(
        {"type": "http", "headers": [(b"origin", b"http://evil.example.com")]}
    )

    response = await auth_router.refresh.__wrapped__(request)

    assert response.status_code == 403
    assert response.body == b'{"detail":"forbidden origin"}'


async def test_refresh_requires_refresh_cookie():
    request = Request({"type": "http", "headers": []})

    response = await auth_router.refresh.__wrapped__(request)

    assert response.status_code == 401
    assert response.body == b'{"detail":"No refresh token"}'


async def test_refresh_clears_cookies_on_failed_token_exchange(monkeypatch):
    request = Request(
        {
            "type": "http",
            "headers": [(b"cookie", b"refresh_token=refresh-1")],
        }
    )
    fake_client = FakeAsyncClient(FakeHTTPResponse(status_code=401, text="bad refresh"))
    monkeypatch.setattr("app.routers.auth.httpx.AsyncClient", lambda timeout: fake_client)

    response = await auth_router.refresh.__wrapped__(request)

    assert response.status_code == 401
    set_cookie = response.headers.getlist("set-cookie")
    assert any("session_token=" in value for value in set_cookie)
    assert any("refresh_token=" in value for value in set_cookie)


async def test_refresh_sets_new_session_cookies_on_success(monkeypatch):
    request = Request(
        {
            "type": "http",
            "headers": [(b"cookie", b"refresh_token=refresh-1")],
        }
    )
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

    response = await auth_router.refresh.__wrapped__(request)

    assert response.status_code == 200
    assert response.body == b'{"message":"refreshed"}'
    set_cookie = response.headers.getlist("set-cookie")
    assert any("session_token=access-2" in value for value in set_cookie)
    assert any("refresh_token=refresh-2" in value for value in set_cookie)
