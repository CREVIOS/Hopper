import httpx
from jose import JWTError, jwt

from app.config import settings
from app.schemas.user import TokenPayload

_jwks_cache: dict | None = None


async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            _jwks_cache = resp.json()
    return _jwks_cache


async def verify_token(token: str) -> TokenPayload | None:
    """Validate a Keycloak-issued JWT and return the payload."""
    try:
        jwks = await _get_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=[settings.jwt_algorithm],
            audience=settings.keycloak_client_id,
        )
        return TokenPayload(
            sub=payload["sub"],
            email=payload.get("email", ""),
            name=payload.get("name", ""),
            role=payload.get("realm_access", {}).get("roles", ["student"])[0],
            exp=payload["exp"],
        )
    except JWTError:
        return None
