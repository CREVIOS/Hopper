"""Per-user persistent workspace (FR-HC-28).

Each user has exactly one workspace PVC, created lazily on first VM launch and
reused for every subsequent session so files/datasets/venvs survive across
sessions. This service owns the DB bookkeeping (name, capacity, storage class);
the orchestrator ensures the actual K8s PVC and mounts it at /workspace.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)


class WorkspaceNotFound(Exception):
    """No workspace row exists for the user (nothing to resize)."""


class ShrinkNotAllowed(Exception):
    """Workspaces only ever grow — shrinking a PVC is unsupported (FR-HC-30)."""

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
    db: AsyncSession,
    user_id: str,
    plan: str,
    capacity_gb: int | None = None,
    max_capacity_gb: int | None = None,
) -> UserWorkspace:
    """Return the user's workspace row, creating it on first use.

    Idempotent per user (unique user_id). Capacity is taken from ``capacity_gb``
    when provided (the DB-backed plan's workspace_gb), else the legacy per-plan map.

    For an existing workspace, capacity is reconciled **upward only** (FR-HC-30):
    if the requested ``capacity_gb`` exceeds the stored size — and does not exceed
    ``max_capacity_gb`` (the user's quota cap, when given) — the row grows and the
    orchestrator expands the PVC on the next launch. It is never shrunk, and a
    request above the quota cap is ignored rather than partially applied.
    """
    existing = (
        await db.execute(select(UserWorkspace).where(UserWorkspace.user_id == user_id))
    ).scalar_one_or_none()
    if existing is not None:
        if (
            capacity_gb is not None
            and capacity_gb > existing.capacity_gb
            and (max_capacity_gb is None or capacity_gb <= max_capacity_gb)
        ):
            logger.info(
                "growing workspace %s: %dGi -> %dGi",
                existing.pvc_name, existing.capacity_gb, capacity_gb,
            )
            existing.capacity_gb = capacity_gb
            await db.commit()
            await db.refresh(existing)
        return existing

    if capacity_gb is None:
        capacity_gb = PLAN_WORKSPACE_GB.get(plan, DEFAULT_WORKSPACE_GB)

    ws = UserWorkspace(
        id=str(uuid.uuid4()),
        user_id=user_id,
        pvc_name=pvc_name_for(user_id),
        # New workspaces adopt the configured class ("" = cluster default). This
        # is the only place the class is chosen; existing rows keep theirs, which
        # is how a mixed local-path/Longhorn fleet is tracked during migration.
        storage_class=settings.workspace_storage_class,
        capacity_gb=capacity_gb,
    )
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    return ws


async def resize_workspace(
    db: AsyncSession, user_id: str, new_capacity_gb: int
) -> UserWorkspace:
    """Admin resize of a user's workspace (FR-HC-30) — **up only**.

    Writes the desired capacity to the DB; the orchestrator expands the actual
    PVC on the user's next VM start. Raises ``WorkspaceNotFound`` if the user has
    no workspace yet, and ``ShrinkNotAllowed`` if ``new_capacity_gb`` is not
    strictly greater than the current size (block-storage cannot shrink).
    """
    ws = (
        await db.execute(select(UserWorkspace).where(UserWorkspace.user_id == user_id))
    ).scalar_one_or_none()
    if ws is None:
        raise WorkspaceNotFound(user_id)
    if new_capacity_gb <= ws.capacity_gb:
        raise ShrinkNotAllowed(
            f"workspace is {ws.capacity_gb}Gi; new size {new_capacity_gb}Gi is not larger"
        )
    logger.info("admin resize workspace %s: %dGi -> %dGi", ws.pvc_name, ws.capacity_gb, new_capacity_gb)
    ws.capacity_gb = new_capacity_gb
    await db.commit()
    await db.refresh(ws)
    return ws
