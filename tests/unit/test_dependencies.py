import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.dependencies import get_current_user, get_db
from app.schemas.user import TokenPayload


class _AsyncSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def test_get_db_yields_session(monkeypatch):
    expected_session = object()

    def fake_async_session():
        return _AsyncSessionContext(expected_session)

    monkeypatch.setattr("app.dependencies.async_session", fake_async_session)

    generator = get_db()
    yielded = await anext(generator)

    assert yielded is expected_session

    with pytest.raises(StopAsyncIteration):
        await anext(generator)


async def test_get_current_user_returns_verified_payload(monkeypatch):
    payload = TokenPayload(
        sub="user-1",
        email="student@example.com",
        name="Test Student",
        role="student",
        exp=1234567890,
    )

    async def fake_verify_token(token):
        assert token == "valid-token"
        return payload

    monkeypatch.setattr("app.dependencies.verify_token", fake_verify_token)

    request = Request(
        {"type": "http", "headers": [(b"cookie", b"session_token=valid-token")]}
    )

    result = await get_current_user(request)

    assert result == payload


async def test_get_current_user_rejects_missing_cookie():
    request = Request({"type": "http", "headers": []})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


async def test_get_current_user_rejects_invalid_token(monkeypatch):
    async def fake_verify_token(token):
        assert token == "bad-token"
        return None

    monkeypatch.setattr("app.dependencies.verify_token", fake_verify_token)

    request = Request(
        {"type": "http", "headers": [(b"cookie", b"session_token=bad-token")]}
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or expired token"


# ---------------------------------------------------------------------------
# API-key authentication (HOP-19 18.1)
# ---------------------------------------------------------------------------

class _FakeApiKeyRow:
    def __init__(self, key_id="key-1", user_id="user-1", scope="full_access"):
        self.id = key_id
        self.user_id = user_id
        self.scope = scope
        self.revoked_at = None


class _FakeUserRow:
    def __init__(self, user_id="user-1"):
        self.id = user_id
        self.email = "student@example.com"
        self.name = "Test Student"
        self.role = "student"


class _FakeDb:
    def __init__(self, user_row):
        self.user_row = user_row

    async def get(self, model, pk):
        return self.user_row


def _api_key_request(method="GET", header=("x-api-key", "hop_test")):
    name, value = header
    return Request(
        {
            "type": "http",
            "method": method,
            "headers": [(name.encode(), value.encode())],
            "client": ("203.0.113.7", 1234),
            "path": "/",
        }
    )


def _install_api_key_fakes(monkeypatch, row, user_row):
    async def fake_verify_key(db, token):
        return row

    monkeypatch.setattr("app.services.api_key_service.verify_key", fake_verify_key)
    monkeypatch.setattr(
        "app.dependencies.async_session", lambda: _AsyncSessionContext(_FakeDb(user_row))
    )


async def test_api_key_header_authenticates_and_sets_rate_key(monkeypatch):
    _install_api_key_fakes(monkeypatch, _FakeApiKeyRow(), _FakeUserRow())

    request = _api_key_request()
    payload = await get_current_user(request)

    assert payload.sub == "user-1"
    assert payload.role == "student"
    # Rate limited separately from session auth: keyed per API key.
    assert request.state.rate_key == "apikey:key-1"
    assert request.state.api_key_auth is True


async def test_api_key_via_bearer_authorization(monkeypatch):
    _install_api_key_fakes(monkeypatch, _FakeApiKeyRow(), _FakeUserRow())

    request = _api_key_request(header=("authorization", "Bearer hop_test"))
    payload = await get_current_user(request)

    assert payload.sub == "user-1"


async def test_non_hop_bearer_token_is_not_treated_as_api_key():
    # A Keycloak JWT in Authorization must fall through to the cookie flow
    # (and 401 without a cookie), not the API-key lookup.
    request = _api_key_request(header=("authorization", "Bearer eyJhbGciOiJSUzI1NiJ9.x.y"))

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


async def test_invalid_api_key_rejected(monkeypatch):
    _install_api_key_fakes(monkeypatch, None, _FakeUserRow())

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(_api_key_request())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or revoked API key"


async def test_read_only_key_rejects_mutating_methods(monkeypatch):
    _install_api_key_fakes(
        monkeypatch, _FakeApiKeyRow(key_id="ro-key", scope="read_only"), _FakeUserRow()
    )

    payload = await get_current_user(_api_key_request(method="GET"))
    assert payload.sub == "user-1"

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(_api_key_request(method="POST"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "This API key is read-only"


async def test_session_auth_sets_user_rate_key(monkeypatch):
    payload = TokenPayload(
        sub="user-rate-key-test",
        email="student@example.com",
        name="Test Student",
        role="student",
        exp=1234567890,
    )

    async def fake_verify_token(token):
        return payload

    monkeypatch.setattr("app.dependencies.verify_token", fake_verify_token)

    request = Request(
        {"type": "http", "headers": [(b"cookie", b"session_token=valid-token")]}
    )
    await get_current_user(request)

    assert request.state.rate_key == "user:user-rate-key-test"
