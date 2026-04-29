"""OIDC auth flow against Keycloak.

Implements OAuth 2.1 baseline: PKCE (S256), `state` (CSRF), `nonce` (replay).
Cookies are SameSite=Lax, HttpOnly, Secure; the access token cookie max-age
matches the access token's `exp` so a stolen cookie expires sooner than the
refresh token. Logout is RP-initiated against Keycloak so SSO sessions and
refresh tokens are actually revoked, not just deleted client-side.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import get_current_user, get_db
from app.middleware.auth import verify_token
from app.models.user import User
from app.schemas.user import TokenPayload, UserResponse
from app.services.credit_service import get_or_create_account

logger = logging.getLogger(__name__)
router = APIRouter()

KEYCLOAK_AUTH_URL = (
    f"{settings.keycloak_external_url.rstrip('/')}/realms/{settings.keycloak_realm}/protocol/openid-connect/auth"
)
KEYCLOAK_TOKEN_URL = (
    f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"
)
KEYCLOAK_LOGOUT_URL = (
    f"{settings.keycloak_external_url.rstrip('/')}/realms/{settings.keycloak_realm}/protocol/openid-connect/logout"
)
KEYCLOAK_REVOKE_URL = (
    f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}/protocol/openid-connect/revoke"
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _new_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier = _b64url(os.urandom(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _domain_allowed(email: str) -> bool:
    if not settings.allowed_email_domains:
        return True  # dev mode
    email = (email or "").lower().strip()
    if "@" not in email:
        return False
    # Use exact suffix match — `attacker@evil.cs.du.ac.bd` must NOT match
    # `cs.du.ac.bd`. We compare only the part after the last `@`.
    domain = email.rsplit("@", 1)[1]
    return domain in {d.lower() for d in settings.allowed_email_domains}


def _set_session_cookies(
    resp: Response,
    *,
    access_token: str | None = None,
    access_ttl: int | None = None,
    refresh_token: str | None = None,
    refresh_ttl: int | None = None,
) -> None:
    """Set the auth cookies with consistent attributes.

    Access cookie max-age tracks the access token's TTL (typically 5 min) so a
    stolen browser cookie expires before the refresh token. Refresh cookie max
    -age tracks the refresh token TTL.
    """
    common = dict(httponly=True, secure=True, samesite="lax", path="/")
    if access_token is not None and access_ttl is not None:
        resp.set_cookie("session_token", access_token, max_age=access_ttl, **common)
    if refresh_token is not None and refresh_ttl is not None:
        resp.set_cookie("refresh_token", refresh_token, max_age=refresh_ttl, **common)


def _clear_session_cookies(resp: Response) -> None:
    """Delete auth cookies with attributes matching the original Set-Cookie.

    Browsers ignore delete_cookie() if Secure / SameSite / Path don't match
    the original — without this, logout silently leaves the cookies in place.
    """
    for name in ("session_token", "refresh_token", "oauth_state", "oauth_pkce"):
        resp.delete_cookie(
            name,
            path="/",
            secure=True,
            samesite="lax",
            httponly=True,
        )


@router.get("/login")
@limiter.limit("20/minute")
async def login(request: Request):
    """Begin OIDC auth with PKCE + state + nonce."""
    verifier, challenge = _new_pkce_pair()
    state = _b64url(os.urandom(24))
    nonce = _b64url(os.urandom(24))

    params = urlencode({
        "client_id": settings.keycloak_client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": settings.callback_url,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "nonce": nonce,
    })
    resp = RedirectResponse(url=f"{KEYCLOAK_AUTH_URL}?{params}")
    # Store the PKCE verifier and CSRF state in HttpOnly cookies. The callback
    # reads them back to complete the exchange.
    resp.set_cookie(
        "oauth_state",
        f"{state}.{nonce}",
        httponly=True, secure=True, samesite="lax", path="/", max_age=600,
    )
    resp.set_cookie(
        "oauth_pkce",
        verifier,
        httponly=True, secure=True, samesite="lax", path="/", max_age=600,
    )
    return resp


@router.get("/callback")
@limiter.limit("30/minute")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle OIDC callback — verify state, exchange with PKCE, gate by domain."""
    if error:
        logger.warning("OIDC error from Keycloak: %s", error)
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=oidc")

    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code/state")

    cookie_state = request.cookies.get("oauth_state") or ""
    expected_state, _, expected_nonce = cookie_state.partition(".")
    if not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="state mismatch")

    verifier = request.cookies.get("oauth_pkce")
    if not verifier:
        raise HTTPException(status_code=400, detail="missing pkce verifier")

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.keycloak_client_id,
        "code": code,
        "redirect_uri": settings.callback_url,
        "code_verifier": verifier,
    }
    if settings.keycloak_client_secret:
        data["client_secret"] = settings.keycloak_client_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(KEYCLOAK_TOKEN_URL, data=data)
    if token_resp.status_code != 200:
        logger.warning("Token exchange failed: %s", token_resp.text)
        raise HTTPException(status_code=401, detail="token exchange failed")

    tokens = token_resp.json()
    access_token = tokens["access_token"]

    payload = await verify_token(access_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="invalid id token")

    # Domain gate (defence in depth — Keycloak realm should also enforce).
    if not _domain_allowed(payload.email):
        logger.info("Rejecting login from disallowed domain: %s", payload.email)
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=domain")

    if settings.require_email_verified and not payload.email_verified:
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=email_unverified")

    # Upsert the user. Keycloak is canonical for role; we cache it on the row
    # for fast reads and to avoid a lookup on every request.
    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()
    if user:
        user.email = payload.email
        user.name = payload.name
        user.role = payload.role
    else:
        user = User(
            id=payload.sub,
            email=payload.email,
            name=payload.name,
            role=payload.role,
        )
        db.add(user)
    await db.commit()
    await get_or_create_account(db, payload.sub)

    access_ttl = int(tokens.get("expires_in", 300))
    refresh_ttl = int(tokens.get("refresh_expires_in", 1800))
    resp = RedirectResponse(url=f"{settings.frontend_url}/dashboard")
    _set_session_cookies(
        resp,
        access_token=access_token,
        access_ttl=access_ttl,
        refresh_token=tokens.get("refresh_token"),
        refresh_ttl=refresh_ttl,
    )
    # Clear the one-time PKCE/state cookies.
    resp.delete_cookie("oauth_state", path="/", secure=True, samesite="lax", httponly=True)
    resp.delete_cookie("oauth_pkce", path="/", secure=True, samesite="lax", httponly=True)
    # id_token is needed for RP-initiated logout (`id_token_hint`).
    if "id_token" in tokens:
        resp.set_cookie(
            "id_token",
            tokens["id_token"],
            httponly=True, secure=True, samesite="lax", path="/",
            max_age=refresh_ttl,
        )
    return resp


@router.post("/refresh")
@limiter.limit("60/minute")
async def refresh(request: Request):
    """Use the refresh_token cookie to mint a new access token.

    Origin is checked even though the cookie is HttpOnly — defence-in-depth
    against a CSRF flow that drives the browser to /auth/refresh from a
    malicious origin in our CORS allowlist.
    """
    origin = request.headers.get("origin", "")
    if origin and origin not in settings.cors_origins:
        return Response(status_code=403, content='{"detail":"forbidden origin"}')

    refresh_tok = request.cookies.get("refresh_token")
    if not refresh_tok:
        return Response(status_code=401, content='{"detail":"No refresh token"}')

    data = {
        "grant_type": "refresh_token",
        "client_id": settings.keycloak_client_id,
        "refresh_token": refresh_tok,
    }
    if settings.keycloak_client_secret:
        data["client_secret"] = settings.keycloak_client_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(KEYCLOAK_TOKEN_URL, data=data)

    if token_resp.status_code != 200:
        resp = Response(status_code=401, content='{"detail":"Refresh failed"}')
        _clear_session_cookies(resp)
        return resp

    tokens = token_resp.json()
    access_ttl = int(tokens.get("expires_in", 300))
    refresh_ttl = int(tokens.get("refresh_expires_in", 1800))
    resp = JSONResponse({"message": "refreshed"})
    _set_session_cookies(
        resp,
        access_token=tokens["access_token"],
        access_ttl=access_ttl,
        refresh_token=tokens.get("refresh_token"),
        refresh_ttl=refresh_ttl,
    )
    return resp


@router.get("/me", response_model=UserResponse)
async def me(current_user: TokenPayload = Depends(get_current_user)):
    return UserResponse(
        id=current_user.sub,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
    )


@router.post("/logout")
async def logout(request: Request):
    """RP-initiated logout against Keycloak.

    Revokes the refresh token, clears local cookies, and redirects to the
    Keycloak `end_session_endpoint` so the SSO session is also killed. Without
    this, the user can hit /auth/login and be SSO'd back in without entering
    credentials.
    """
    refresh_tok = request.cookies.get("refresh_token")
    id_token = request.cookies.get("id_token")

    # Best-effort revoke; ignore failures so the user can always log out.
    if refresh_tok:
        try:
            data = {
                "client_id": settings.keycloak_client_id,
                "token": refresh_tok,
                "token_type_hint": "refresh_token",
            }
            if settings.keycloak_client_secret:
                data["client_secret"] = settings.keycloak_client_secret
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(KEYCLOAK_REVOKE_URL, data=data)
        except Exception:
            logger.exception("refresh token revoke failed")

    params = {"post_logout_redirect_uri": f"{settings.frontend_url}/login"}
    if id_token:
        params["id_token_hint"] = id_token
    else:
        params["client_id"] = settings.keycloak_client_id
    redirect_url = f"{KEYCLOAK_LOGOUT_URL}?{urlencode(params)}"

    resp = RedirectResponse(url=redirect_url, status_code=302)
    _clear_session_cookies(resp)
    resp.delete_cookie("id_token", path="/", secure=True, samesite="lax", httponly=True)
    return resp
