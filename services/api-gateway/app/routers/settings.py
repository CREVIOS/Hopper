from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.schemas.user import TokenPayload

router = APIRouter()

@router.put("/vscode")
async def save_vscode_settings(
    settings_body: dict,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Store VS Code settings blob per user.
    
    The orchestrator mounts the user's PVC at /workspace/.vscode/settings.json.
    code-server picks this up automatically on next launch.
    """
    raise HTTPException(
        status_code=501,
        detail="VS Code settings persistence is not implemented yet",
    )
