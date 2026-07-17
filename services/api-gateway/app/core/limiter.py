"""Rate limiting shared across routers (HOP-19 18.2).

Two layers:

1. ``limiter`` — slowapi decorators on individual routes. The key function
   prefers the VERIFIED caller identity (``request.state.rate_key``, set by
   ``get_current_user`` — ``user:<jwt-sub>`` for sessions, ``apikey:<id>``
   for API keys) and falls back to the X-Forwarded-For-aware client IP for
   unauthenticated routes (login, signup, ...). FastAPI resolves dependencies
   before the decorated endpoint body runs, so the state is already set when
   the limit is evaluated on authenticated routes.

2. Moving-window buckets (the ``limits`` library slowapi builds on) for the
   checks that don't fit the decorator model: the per-user default applied
   after auth resolves, the separate per-key API-key limit, and the
   failed-login throttle (which must count only FAILURES, not calls).

All storage is in-memory per worker process; with N uvicorn workers × M
replicas the effective ceiling is up to N×M× the configured rate. These are
abuse guards, not billing-grade quotas.
"""
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def user_or_ip_key(request) -> str:
    """Verified per-user/per-key identity when auth has run, else client IP."""
    return getattr(request.state, "rate_key", None) or get_remote_address(request)


limiter = Limiter(
    key_func=user_or_ip_key,
    default_limits=["120/minute"],
    headers_enabled=True,
)

_storage = MemoryStorage()
_window = MovingWindowRateLimiter(_storage)
_user_default = parse(settings.rate_limit_user_default)
_api_key_rate = parse(settings.rate_limit_api_key)
_login_failure_rate = parse(settings.rate_limit_login_failures)


def allow_session_request(user_id: str) -> bool:
    """Per-user default for session-authenticated traffic (keyed by JWT sub)."""
    return _window.hit(_user_default, "user", user_id)


def allow_api_key_request(key_id: str) -> bool:
    """Separate, tighter bucket for programmatic (API-key) access, per key."""
    return _window.hit(_api_key_rate, "apikey", key_id)


def login_blocked(ip: str, email: str) -> bool:
    """True when (ip, email) has exhausted its failed-attempt budget."""
    return not _window.test(_login_failure_rate, "login", ip, email)


def record_login_failure(ip: str, email: str) -> None:
    _window.hit(_login_failure_rate, "login", ip, email)


def clear_login_failures(ip: str, email: str) -> None:
    """A successful sign-in resets the counter (it was the right user)."""
    _window.clear(_login_failure_rate, "login", ip, email)
