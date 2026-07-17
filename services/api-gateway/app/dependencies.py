import time
from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.limiter import allow_api_key_request, allow_session_request
from app.middleware.auth import verify_token
from app.schemas.user import TokenPayload

_READ_METHODS = ("GET", "HEAD", "OPTIONS")


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session() as session:
        yield session


def _api_key_from_request(request: Request) -> str | None:
    """Extract a presented API key: `X-API-Key` header, or an
    `Authorization: Bearer hop_...` value (only the hop_ prefix is treated as
    an API key — anything else is not ours)."""
    from app.services.api_key_service import looks_like_api_key

    header = request.headers.get("X-API-Key")
    if header and looks_like_api_key(header):
        return header
    authz = request.headers.get("Authorization", "")
    if authz.startswith("Bearer "):
        candidate = authz[len("Bearer "):].strip()
        if looks_like_api_key(candidate):
            return candidate
    return None


async def _user_from_api_key(request: Request, token: str) -> TokenPayload:
    """Resolve an API key to its owning user (HOP-19 18.1).

    Enforces the separate programmatic rate limit (per key, tighter than the
    session default) and the read_only scope (GET/HEAD/OPTIONS only). Marks
    the request so key-management endpoints can insist on a real session.
    """
    from app.models.user import User
    from app.services import api_key_service

    async with async_session() as db:
        row = await api_key_service.verify_key(db, token)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API key",
            )
        if not allow_api_key_request(row.id):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="API key rate limit exceeded",
            )
        if row.scope == "read_only" and request.method not in _READ_METHODS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This API key is read-only",
            )
        user = await db.get(User, row.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key owner no longer exists",
            )
        # Keyed per key (not per user) so programmatic access is rate limited
        # separately from the same user's browser session.
        request.state.rate_key = f"apikey:{row.id}"
        request.state.api_key_auth = True
        return TokenPayload(
            sub=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            # Synthetic expiry — API keys don't expire like JWTs; revocation
            # is the kill switch. Nothing downstream should trust this field
            # for an API-key principal.
            exp=int(time.time()) + 300,
            email_verified=True,
        )


async def get_current_user(request: Request) -> TokenPayload:
    """Authenticate the request: API key (programmatic) or session cookie.

    Session traffic gets a per-user default rate limit keyed by the VERIFIED
    JWT subject (not the client IP, which is shared behind university NAT).
    """
    api_key = _api_key_from_request(request)
    if api_key:
        return await _user_from_api_key(request, api_key)

    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = await verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    request.state.rate_key = f"user:{payload.sub}"
    if not allow_session_request(payload.sub):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    return payload
