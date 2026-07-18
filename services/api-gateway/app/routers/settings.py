from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.schemas.user import TokenPayload
from app.services.settings_service import get_user_settings, set_vscode_settings

router = APIRouter()


@router.get("/vscode")
async def read_vscode_settings(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's persisted VS Code settings blob ({} if none saved)."""
    row = await get_user_settings(db, current_user.sub)
    return {"vscode": row.vscode if row else {}}


@router.put("/vscode")
async def save_vscode_settings(
    settings_body: dict,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist the user's VS Code settings blob (per-user, upserted).

    Previously this accepted the body and discarded it. It is now stored in the
    DB so it survives across sessions (a future enhancement can sync it into the
    VM's code-server config on launch).
    """
    row = await set_vscode_settings(db, current_user.sub, settings_body)
    return {"status": "saved", "vscode": row.vscode}
