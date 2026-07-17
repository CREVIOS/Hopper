import types

import pytest

from app.services.keycloak_admin import KeycloakAdminClient, KeycloakAdminError


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text="", headers=None):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json_body


class FakeAsyncClient:
    def __init__(self, *, post_responses=None, get_responses=None, request_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.request_responses = list(request_responses or [])
        self.post_calls = []
        self.get_calls = []
        self.request_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.post_responses.pop(0)

    async def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.get_responses.pop(0)

    async def request(self, method, url, **kwargs):
        self.request_calls.append((method, url, kwargs))
        return self.request_responses.pop(0)


async def test_get_token_uses_cache_when_not_near_expiry(monkeypatch):
    client = KeycloakAdminClient()
    client._token = "cached-token"
    client._token_exp = 500.0

    monkeypatch.setattr("app.services.keycloak_admin.time.monotonic", lambda: 100.0)

    assert await client._get_token() == "cached-token"


async def test_get_token_requires_client_secret():
    client = KeycloakAdminClient()
    client._client_secret = ""

    with pytest.raises(KeycloakAdminError) as exc_info:
        await client._get_token()

    assert "HOPPER_KEYCLOAK_ADMIN_CLIENT_SECRET not configured" in str(exc_info.value)


async def test_get_token_fetches_and_stores_expiry(monkeypatch):
    fake_client = FakeAsyncClient(
        post_responses=[
            FakeResponse(
                status_code=200,
                json_body={"access_token": "new-token", "expires_in": 120},
            )
        ]
    )

    monkeypatch.setattr("app.services.keycloak_admin.httpx.AsyncClient", lambda timeout: fake_client)
    monkeypatch.setattr("app.services.keycloak_admin.time.monotonic", lambda: 100.0)

    client = KeycloakAdminClient()
    client._client_secret = "secret"

    token = await client._get_token()

    assert token == "new-token"
    assert client._token == "new-token"
    assert client._token_exp == 220.0


async def test_headers_wraps_bearer_token(monkeypatch):
    client = KeycloakAdminClient()

    async def fake_get_token():
        return "token-1"

    monkeypatch.setattr(client, "_get_token", fake_get_token)

    assert await client._headers() == {"Authorization": "Bearer token-1"}


async def test_set_user_role_rejects_invalid_role():
    client = KeycloakAdminClient()

    with pytest.raises(ValueError) as exc_info:
        await client.set_user_role("user-1", "ta")

    assert "invalid role" in str(exc_info.value)


async def test_set_user_role_fails_when_target_role_missing(monkeypatch):
    client = KeycloakAdminClient()

    async def fake_list_roles():
        return [{"id": "1", "name": "student"}]

    async def fake_user_roles(user_id):
        return []

    monkeypatch.setattr(client, "list_realm_roles", fake_list_roles)
    monkeypatch.setattr(client, "get_user_realm_roles", fake_user_roles)

    with pytest.raises(KeycloakAdminError) as exc_info:
        await client.set_user_role("user-1", "admin")

    assert "does not exist" in str(exc_info.value)


async def test_create_user_uses_location_header(monkeypatch):
    # Admin REST calls now go through _request -> client.request (so they can
    # transparently retry on a rejected/stale token), hence request_responses.
    fake_client = FakeAsyncClient(
        request_responses=[
            FakeResponse(status_code=201, headers={"Location": "http://keycloak/users/user-1"})
        ]
    )

    client = KeycloakAdminClient()

    async def fake_headers():
        return {"Authorization": "Bearer token"}

    async def fake_set_user_role(user_id, role):
        assert user_id == "user-1"
        assert role == "student"

    monkeypatch.setattr("app.services.keycloak_admin.httpx.AsyncClient", lambda timeout: fake_client)
    monkeypatch.setattr(client, "_headers", fake_headers)
    monkeypatch.setattr(client, "set_user_role", fake_set_user_role)

    user_id = await client.create_user(
        email="student@example.com",
        name="Test Student",
        password="password123",
    )

    assert user_id == "user-1"
    # request_calls stores (method, url, kwargs).
    method, _url, kwargs = fake_client.request_calls[0]
    assert method == "POST"
    payload = kwargs["json"]
    assert payload["firstName"] == "Test"
    assert payload["lastName"] == "Student"


async def test_create_user_uses_lookup_when_location_header_missing(monkeypatch):
    fake_client = FakeAsyncClient(
        # First the create POST (no Location), then the username lookup GET —
        # both flow through client.request now.
        request_responses=[
            FakeResponse(status_code=201, headers={}),
            FakeResponse(status_code=200, json_body=[{"id": "user-lookup"}]),
        ],
    )

    client = KeycloakAdminClient()

    async def fake_headers():
        return {"Authorization": "Bearer token"}

    async def fake_set_user_role(user_id, role):
        assert user_id == "user-lookup"
        assert role == "student"

    monkeypatch.setattr("app.services.keycloak_admin.httpx.AsyncClient", lambda timeout: fake_client)
    monkeypatch.setattr(client, "_headers", fake_headers)
    monkeypatch.setattr(client, "set_user_role", fake_set_user_role)

    user_id = await client.create_user(
        email="student@example.com",
        name="Solo",
        password="password123",
    )

    assert user_id == "user-lookup"


async def test_logout_user_raises_on_failed_response(monkeypatch):
    # A 5xx is retried once by _request, so both attempts must be fed; a
    # persistent failure still surfaces as a KeycloakAdminError.
    fake_client = FakeAsyncClient(
        request_responses=[
            FakeResponse(status_code=500, text="boom"),
            FakeResponse(status_code=500, text="boom"),
        ]
    )

    client = KeycloakAdminClient()

    async def fake_headers():
        return {"Authorization": "Bearer token"}

    monkeypatch.setattr("app.services.keycloak_admin.httpx.AsyncClient", lambda timeout: fake_client)
    monkeypatch.setattr(client, "_headers", fake_headers)

    with pytest.raises(KeycloakAdminError) as exc_info:
        await client.logout_user("user-1")

    assert "force logout failed" in str(exc_info.value)
    assert len(fake_client.request_calls) == 2  # retried once


async def test_request_retries_once_on_401_and_refreshes_token(monkeypatch):
    """Guard for the intermittent-signup fix: a cached token that Keycloak has
    started rejecting (401) must be dropped and the call retried once with a
    fresh token, instead of bubbling up as a hard error."""
    fake_client = FakeAsyncClient(
        request_responses=[
            FakeResponse(status_code=401, text="token rejected"),
            FakeResponse(status_code=200, json_body={"ok": True}),
        ]
    )

    client = KeycloakAdminClient()
    client._token = "stale-token"
    client._token_exp = 10_000.0  # looks un-expired locally -> would be reused

    seen_tokens = []

    async def fake_get_token():
        seen_tokens.append(client._token)
        return client._token or "fresh-token"

    monkeypatch.setattr("app.services.keycloak_admin.httpx.AsyncClient", lambda timeout: fake_client)
    monkeypatch.setattr(client, "_get_token", fake_get_token)

    resp = await client._request("GET", "/users")

    assert resp.status_code == 200
    assert len(fake_client.request_calls) == 2          # retried exactly once
    # The 401 cleared the cache before the retry re-fetched the token.
    assert seen_tokens == ["stale-token", None]


async def test_request_retries_once_on_5xx(monkeypatch):
    """A transient 5xx (Keycloak briefly busy) is retried once and can succeed
    without refreshing the token."""
    fake_client = FakeAsyncClient(
        request_responses=[
            FakeResponse(status_code=503, text="unavailable"),
            FakeResponse(status_code=200, json_body=[{"id": "role-1"}]),
        ]
    )

    client = KeycloakAdminClient()

    async def fake_headers():
        return {"Authorization": "Bearer token"}

    monkeypatch.setattr("app.services.keycloak_admin.httpx.AsyncClient", lambda timeout: fake_client)
    monkeypatch.setattr(client, "_headers", fake_headers)

    resp = await client._request("GET", "/roles")

    assert resp.status_code == 200
    assert len(fake_client.request_calls) == 2
