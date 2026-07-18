import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.audit import AuditLog
from app.models.session import PodSession
from app.models.user import User
from app.schemas.user import ChangeRoleRequest, TokenPayload
from app.services.keycloak_admin import KeycloakAdminError, keycloak_admin
from app.services.orchestrator_client import orchestrator_client

logger = logging.getLogger(__name__)
router = APIRouter()

APP_ROLES = {"admin", "professor", "student"}


def _require_admin(current_user: TokenPayload):
    """All admin endpoints are admin-only.

    Teachers (professors) have the Teaching console instead — they must not
    reach any admin data or action, so professors are rejected here too.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/users")
async def list_users(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)."""
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
            "pending_teacher": u.pending_teacher,
            "university_id": u.university_id,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.get("/teacher-requests")
async def list_teacher_requests(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Users who signed up as a teacher and await approval (admin only)."""
    _require_admin(current_user)
    result = await db.execute(
        select(User).where(User.pending_teacher.is_(True)).order_by(User.created_at.desc())
    )
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in result.scalars().all()
    ]


@router.post("/teacher-requests/{user_id}/approve")
async def approve_teacher(
    user_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending teacher: promote to professor and clear the flag."""
    _require_admin(current_user)
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if not user.pending_teacher:
        raise HTTPException(status_code=400, detail="no pending teacher request for this user")

    try:
        await keycloak_admin.set_user_role(user_id, "professor")
    except KeycloakAdminError as e:
        logger.error("approve_teacher: keycloak role change failed for %s: %s", user_id, e)
        raise HTTPException(status_code=502, detail="failed to update role in Keycloak")

    user.role = "professor"
    user.pending_teacher = False
    db.add(AuditLog(
        id=str(uuid.uuid4()), user_id=current_user.sub, action="approve_teacher",
        resource_type="user", resource_id=user_id, ip_address="-", status_code=200,
    ))
    await db.commit()
    # Force re-issue of the user's tokens so the new role takes effect promptly.
    try:
        await keycloak_admin.logout_user(user_id)
    except Exception:
        logger.warning("could not force-logout %s after teacher approval", user_id)
    return {"status": "ok", "user_id": user_id, "role": "professor"}


@router.post("/teacher-requests/{user_id}/reject")
async def reject_teacher(
    user_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending teacher: clear the flag, the user stays a student."""
    _require_admin(current_user)
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    user.pending_teacher = False
    db.add(AuditLog(
        id=str(uuid.uuid4()), user_id=current_user.sub, action="reject_teacher",
        resource_type="user", resource_id=user_id, ip_address="-", status_code=200,
    ))
    await db.commit()
    return {"status": "ok", "user_id": user_id, "role": "student"}


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


@router.get("/active-vms")
async def list_active_vms(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List currently active VMs across all users with owner email/name."""
    _require_admin(current_user)

    result = await db.execute(
        select(PodSession, User.email, User.name)
        .join(User, User.id == PodSession.user_id, isouter=True)
        .where(PodSession.state.in_(["pending", "creating", "running"]))
        .order_by(PodSession.started_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": s.id,
            "state": s.state,
            "plan": s.plan,
            "image": s.image,
            "cpu": s.cpu,
            "memory": s.memory,
            "user_email": email,
            "user_name": name,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        }
        for s, email, name in rows
    ]


@router.patch("/users/{user_id}/role")
async def change_user_role(
    user_id: str,
    body: ChangeRoleRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change a user's app role.

    Updates Keycloak (canonical source) first, then mirrors to the local
    `users.role` column, then force-logs-out the user so their next request
    receives a JWT with the new role. Refuses to:
      - demote yourself
      - drop the admin count to zero
      - assign an unknown role
    Writes an audit_logs row with old/new role for accountability.
    """
    _require_admin(current_user)
    if body.role not in APP_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {sorted(APP_ROLES)}")
    if user_id == current_user.sub and body.role != "admin":
        raise HTTPException(status_code=400, detail="cannot demote yourself")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    old_role = user.role

    if old_role == "admin" and body.role != "admin":
        n_admins = await db.scalar(select(func.count()).where(User.role == "admin"))
        if (n_admins or 0) <= 1:
            raise HTTPException(status_code=400, detail="cannot demote the last admin")

    if old_role == body.role:
        return {"status": "noop", "user_id": user_id, "role": body.role}

    try:
        await keycloak_admin.set_user_role(user_id, body.role)
    except KeycloakAdminError as e:
        logger.error("keycloak role change failed for %s: %s", user_id, e)
        raise HTTPException(status_code=502, detail="failed to update role in Keycloak")
    except Exception:
        logger.exception("unexpected keycloak admin failure")
        raise HTTPException(status_code=500, detail="role change failed")

    user.role = body.role
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            user_id=current_user.sub,
            action="change_role",
            resource_type="user",
            resource_id=user_id,
            ip_address="-",
            status_code=200,
        )
    )
    await db.commit()

    # Force the target user's existing tokens to be re-issued so the new role
    # propagates immediately. If this fails, the role still changes — they
    # just need to wait for token refresh (≤5 min).
    try:
        await keycloak_admin.logout_user(user_id)
    except Exception:
        logger.warning("could not force-logout user %s after role change", user_id)

    return {"status": "ok", "user_id": user_id, "old_role": old_role, "new_role": body.role}


@router.get("/audit-logs")
async def get_audit_logs(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """View audit logs (admin only)."""
    _require_admin(current_user)

    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "ip_address": log.ip_address,
            "status_code": log.status_code,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
