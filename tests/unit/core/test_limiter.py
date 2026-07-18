import uuid

from starlette.requests import Request

from app.core.limiter import (
    allow_api_key_request,
    allow_session_request,
    clear_login_failures,
    limiter,
    login_blocked,
    record_login_failure,
    user_or_ip_key,
)


def _request(client_ip: str = "203.0.113.7") -> Request:
    return Request(
        {
            "type": "http",
            "headers": [],
            "client": (client_ip, 1234),
            "method": "GET",
            "path": "/",
        }
    )


def test_limiter_uses_expected_defaults():
    assert len(limiter._default_limits) == 1
    assert limiter._default_limits[0]._LimitGroup__limit_provider == "120/minute"
    assert limiter.enabled is True
    assert limiter._headers_enabled is True
    # HOP-19 18.2: keyed by verified user identity, falling back to client IP.
    assert limiter._key_func is user_or_ip_key


def test_key_prefers_verified_identity_over_ip():
    request = _request()
    assert user_or_ip_key(request) == "203.0.113.7"
    request.state.rate_key = "user:abc-123"
    assert user_or_ip_key(request) == "user:abc-123"


def test_session_and_api_key_buckets_are_separate():
    # Same underlying user: the session bucket and an API-key bucket must not
    # share state ("rate limited separately from session auth").
    uid = f"u-{uuid.uuid4()}"
    kid = f"k-{uuid.uuid4()}"
    assert allow_session_request(uid) is True
    assert allow_api_key_request(kid) is True


def test_api_key_bucket_enforces_configured_rate():
    kid = f"k-{uuid.uuid4()}"
    # Default HOPPER_RATE_LIMIT_API_KEY is 30/minute.
    results = [allow_api_key_request(kid) for _ in range(31)]
    assert all(results[:30])
    assert results[30] is False


def test_login_throttle_counts_failures_and_resets_on_success():
    ip, email = "198.51.100.9", f"{uuid.uuid4()}@example.com"
    assert login_blocked(ip, email) is False
    for _ in range(3):  # default HOPPER_RATE_LIMIT_LOGIN_FAILURES is 3/5minutes
        record_login_failure(ip, email)
    assert login_blocked(ip, email) is True
    # A different email from the same (NAT) address is unaffected.
    assert login_blocked(ip, f"{uuid.uuid4()}@example.com") is False
    clear_login_failures(ip, email)
    assert login_blocked(ip, email) is False
