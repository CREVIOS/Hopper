from fastapi import Response

from app.routers import auth as auth_router


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
