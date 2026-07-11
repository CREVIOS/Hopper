"""Data access for the admin-configurable VM plan catalogue (``vm_plans``).

Encapsulates all reads/writes behind a small repository so routers depend on
this interface rather than raw SQL. The plan ``name`` is the primary key and the
stable identifier used across the gateway, orchestrator, and pod records.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vm_plan import VmPlanRow


async def list_plans(db: AsyncSession, *, include_inactive: bool = False) -> list[VmPlanRow]:
    stmt = select(VmPlanRow)
    if not include_inactive:
        stmt = stmt.where(VmPlanRow.is_active.is_(True))
    stmt = stmt.order_by(VmPlanRow.credits_per_hour)
    return list((await db.execute(stmt)).scalars().all())


async def get_plan(db: AsyncSession, name: str, *, active_only: bool = False) -> VmPlanRow | None:
    stmt = select(VmPlanRow).where(VmPlanRow.name == name)
    if active_only:
        stmt = stmt.where(VmPlanRow.is_active.is_(True))
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_plan(
    db: AsyncSession,
    *,
    name: str,
    display_name: str,
    cpu: str,
    memory: str,
    disk: str,
    credits_per_hour: float,
    workspace_gb: int,
) -> VmPlanRow:
    plan = VmPlanRow(
        name=name,
        display_name=display_name,
        cpu=cpu,
        memory=memory,
        disk=disk,
        credits_per_hour=credits_per_hour,
        workspace_gb=workspace_gb,
        is_active=True,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def update_plan(db: AsyncSession, plan: VmPlanRow, fields: dict) -> VmPlanRow:
    """Apply the given non-None fields to an existing plan row (immutable-style:
    only the provided keys change). ``name`` is the immutable PK and is ignored.
    """
    for key, value in fields.items():
        if key == "name" or value is None:
            continue
        setattr(plan, key, value)
    await db.commit()
    await db.refresh(plan)
    return plan


async def deactivate_plan(db: AsyncSession, plan: VmPlanRow) -> VmPlanRow:
    """Soft-delete: mark inactive. Existing pods on the plan keep billing."""
    plan.is_active = False
    await db.commit()
    await db.refresh(plan)
    return plan
