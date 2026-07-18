import httpx

from app.middleware import auth as auth_module


async def test_get_jwks_returns_cached_value_without_fetch(monkeypatch):
    auth_module._jwks = {"keys": [{"kid": "cached"}]}
    auth_module._jwks_fetched_at = 1_000.0

    monkeypatch.setattr("app.middleware.auth.time.monotonic", lambda: 1_100.0)

    async def fail_fetch():
        raise AssertionError("fetch should not be called")

    monkeypatch.setattr("app.middleware.auth._fetch_jwks", fail_fetch)

    result = await auth_module._get_jwks()

    assert result == {"keys": [{"kid": "cached"}]}


async def test_get_jwks_refreshes_when_force_is_true(monkeypatch):
    auth_module._jwks = {"keys": [{"kid": "stale"}]}
    auth_module._jwks_fetched_at = 1_000.0

    monkeypatch.setattr("app.middleware.auth.time.monotonic", lambda: 1_050.0)

    async def fake_fetch():
        return {"keys": [{"kid": "fresh"}]}

    monkeypatch.setattr("app.middleware.auth._fetch_jwks", fake_fetch)

    result = await auth_module._get_jwks(force=True)

    assert result == {"keys": [{"kid": "fresh"}]}
    assert auth_module._jwks == {"keys": [{"kid": "fresh"}]}


async def test_get_jwks_keeps_stale_cache_when_fetch_fails(monkeypatch):
    auth_module._jwks = {"keys": [{"kid": "stale"}]}
    auth_module._jwks_fetched_at = 1_000.0

    monkeypatch.setattr("app.middleware.auth.time.monotonic", lambda: 2_000.0)

    async def fake_fetch():
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("app.middleware.auth._fetch_jwks", fake_fetch)

    result = await auth_module._get_jwks()

    assert result == {"keys": [{"kid": "stale"}]}


def test_has_kid_requires_matching_key_id():
    assert auth_module._has_kid({"keys": [{"kid": "a"}]}, "a") is True
    assert auth_module._has_kid({"keys": [{"kid": "a"}]}, "b") is False
    assert auth_module._has_kid({"keys": [{"kid": "a"}]}, None) is False


async def test_verify_token_returns_none_for_invalid_header(monkeypatch):
    def fake_header(token):
        raise auth_module.JWTError("bad header")

    monkeypatch.setattr("app.middleware.auth.jwt.get_unverified_header", fake_header)

    assert await auth_module.verify_token("bad-token") is None


async def test_verify_token_refreshes_on_kid_miss_and_builds_payload(monkeypatch):
    monkeypatch.setattr(
        "app.middleware.auth.jwt.get_unverified_header",
        lambda token: {"kid": "new-kid"},
    )

    jwks_responses = iter([
        {"keys": [{"kid": "old-kid"}]},
        {"keys": [{"kid": "new-kid"}]},
    ])

    async def fake_get_jwks(force=False):
        return next(jwks_responses)

    decoded_payload = {
        "sub": "user-1",
        "email": "student@example.com",
        "name": "Test Student",
        "realm_access": {"roles": ["offline_access", "admin"]},
        "exp": 1234567890,
        "email_verified": True,
    }

    def fake_decode(token, jwks, algorithms, audience, issuer, options):
        assert jwks == {"keys": [{"kid": "new-kid"}]}
        assert algorithms == [auth_module.settings.jwt_algorithm]
        assert audience == auth_module.settings.keycloak_client_id
        assert issuer == (
            f"{auth_module.settings.keycloak_external_url.rstrip('/')}/realms/"
            f"{auth_module.settings.keycloak_realm}"
        )
        assert options["require_exp"] is True
        return decoded_payload

    monkeypatch.setattr("app.middleware.auth._get_jwks", fake_get_jwks)
    monkeypatch.setattr("app.middleware.auth.jwt.decode", fake_decode)

    payload = await auth_module.verify_token("valid-token")

    assert payload.sub == "user-1"
    assert payload.role == "admin"
    assert payload.email_verified is True


async def test_verify_token_defaults_role_to_student(monkeypatch):
    monkeypatch.setattr(
        "app.middleware.auth.jwt.get_unverified_header",
        lambda token: {"kid": "kid-1"},
    )

    async def fake_get_jwks(force=False):
        return {"keys": [{"kid": "kid-1"}]}

    monkeypatch.setattr("app.middleware.auth._get_jwks", fake_get_jwks)
    monkeypatch.setattr(
        "app.middleware.auth.jwt.decode",
        lambda *args, **kwargs: {
            "sub": "user-1",
            "email": "student@example.com",
            "name": "Test Student",
            "realm_access": {"roles": ["offline_access"]},
            "exp": 1234567890,
        },
    )

    payload = await auth_module.verify_token("valid-token")

    assert payload.role == "student"


async def test_verify_token_returns_none_when_decode_fails(monkeypatch):
    monkeypatch.setattr(
        "app.middleware.auth.jwt.get_unverified_header",
        lambda token: {"kid": "kid-1"},
    )

    async def fake_get_jwks(force=False):
        return {"keys": [{"kid": "kid-1"}]}

    def fake_decode(*args, **kwargs):
        raise auth_module.JWTError("bad token")

    monkeypatch.setattr("app.middleware.auth._get_jwks", fake_get_jwks)
    monkeypatch.setattr("app.middleware.auth.jwt.decode", fake_decode)

    assert await auth_module.verify_token("bad-token") is None
