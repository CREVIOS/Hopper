from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.schemas.user import TokenPayload

router = APIRouter()

@router.put("/vscode")
async def save_vscode_settings(
    settings_body: dict,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Store VS Code settings blob per user.
    
    The orchestrator mounts the user's PVC at /workspace/.vscode/settings.json.
    code-server picks this up automatically on next launch.
    """
    # Store in user record or a dedicated settings table
    # For now, write to the user's PVC path via a K8s ConfigMap or direct PVC write
    # Implementation depends on your PVC strategy — see Phase 5
    return {"status": "saved"}