"""Per-user persistent workspace (FR-HC-28).

Each user has exactly one workspace PVC, created lazily on first VM launch and
reused for every subsequent session so files/datasets/venvs survive across
sessions. This service owns the DB bookkeeping (name, capacity, storage class);
the orchestrator ensures the actual K8s PVC and mounts it at /workspace.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_workspace import UserWorkspace

# Per-plan workspace capacity in GiB. SRS_ADDENDUM §2.2 fixes small=20, large=100;
# medium is interpolated. Capacity is set at first creation and only ever grows
# via an explicit admin resize (FR-HC-30) — never shrunk on a later launch.
PLAN_WORKSPACE_GB = {"small": 20, "medium": 50, "large": 100}
DEFAULT_WORKSPACE_GB = 20


def pvc_name_for(user_id: str) -> str:
    """Deterministic, DNS-1123-safe PVC name for a user's workspace.

    Keycloak subs are lowercase UUIDs; lower-casing defensively keeps the name
    a valid K8s object name regardless.
    """
    return f"ws-user-{user_id}".lower()


async def get_or_create_workspace(
    db: AsyncSession, user_id: str, plan: str, capacity_gb: int | None = None
) -> UserWorkspace:
    """Return the user's workspace row, creating it on first use.

    Idempotent per user (unique user_id). Capacity is taken from ``capacity_gb``
    when provided (the DB-backed plan's workspace_gb), else falls back to the
    legacy per-plan map. Set once at creation and not changed here.
    """
    existing = (
        await db.execute(select(UserWorkspace).where(UserWorkspace.user_id == user_id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    if capacity_gb is None:
        capacity_gb = PLAN_WORKSPACE_GB.get(plan, DEFAULT_WORKSPACE_GB)

    ws = UserWorkspace(
        id=str(uuid.uuid4()),
        user_id=user_id,
        pvc_name=pvc_name_for(user_id),
        storage_class="",
        capacity_gb=capacity_gb,
    )
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    return ws
