"""JWT verification with proper aud/iss/exp checks and JWKS rotation."""
import asyncio
import logging
import time

import httpx
from jose import JWTError, jwt

from app.config import settings
from app.schemas.user import TokenPayload

logger = logging.getLogger(__name__)

# Cache JWKS keyed by `kid`. Refreshed on cache miss (signing-key rotation)
# and on a periodic TTL so expired keys eventually drop out.
_JWKS_TTL_SECONDS = 600  # 10 minutes
_jwks: dict = {"keys": []}
_jwks_fetched_at: float = 0.0
_jwks_lock = asyncio.Lock()


async def _fetch_jwks() -> dict:
    url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def _get_jwks(force: bool = False) -> dict:
    """Return JWKS, refreshing if missing/stale or `force=True`."""
    global _jwks, _jwks_fetched_at
    now = time.monotonic()
    if not force and _jwks.get("keys") and (now - _jwks_fetched_at) < _JWKS_TTL_SECONDS:
        return _jwks
    async with _jwks_lock:
        # Re-check after acquiring the lock — another coroutine may have refreshed.
        now = time.monotonic()
        if not force and _jwks.get("keys") and (now - _jwks_fetched_at) < _JWKS_TTL_SECONDS:
            return _jwks
        try:
            _jwks = await _fetch_jwks()
            _jwks_fetched_at = now
        except httpx.HTTPError:
            logger.exception("JWKS fetch failed")
            # Keep the stale cache if we have one — better than 401-ing every request.
            if not _jwks.get("keys"):
                raise
        return _jwks


def _has_kid(jwks: dict, kid: str | None) -> bool:
    if not kid:
        return False
    return any(k.get("kid") == kid for k in jwks.get("keys", []))


async def verify_token(token: str) -> TokenPayload | None:
    """Validate a Keycloak-issued JWT.

    Verifies signature, exp, iss, and audience. Refreshes JWKS on `kid` miss
    (Keycloak key rotation). Returns None on any validation failure.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        return None
    kid = unverified_header.get("kid")

    jwks = await _get_jwks()
    if not _has_kid(jwks, kid):
        # Likely a key rotation — fetch fresh JWKS and retry.
        try:
            jwks = await _get_jwks(force=True)
        except Exception:
            return None
        if not _has_kid(jwks, kid):
            return None

    expected_issuer = (
        f"{settings.keycloak_external_url.rstrip('/')}/realms/{settings.keycloak_realm}"
    )

    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=[settings.jwt_algorithm],
            audience=settings.keycloak_client_id,
            issuer=expected_issuer,
            options={
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
                "verify_signature": True,
                "require_exp": True,
            },
        )
    except JWTError as e:
        logger.debug("Token validation failed: %s", e)
        return None

    # App roles are realm-roles in Keycloak. Built-in Keycloak roles like
    # "default-roles-hopper" are filtered out.
    roles = payload.get("realm_access", {}).get("roles", [])
    app_roles = {"admin", "professor", "student"}
    role = next((r for r in roles if r in app_roles), "student")

    return TokenPayload(
        sub=payload["sub"],
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        role=role,
        exp=payload["exp"],
        email_verified=bool(payload.get("email_verified", False)),
    )
