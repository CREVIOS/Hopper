import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.session import PodSession
from app.schemas.user import TokenPayload
from app.services.orchestrator_client import orchestrator_client

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(current_user: TokenPayload):
    if current_user.role not in ("admin", "professor"):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/users")
async def list_users(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin/professor only)."""
    _require_admin(current_user)

    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "university_id": u.university_id,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.get("/courses")
async def list_courses(current_user: TokenPayload = Depends(get_current_user)):
    """List courses and their resource quotas.

    Not yet implemented — no course model in the DB.
    Returns an empty list for the POC.
    """
    _require_admin(current_user)
    return []


@router.get("/nodes")
async def list_nodes(current_user: TokenPayload = Depends(get_current_user)):
    """List compute nodes and their resource usage.

    Calls the orchestrator's ListNodes gRPC to get real K8s node info
    including CPU/memory capacity, allocatable resources, and pod counts.
    """
    _require_admin(current_user)

    try:
        nodes = await orchestrator_client.list_nodes()
        return [
            {
                "name": n.name,
                "cpu_capacity": n.cpu_capacity,
                "memory_capacity": n.memory_capacity,
                "cpu_allocatable": n.cpu_allocatable,
                "memory_allocatable": n.memory_allocatable,
                "pod_count": n.pod_count,
                "ready": n.ready,
            }
            for n in nodes
        ]
    except Exception as e:
        logger.error("Failed to list nodes: %s", e)
        raise HTTPException(status_code=502, detail="Could not reach orchestrator")


@router.get("/stats")
async def get_stats(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard stats: total users, active VMs, etc."""
    _require_admin(current_user)

    user_count = await db.scalar(select(func.count()).select_from(User))
    active_pods = await db.scalar(
        select(func.count())
        .select_from(PodSession)
        .where(PodSession.state.in_(["pending", "creating", "running"]))
    )
    total_pods = await db.scalar(select(func.count()).select_from(PodSession))

    return {
        "total_users": user_count or 0,
        "active_vms": active_pods or 0,
        "total_vms_created": total_pods or 0,
    }
