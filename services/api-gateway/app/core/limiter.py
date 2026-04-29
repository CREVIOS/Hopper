"""Rate limiter shared across routers.

Uses the X-Forwarded-For-aware client address so limits apply per real-client
IP behind the nginx ingress. Default global limit is generous; specific
routes (auth, terminal, pod create) tighten further with @limiter.limit().
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    headers_enabled=True,
)
