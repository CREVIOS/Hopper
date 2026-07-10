"""Per-user application settings persistence (VS Code prefs).

Replaces the old accept-and-discard `PUT /settings/vscode` stub. Stored in the
DB (one row per user) rather than the workspace PVC, so settings survive
independently of any VM and can be served without a running pod.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_setting import UserSetting


async def get_user_settings(db: AsyncSession, user_id: str) -> UserSetting | None:
    return (
        await db.execute(select(UserSetting).where(UserSetting.user_id == user_id))
    ).scalar_one_or_none()


async def set_vscode_settings(db: AsyncSession, user_id: str, vscode: dict) -> UserSetting:
    """Upsert the user's VS Code settings blob (idempotent per user)."""
    row = await get_user_settings(db, user_id)
    if row is None:
        row = UserSetting(id=str(uuid.uuid4()), user_id=user_id, vscode=vscode)
        db.add(row)
    else:
        row.vscode = vscode
    await db.commit()
    await db.refresh(row)
    return row
