"""Per-user resource quota resolution + management.

A user's effective quota is their ``user_quotas`` row if present, else the
global defaults from config. Enforced at pod-create time.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user_quota import UserQuota


async def get_quota_row(db: AsyncSession, user_id: str) -> UserQuota | None:
    return (
        await db.execute(select(UserQuota).where(UserQuota.user_id == user_id))
    ).scalar_one_or_none()


async def get_effective_quota(db: AsyncSession, user_id: str) -> dict:
    """Return {max_concurrent_vms, max_workspace_gb, is_custom} for a user."""
    row = await get_quota_row(db, user_id)
    if row is not None:
        return {
            "max_concurrent_vms": row.max_concurrent_vms,
            "max_workspace_gb": row.max_workspace_gb,
            "is_custom": True,
        }
    return {
        "max_concurrent_vms": settings.default_max_concurrent_vms,
        "max_workspace_gb": settings.default_max_workspace_gb,
        "is_custom": False,
    }


async def set_quota(
    db: AsyncSession, user_id: str, *, max_concurrent_vms: int, max_workspace_gb: int
) -> UserQuota:
    """Upsert a per-user quota override."""
    row = await get_quota_row(db, user_id)
    if row is None:
        row = UserQuota(
            user_id=user_id,
            max_concurrent_vms=max_concurrent_vms,
            max_workspace_gb=max_workspace_gb,
        )
        db.add(row)
    else:
        row.max_concurrent_vms = max_concurrent_vms
        row.max_workspace_gb = max_workspace_gb
    await db.commit()
    await db.refresh(row)
    return row


async def clear_quota(db: AsyncSession, user_id: str) -> bool:
    """Remove a user's override so they revert to defaults. Returns True if a
    row was deleted.
    """
    row = await get_quota_row(db, user_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True
