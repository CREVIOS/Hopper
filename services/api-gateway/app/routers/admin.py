import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.audit import AuditLog
from app.models.session import PodSession
from app.models.user import User
from app.models.user_workspace import UserWorkspace
from app.schemas.image import ImageCreateRequest, ImageResponse, ImageUpdateRequest
from app.schemas.plan import PlanCreateRequest, PlanResponse, PlanUpdateRequest
from app.schemas.quota import QuotaResponse, QuotaSetRequest
from app.schemas.user import ChangeRoleRequest, TokenPayload
from app.schemas.workspace import WorkspaceResizeRequest
from app.services import image_service, plan_service, quota_service, workspace_service
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
    # Deliberately NOT force-logging the user out here. This is a pure
    # elevation (student → professor), so their current token grants strictly
    # less than the new role — nothing to revoke. Killing the Keycloak session
    # would also revoke the refresh token, and the session can only pick the
    # new role up via a refresh, which left an approved-but-signed-in teacher
    # stuck as a student until they manually logged out and back in.
    # /auth/me now reports role_stale and the frontend refreshes in place.
    # (Demotions still force a logout — see change_role below.)
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


# --- VM plan catalogue (admin CRUD) -----------------------------------------
# Mutations here are captured by AuditMiddleware (all POST/PUT/DELETE), so no
# explicit audit rows are written (avoids the double-logging seen elsewhere).


@router.get("/plans", response_model=list[PlanResponse])
async def admin_list_plans(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List every plan, including inactive ones (admin view)."""
    _require_admin(current_user)
    plans = await plan_service.list_plans(db, include_inactive=True)
    return [PlanResponse.model_validate(p) for p in plans]


@router.post("/plans", response_model=PlanResponse, status_code=201)
async def admin_create_plan(
    body: PlanCreateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new VM plan."""
    _require_admin(current_user)
    if await plan_service.get_plan(db, body.name) is not None:
        raise HTTPException(status_code=409, detail=f"Plan '{body.name}' already exists")
    plan = await plan_service.create_plan(db, **body.model_dump())
    return PlanResponse.model_validate(plan)


@router.put("/plans/{name}", response_model=PlanResponse)
async def admin_update_plan(
    name: str,
    body: PlanUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a plan's resources / pricing / active flag (name is immutable)."""
    _require_admin(current_user)
    plan = await plan_service.get_plan(db, name)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan '{name}' not found")
    updated = await plan_service.update_plan(db, plan, body.model_dump(exclude_unset=True))
    return PlanResponse.model_validate(updated)


@router.delete("/plans/{name}")
async def admin_delete_plan(
    name: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (deactivate) a plan. Existing pods on it keep billing."""
    _require_admin(current_user)
    plan = await plan_service.get_plan(db, name)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan '{name}' not found")
    await plan_service.deactivate_plan(db, plan)
    return {"message": "deactivated", "name": name}


# --- Per-user quotas ---------------------------------------------------------


@router.get("/users/{user_id}/quota", response_model=QuotaResponse)
async def admin_get_quota(
    user_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a user's effective quota (their override or the global default)."""
    _require_admin(current_user)
    return QuotaResponse(**await quota_service.get_effective_quota(db, user_id))


@router.put("/users/{user_id}/quota", response_model=QuotaResponse)
async def admin_set_quota(
    user_id: str,
    body: QuotaSetRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set a per-user quota override."""
    _require_admin(current_user)
    await quota_service.set_quota(
        db, user_id,
        max_concurrent_vms=body.max_concurrent_vms,
        max_workspace_gb=body.max_workspace_gb,
    )
    return QuotaResponse(**await quota_service.get_effective_quota(db, user_id))


@router.delete("/users/{user_id}/quota", response_model=QuotaResponse)
async def admin_clear_quota(
    user_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a user's override so they revert to the global default quota."""
    _require_admin(current_user)
    await quota_service.clear_quota(db, user_id)
    return QuotaResponse(**await quota_service.get_effective_quota(db, user_id))


# --- Per-user workspaces (FR-HC-30) -----------------------------------------


@router.get("/workspaces")
async def admin_list_workspaces(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every user's persistent workspace, with owner + storage details."""
    _require_admin(current_user)
    rows = (
        await db.execute(
            select(UserWorkspace, User)
            .join(User, User.id == UserWorkspace.user_id, isouter=True)
            .order_by(UserWorkspace.created_at.desc())
        )
    ).all()
    return [
        {
            "user_id": ws.user_id,
            "user_email": u.email if u else None,
            "user_name": u.name if u else None,
            "pvc_name": ws.pvc_name,
            "storage_class": ws.storage_class or "",
            "capacity_gb": ws.capacity_gb,
            "used_gb": float(ws.used_gb) if ws.used_gb is not None else None,
            "created_at": ws.created_at.isoformat() if ws.created_at else None,
            "last_mounted_at": ws.last_mounted_at.isoformat() if ws.last_mounted_at else None,
        }
        for ws, u in rows
    ]


@router.post("/workspaces/{user_id}/resize")
async def admin_resize_workspace(
    user_id: str,
    body: WorkspaceResizeRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grow a user's workspace (up only). Takes effect at the user's next VM start."""
    _require_admin(current_user)
    quota = await quota_service.get_effective_quota(db, user_id)
    if body.capacity_gb > quota["max_workspace_gb"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{body.capacity_gb} GB exceeds the user's storage quota "
                f"({quota['max_workspace_gb']} GB) — raise the quota first"
            ),
        )
    try:
        ws = await workspace_service.resize_workspace(db, user_id, body.capacity_gb)
    except workspace_service.WorkspaceNotFound:
        raise HTTPException(status_code=404, detail="User has no workspace yet")
    except workspace_service.ShrinkNotAllowed as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"user_id": user_id, "capacity_gb": ws.capacity_gb, "applies": "next-start"}


# --- VM image / template catalogue (admin CRUD) -----------------------------


@router.get("/images", response_model=list[ImageResponse])
async def admin_list_images(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List every image/template, including inactive ones (admin view)."""
    _require_admin(current_user)
    images = await image_service.list_images(db, include_inactive=True)
    return [ImageResponse.model_validate(i) for i in images]


@router.post("/images", response_model=ImageResponse, status_code=201)
async def admin_create_image(
    body: ImageCreateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new VM template → image mapping."""
    _require_admin(current_user)
    if await image_service.get_image(db, body.template) is not None:
        raise HTTPException(status_code=409, detail=f"Template '{body.template}' already exists")
    image = await image_service.create_image(db, **body.model_dump())
    return ImageResponse.model_validate(image)


@router.put("/images/{template}", response_model=ImageResponse)
async def admin_update_image(
    template: str,
    body: ImageUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a template's image / metadata / active + default flags."""
    _require_admin(current_user)
    row = await image_service.get_image(db, template)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Template '{template}' not found")
    updated = await image_service.update_image(db, row, body.model_dump(exclude_unset=True))
    return ImageResponse.model_validate(updated)


@router.delete("/images/{template}")
async def admin_delete_image(
    template: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (deactivate) a template."""
    _require_admin(current_user)
    row = await image_service.get_image(db, template)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Template '{template}' not found")
    await image_service.deactivate_image(db, row)
    return {"message": "deactivated", "template": template}
