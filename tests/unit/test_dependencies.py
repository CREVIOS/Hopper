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
