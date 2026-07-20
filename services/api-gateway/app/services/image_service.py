"""Data access for the admin-configurable VM image/template catalogue.

Repository over ``vm_images``. Keeps the "default" flag single-valued so a
launch that omits a template always resolves to exactly one image.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vm_image import VmImageRow


async def list_images(db: AsyncSession, *, include_inactive: bool = False) -> list[VmImageRow]:
    stmt = select(VmImageRow)
    if not include_inactive:
        stmt = stmt.where(VmImageRow.is_active.is_(True))
    stmt = stmt.order_by(VmImageRow.is_default.desc(), VmImageRow.template)
    return list((await db.execute(stmt)).scalars().all())


async def get_image(db: AsyncSession, template: str, *, active_only: bool = False) -> VmImageRow | None:
    stmt = select(VmImageRow).where(VmImageRow.template == template)
    if active_only:
        stmt = stmt.where(VmImageRow.is_active.is_(True))
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_default_image(db: AsyncSession) -> VmImageRow | None:
    stmt = select(VmImageRow).where(
        VmImageRow.is_default.is_(True), VmImageRow.is_active.is_(True)
    )
    return (await db.execute(stmt)).scalars().first()


async def _clear_default(db: AsyncSession) -> None:
    await db.execute(update(VmImageRow).values(is_default=False))


async def create_image(
    db: AsyncSession,
    *,
    template: str,
    display_name: str,
    image: str,
    description: str = "",
    is_default: bool = False,
) -> VmImageRow:
    if is_default:
        await _clear_default(db)
    row = VmImageRow(
        template=template,
        display_name=display_name,
        image=image,
        description=description,
        is_active=True,
        is_default=is_default,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_image(db: AsyncSession, row: VmImageRow, fields: dict) -> VmImageRow:
    """Apply provided (non-None) fields. Setting is_default=True clears the flag
    on all other rows first so it stays single-valued. ``template`` is immutable.
    """
    if fields.get("is_default") is True:
        await _clear_default(db)
    for key, value in fields.items():
        if key == "template" or value is None:
            continue
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


async def deactivate_image(db: AsyncSession, row: VmImageRow) -> VmImageRow:
    row.is_active = False
    row.is_default = False
    await db.commit()
    await db.refresh(row)
    return row
