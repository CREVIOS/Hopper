from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.middleware.auth import verify_token
from app.models.user import User
from app.schemas.user import TokenPayload, UserResponse
from app.services.credit_service import get_or_create_account

router = APIRouter()

KEYCLOAK_AUTH_URL = (
    f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/auth"
)
KEYCLOAK_TOKEN_URL = (
    f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"
)
CALLBACK_URL = "http://localhost:5173/api/auth/callback"


@router.get("/login")
async def login():
    """Redirect to Keycloak OIDC login."""
    params = urlencode({
        "client_id": settings.keycloak_client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": CALLBACK_URL,
    })
    return RedirectResponse(url=f"{KEYCLOAK_AUTH_URL}?{params}")


@router.get("/callback")
async def callback(code: str, response: Response, db: AsyncSession = Depends(get_db)):
    """Handle OIDC callback and exchange code for tokens."""
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            KEYCLOAK_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.keycloak_client_id,
                "code": code,
                "redirect_uri": CALLBACK_URL,
            },
        )
    if token_resp.status_code != 200:
        return {"error": "Token exchange failed", "detail": token_resp.text}

    tokens = token_resp.json()
    access_token = tokens["access_token"]

    # Decode the token to get user claims
    payload = await verify_token(access_token)
    if payload:
        # Upsert user in DB
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

        # Auto-create credit account for new users
        await get_or_create_account(db, payload.sub)

    resp = RedirectResponse(url="http://localhost:5173/dashboard")
    resp.set_cookie(
        key="session_token",
        value=access_token,
        httponly=True,
        max_age=tokens.get("expires_in", 300),
        samesite="lax",
    )
    return resp


@router.post("/refresh")
async def refresh(refresh_token: str):
    """Refresh access token."""
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            KEYCLOAK_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.keycloak_client_id,
                "refresh_token": refresh_token,
            },
        )
    return token_resp.json()


@router.get("/me", response_model=UserResponse)
async def me(current_user: TokenPayload = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse(
        id=current_user.sub,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
    )


@router.post("/logout")
async def logout():
    """Clear session cookie and redirect to login."""
    resp = RedirectResponse(url="http://localhost:5173/login", status_code=302)
    resp.delete_cookie(key="session_token")
    return resp
