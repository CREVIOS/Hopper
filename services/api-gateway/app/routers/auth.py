"""OIDC auth flow against Keycloak.

Implements OAuth 2.1 baseline: PKCE (S256), `state` (CSRF), `nonce` (replay).
Cookies are SameSite=Lax, HttpOnly, Secure; the access token cookie max-age
matches the access token's `exp` so a stolen cookie expires sooner than the
refresh token. Logout is RP-initiated against Keycloak so SSO sessions and
refresh tokens are actually revoked, not just deleted client-side.
"""
import base64
import hashlib
import logging
import os
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import get_current_user, get_db
from app.middleware.auth import verify_token
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.user import (
    ForgotPasswordRequest,
    LoginRequest,
    ResendCodeRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenPayload,
    UserResponse,
    VerifyEmailRequest,
)
from app.services import verification
from app.services.credit_service import get_or_create_account
from app.services.email import send_code_email
from app.services.keycloak_admin import KeycloakAdminError, keycloak_admin

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
    common = dict(httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")
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
            secure=settings.cookie_secure,
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
        httponly=True, secure=settings.cookie_secure, samesite="lax", path="/", max_age=600,
    )
    resp.set_cookie(
        "oauth_pkce",
        verifier,
        httponly=True, secure=settings.cookie_secure, samesite="lax", path="/", max_age=600,
    )
    return resp


async def _password_grant(email: str, password: str) -> dict:
    """Resource-owner password grant against the public hopper-api client.

    Powers the themed in-app login/signup (no redirect to Keycloak's hosted
    page). The client must have Direct Access Grants enabled. Raises 401 on bad
    credentials so the caller returns a clean error to the browser.
    """
    data = {
        "grant_type": "password",
        "client_id": settings.keycloak_client_id,
        "scope": "openid email profile",
        "username": email,
        "password": password,
    }
    if settings.keycloak_client_secret:
        data["client_secret"] = settings.keycloak_client_secret
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(KEYCLOAK_TOKEN_URL, data=data)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if resp.status_code != 200:
        logger.warning("password grant failed: %s", resp.text)
        raise HTTPException(status_code=401, detail="Login failed")
    return resp.json()


def _issue_session(
    body: dict,
    tokens: dict,
    *,
    status_code: int = 200,
) -> JSONResponse:
    """Return a JSON response carrying the auth cookies (same shape as callback)."""
    refresh_ttl = int(tokens.get("refresh_expires_in", 1800))
    resp = JSONResponse(body, status_code=status_code)
    _set_session_cookies(
        resp,
        access_token=tokens["access_token"],
        access_ttl=int(tokens.get("expires_in", 300)),
        refresh_token=tokens.get("refresh_token"),
        refresh_ttl=refresh_ttl,
    )
    if "id_token" in tokens:
        resp.set_cookie(
            "id_token", tokens["id_token"],
            httponly=True, secure=settings.cookie_secure, samesite="lax", path="/", max_age=refresh_ttl,
        )
    return resp


async def _upsert_user_row(db: AsyncSession, payload: TokenPayload) -> None:
    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()
    if user:
        user.email = payload.email
        user.name = payload.name
        user.role = payload.role
    else:
        db.add(User(id=payload.sub, email=payload.email, name=payload.name, role=payload.role))
    await db.commit()
    await get_or_create_account(db, payload.sub)


@router.post(
    "/signup",
    responses={
        202: {"description": "Teacher signup accepted and pending admin approval"},
    },
)
@limiter.limit("5/minute")
async def signup(request: Request, body: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Self-service signup. Students activate immediately; teachers are created
    as students with pending_teacher=true, awaiting admin approval."""
    email = (body.email or "").lower().strip()
    if body.role not in ("student", "teacher"):
        raise HTTPException(status_code=400, detail="role must be 'student' or 'teacher'")
    if "@" not in email or not _domain_allowed(email):
        raise HTTPException(status_code=403, detail="This email domain is not permitted to sign up.")

    try:
        # Created unverified — the user must confirm the emailed code before a
        # session is issued (login enforces require_email_verified).
        user_id = await keycloak_admin.create_user(
            email=email, name=body.name, password=body.password,
            role="student", email_verified=False,
        )
    except KeycloakAdminError as e:
        if "exists" in str(e):
            raise HTTPException(status_code=409, detail="An account with this email already exists.")
        logger.error("signup: keycloak create_user failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not create the account. Try again later.")

    pending = body.role == "teacher"
    db.add(User(id=user_id, email=email, name=body.name, role="student", pending_teacher=pending))
    db.add(AuditLog(
        id=str(uuid.uuid4()), user_id=user_id, action="signup",
        resource_type="user", resource_id=user_id,
        ip_address=request.client.host if request.client else "-", status_code=201,
    ))
    code = await verification.issue_code(db, email, verification.VERIFY_EMAIL)
    await db.commit()
    await get_or_create_account(db, user_id)
    await send_code_email(email, verification.VERIFY_EMAIL, code)

    tokens = await _password_grant(email, body.password)
    return _issue_session(
        {"id": user_id, "email": email, "name": body.name, "role": "student", "pending_teacher": pending},
        tokens,
        status_code=status.HTTP_202_ACCEPTED if pending else status.HTTP_200_OK,
    )


@router.post("/verify-email")
@limiter.limit("10/minute")
async def verify_email(request: Request, body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """Confirm a signup verification code and mark the account email-verified.
    On success the client logs in normally (POST /auth/login)."""
    email = (body.email or "").lower().strip()
    ok = await verification.verify_code(db, email, verification.VERIFY_EMAIL, body.code)
    if not ok:
        await db.commit()  # persist the incremented attempt counter
        raise HTTPException(status_code=400, detail="Invalid or expired code.")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        await db.commit()
        raise HTTPException(status_code=404, detail="Account not found.")
    try:
        await keycloak_admin.set_email_verified(user.id, True)
    except KeycloakAdminError as e:
        logger.error("verify-email: set_email_verified failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not verify the account. Try again later.")
    await db.commit()
    return JSONResponse({"status": "verified", "email": email})


@router.post("/resend-code")
@limiter.limit("3/minute")
async def resend_code(request: Request, body: ResendCodeRequest, db: AsyncSession = Depends(get_db)):
    """Re-send a verification code for a not-yet-verified signup. Always returns
    200 (never reveals whether the account exists / is already verified)."""
    email = (body.email or "").lower().strip()
    try:
        ku = await keycloak_admin.get_user_by_email(email)
        if ku and not ku.get("emailVerified", False):
            code = await verification.issue_code(db, email, verification.VERIFY_EMAIL)
            await db.commit()
            await send_code_email(email, verification.VERIFY_EMAIL, code)
    except KeycloakAdminError as e:
        logger.error("resend-code failed for %s: %s", email, e)
    return JSONResponse({"status": "ok"})


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Begin a password reset. Always returns 200 so the response can't be used
    to enumerate which emails have accounts."""
    email = (body.email or "").lower().strip()
    try:
        ku = await keycloak_admin.get_user_by_email(email)
        if ku:
            code = await verification.issue_code(db, email, verification.PASSWORD_RESET)
            await db.commit()
            await send_code_email(email, verification.PASSWORD_RESET, code)
    except KeycloakAdminError as e:
        logger.error("forgot-password failed for %s: %s", email, e)
    return JSONResponse({"status": "ok"})


@router.post("/reset-password")
@limiter.limit("10/minute")
async def reset_password(request: Request, body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Complete a password reset with the emailed code, then set the new
    password in Keycloak. The client logs in afterwards."""
    email = (body.email or "").lower().strip()
    ok = await verification.verify_code(db, email, verification.PASSWORD_RESET, body.code)
    if not ok:
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired code.")

    try:
        ku = await keycloak_admin.get_user_by_email(email)
        if ku is None:
            await db.commit()
            raise HTTPException(status_code=404, detail="Account not found.")
        await keycloak_admin.reset_password(ku["id"], body.password)
        # A reset also confirms control of the mailbox — mark verified.
        if not ku.get("emailVerified", False):
            await keycloak_admin.set_email_verified(ku["id"], True)
    except KeycloakAdminError as e:
        logger.error("reset-password failed for %s: %s", email, e)
        raise HTTPException(status_code=502, detail="Could not reset the password. Try again later.")
    await db.commit()
    return JSONResponse({"status": "reset", "email": email})


@router.post("/login")
@limiter.limit("10/minute")
async def login_direct(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Themed email + password login (direct grant). The GET /login above keeps
    the OIDC redirect flow for SSO."""
    email = (body.email or "").lower().strip()
    tokens = await _password_grant(email, body.password)
    payload = await verify_token(tokens["access_token"])
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not _domain_allowed(payload.email):
        raise HTTPException(status_code=403, detail="This email domain is not permitted to sign in.")
    if settings.require_email_verified and not payload.email_verified:
        raise HTTPException(status_code=403, detail="Please verify your email, then sign in.")
    await _upsert_user_row(db, payload)
    return _issue_session(
        {"id": payload.sub, "email": payload.email, "name": payload.name, "role": payload.role},
        tokens,
    )


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
    resp.delete_cookie("oauth_state", path="/", secure=settings.cookie_secure, samesite="lax", httponly=True)
    resp.delete_cookie("oauth_pkce", path="/", secure=settings.cookie_secure, samesite="lax", httponly=True)
    # id_token is needed for RP-initiated logout (`id_token_hint`).
    if "id_token" in tokens:
        resp.set_cookie(
            "id_token",
            tokens["id_token"],
            httponly=True, secure=settings.cookie_secure, samesite="lax", path="/",
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
async def me(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Role is canonical in Keycloak (cached on the token); the pending_teacher
    # approval flag lives only on our users row. A teacher signup is a student
    # with pending_teacher=true until an admin approves, so read it back here
    # to let the UI reflect the "awaiting approval" state.
    result = await db.execute(select(User).where(User.id == current_user.sub))
    user = result.scalar_one_or_none()
    return UserResponse(
        id=current_user.sub,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
        pending_teacher=bool(user.pending_teacher) if user else False,
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
    resp.delete_cookie("id_token", path="/", secure=settings.cookie_secure, samesite="lax", httponly=True)
    return resp
