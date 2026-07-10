from slowapi.util import get_remote_address

from app.core.limiter import limiter


def test_limiter_uses_expected_defaults():
    assert limiter._default_limits == ["120/minute"]
    assert limiter.enabled is True
    assert limiter._headers_enabled is True
    assert limiter._key_func is get_remote_address
