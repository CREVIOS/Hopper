from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.schemas.user import TokenPayload

router = APIRouter()


@router.get("/users")
async def list_users(current_user: TokenPayload = Depends(get_current_user)):
    """List all users (admin only)."""
    # TODO: Check admin role, query users
    return []


@router.get("/courses")
async def list_courses(current_user: TokenPayload = Depends(get_current_user)):
    """List courses and their resource quotas."""
    # TODO: Query course configurations
    return []


@router.get("/gpu-nodes")
async def list_gpu_nodes(current_user: TokenPayload = Depends(get_current_user)):
    """List GPU nodes and their status."""
    # TODO: Query node status from orchestrator
    return []
