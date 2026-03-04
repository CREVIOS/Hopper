from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.dependencies import get_current_user
from app.schemas.user import TokenPayload, UserResponse

router = APIRouter()


@router.get("/login")
async def login():
    """Redirect to Keycloak OIDC login."""
    # TODO: Build Keycloak authorization URL
    return RedirectResponse(url="/")


@router.get("/callback")
async def callback(code: str):
    """Handle OIDC callback and exchange code for tokens."""
    # TODO: Exchange authorization code for tokens
    return {"message": "callback"}


@router.post("/refresh")
async def refresh(refresh_token: str):
    """Refresh access token."""
    # TODO: Refresh token via Keycloak
    return {"message": "refreshed"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: TokenPayload = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse(
        id=current_user.sub,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
    )
