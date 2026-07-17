import types

import pytest

from app.services.keycloak_admin import (
    KeycloakAdminClient,
    KeycloakAdminError,
    KeycloakPasswordPolicyError,
    KeycloakUserExistsError,
)


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


# --------------------------------------------------------------------------
# Password-policy error translation.
#
# The realm (scripts/keycloak-harden.sh) rejects a non-compliant password with
# a 400 naming the failed rule. That used to surface as a plain
# KeycloakAdminError, which routers/auth.py turned into a 502 "Could not create
# the account. Try again later." — telling the user nothing. These pin the
# typed translation so a policy rejection stays distinguishable from Keycloak
# actually being down.
#
# Bodies are copied verbatim from a real Keycloak 25 running that policy. Note
# the two shapes: password rejections arrive as `error`/`error_description`,
# conflicts as `errorMessage`. Both must be read.
# --------------------------------------------------------------------------

KC_ALL_DIGITS = {
    "error": "invalidPasswordMinUpperCaseCharsMessage",
    "error_description": "Invalid password: must contain at least 1 upper case characters.",
}
KC_TOO_SHORT = {
    "error": "invalidPasswordMinLengthMessage",
    "error_description": "Invalid password: minimum length 12.",
}
KC_NO_DIGITS = {
    "error": "invalidPasswordMinDigitsMessage",
    "error_description": "Invalid password: must contain at least 1 numerical digits.",
}
KC_HISTORY = {
    "error": "invalidPasswordHistoryMessage",
    "error_description": "Invalid password: must not be equal to any of last 3 passwords.",
}

CREATE_KW = dict(email="jane@cs.du.ac.bd", name="Jane Doe", password="111111111111111")


def _client_returning(monkeypatch, response):
    """A KeycloakAdminClient whose every admin call returns `response`."""
    client = KeycloakAdminClient()

    async def fake_request(method, path, **kwargs):
        return response

    monkeypatch.setattr(client, "_request", fake_request)
    return client


@pytest.mark.parametrize("body", [KC_ALL_DIGITS, KC_TOO_SHORT, KC_NO_DIGITS])
async def test_create_user_types_password_policy_rejections(monkeypatch, body):
    client = _client_returning(monkeypatch, FakeResponse(status_code=400, json_body=body))

    with pytest.raises(KeycloakPasswordPolicyError) as exc_info:
        await client.create_user(**CREATE_KW)

    # Keycloak's own reason is preserved — it names the rule the user missed.
    assert str(exc_info.value) == body["error_description"]


async def test_create_user_reads_legacy_error_message_field(monkeypatch):
    # Other Keycloak versions/paths report the reason as `errorMessage`; keep
    # reading it so an upgrade can't silently regress this to a 502.
    client = _client_returning(
        monkeypatch,
        FakeResponse(status_code=400, json_body={"errorMessage": "Invalid password: minimum length 12."}),
    )

    with pytest.raises(KeycloakPasswordPolicyError):
        await client.create_user(**CREATE_KW)


async def test_password_policy_error_is_still_a_keycloak_admin_error(monkeypatch):
    # routers/admin.py catches the base class — the subclass must not escape it.
    client = _client_returning(monkeypatch, FakeResponse(status_code=400, json_body=KC_ALL_DIGITS))

    with pytest.raises(KeycloakAdminError):
        await client.create_user(**CREATE_KW)


async def test_create_user_types_the_duplicate_conflict(monkeypatch):
    client = _client_returning(
        monkeypatch,
        FakeResponse(status_code=409, json_body={"errorMessage": "User exists with same email"}),
    )

    with pytest.raises(KeycloakUserExistsError) as exc_info:
        await client.create_user(**CREATE_KW)

    # The router used to match on `"exists" in str(e)`; keep that true.
    assert "exists" in str(exc_info.value)


@pytest.mark.parametrize(
    "response",
    [
        # A 400 that isn't about the password must not be shown as one.
        FakeResponse(status_code=400, json_body={"error": "invalid_request", "error_description": "Bad realm role"}),
        FakeResponse(status_code=400, json_body={"errorMessage": "User profile validation failed"}),
        # Non-JSON body (a proxy error page, say) must not crash the parser.
        FakeResponse(status_code=400, json_body=None, text="<html>gateway error</html>"),
        FakeResponse(status_code=500, json_body=None, text="upstream boom"),
    ],
)
async def test_non_password_failures_stay_generic(monkeypatch, response):
    client = _client_returning(monkeypatch, response)

    with pytest.raises(KeycloakAdminError) as exc_info:
        await client.create_user(**CREATE_KW)

    assert not isinstance(exc_info.value, KeycloakPasswordPolicyError)


async def test_reset_password_types_password_history_rejection(monkeypatch):
    # passwordHistory(3) is the rule app.services.password_policy cannot
    # mirror — only Keycloak knows previous hashes — so this typed error is
    # the ONLY way the user learns they reused a password.
    client = _client_returning(monkeypatch, FakeResponse(status_code=400, json_body=KC_HISTORY))

    with pytest.raises(KeycloakPasswordPolicyError) as exc_info:
        await client.reset_password("user-id", "Recycled9Password")

    assert "last 3 passwords" in str(exc_info.value)


async def test_reset_password_succeeds_silently(monkeypatch):
    client = _client_returning(monkeypatch, FakeResponse(status_code=204))

    await client.reset_password("user-id", "Fresh9Password")  # must not raise
