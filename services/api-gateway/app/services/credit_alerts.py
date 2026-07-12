"""Low-credit warnings and the credit-exhaustion grace period (FR-HC-18).

Two jobs:

1. **Warn before the lights go out.** On each billing tick we work out how many
   minutes of VM time the user's balance still buys, and fire a notification as
   the remaining time crosses 60 / 30 / 10 / 5 minutes. Deduped per (VM, band)
   so a once-a-minute billing tick doesn't spam the bell.

2. **Grace, not a guillotine.** When a tick fails for lack of credits we don't
   kill the VM outright — we stamp ``credit_grace_until`` and tell the user.
   A monitor terminates the VM when that deadline passes, *unless* they topped
   up in the meantime, in which case the grace is simply cleared.

``credit_grace_until`` is deliberately its own column rather than reusing
``expires_at``: that field is the session TTL enforced by the session reaper, so
overloading it would both destroy the real TTL and make the reaper kill the VM at
the grace deadline for the wrong reason.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import nats as nats_client
from app.core.database import async_session
from app.models.session import PodSession
from app.schemas.pod import VM_PLAN_RESOURCES
from app.services import plan_service
from app.services.credit_service import get_balance
from app.services.notification_service import create_notification_safely

logger = logging.getLogger(__name__)

_ADVISORY_LOCK_KEY = 907_314_004  # distinct from the session reaper's key

# States that represent a live, billing VM.
ACTIVE_STATES = ("pending", "creating", "running")

# Remaining-minutes bands. Crossing into a band fires exactly one notification.
# (lower, upper] -> threshold label
_WARNING_BANDS: tuple[tuple[float, float, int], ...] = (
    (30, 60, 60),
    (10, 30, 30),
    (5, 10, 10),
    (0, 5, 5),
)


def warning_threshold_for_minutes(minutes_remaining: float) -> int | None:
    """The band a given remaining-time falls into, or None if there's plenty left."""
    if minutes_remaining <= 0:
        return None
    for lower, upper, threshold in _WARNING_BANDS:
        if lower < minutes_remaining <= upper:
            return threshold
    return None


async def hourly_rate_for_plan(db: AsyncSession, plan: str) -> float:
    """Credits per hour for a plan, from the DB catalogue.

    Plans are admin-editable (``vm_plans``), so the rate is read from the DB
    rather than a constant. Falls back to the built-in table for a plan whose
    row has been deleted, so a stale pod still bills at a sane rate.
    """
    row = await plan_service.get_plan(db, plan)
    if row is not None:
        return float(row.credits_per_hour)

    for vm_plan, resources in VM_PLAN_RESOURCES.items():
        if vm_plan.value == plan:
            return float(resources["credits_per_hour"])
    return 0.0


async def user_hourly_burn_rate(db: AsyncSession, user_id: str) -> float:
    """Combined credits/hour across every live VM the user owns.

    A user with three VMs burns credits three times as fast, so the warning has
    to be based on the total, not the one VM that happened to trigger the tick.
    """
    plans = (
        await db.scalars(
            select(PodSession.plan).where(
                PodSession.user_id == user_id,
                PodSession.state.in_(ACTIVE_STATES),
            )
        )
    ).all()

    total = 0.0
    for plan in plans:
        total += await hourly_rate_for_plan(db, plan)
    return total


async def get_billing_session(db: AsyncSession, pod_id: str) -> PodSession | None:
    """Look a session up by either id the orchestrator might send.

    Fresh pods are billed under their K8s name (``vm-<nano>``) until a reconcile
    relabels them to the session UUID — match on both.
    """
    return await db.scalar(
        select(PodSession).where(
            or_(PodSession.id == pod_id, PodSession.pod_name == pod_id)
        )
    )


async def maybe_warn_low_credits(
    db: AsyncSession, *, session: PodSession, balance: float
) -> None:
    """Fire a low-credit warning if the balance has crossed a new band."""
    hourly_rate = await user_hourly_burn_rate(db, session.user_id)
    if hourly_rate <= 0:
        return

    minutes_remaining = balance / (hourly_rate / 60.0)
    threshold = warning_threshold_for_minutes(minutes_remaining)
    if threshold is None:
        return

    approx = max(1, int(round(minutes_remaining)))
    await create_notification_safely(
        db,
        user_id=session.user_id,
        type="credit_warning",
        severity="warning",
        title="Low credits",
        body=f"About {approx} minute{'' if approx == 1 else 's'} of VM time remaining. "
             "Save your work or top up.",
        action_url="/credits",
        # One notification per VM per band — the tick is once a minute.
        dedupe_key=f"credit-warning:{session.id}:{threshold}",
        metadata={
            "pod_id": session.id,
            "minutes_remaining": minutes_remaining,
            "threshold_minutes": threshold,
        },
    )


async def start_credit_grace(
    db: AsyncSession, *, session: PodSession, now: datetime | None = None
) -> None:
    """Begin the grace window for a VM whose owner has run out of credits."""
    now = now or datetime.utcnow()

    if session.credit_grace_until is None:
        session.credit_grace_until = now + timedelta(minutes=settings.credit_grace_minutes)
        await db.commit()
        await db.refresh(session)

    minutes = int(settings.credit_grace_minutes)
    await create_notification_safely(
        db,
        user_id=session.user_id,
        type="credit_grace",
        severity="error",
        title="Credits exhausted",
        body=f"Your VM stops in {minutes} minutes unless you add credits. Save your work now.",
        action_url="/credits",
        dedupe_key=f"credit-grace:{session.id}:{session.credit_grace_until.isoformat()}",
        metadata={
            "pod_id": session.id,
            "grace_until": session.credit_grace_until.isoformat(),
        },
    )


async def publish_billing_exhausted(pod_id: str, user_id: str) -> None:
    """Tell the orchestrator to kill the VM (it owns the actual teardown)."""
    nc = nats_client.get_nc()
    await nc.publish(
        "billing.exhausted",
        json.dumps({"pod_id": pod_id, "user_id": user_id}).encode(),
    )


async def process_expired_graces(db: AsyncSession, now: datetime | None = None) -> int:
    """Resolve every grace window whose deadline has passed.

    Topped up in time → clear the grace and let the VM live.
    Still short       → ask the orchestrator to terminate it, and say why.

    Returns the number of sessions resolved. ``now`` is injectable for tests.
    """
    now = now or datetime.utcnow()
    sessions = (
        await db.scalars(
            select(PodSession).where(
                PodSession.credit_grace_until.is_not(None),
                PodSession.credit_grace_until <= now,
                PodSession.state.in_(ACTIVE_STATES),
            )
        )
    ).all()

    resolved = 0
    for session in sessions:
        balance = await get_balance(db, session.user_id)
        # Enough to pay for at least one more minute of this VM? Then they made it.
        rate_per_minute = await hourly_rate_for_plan(db, session.plan) / 60.0

        if rate_per_minute > 0 and balance >= rate_per_minute:
            session.credit_grace_until = None
            await db.commit()
            await create_notification_safely(
                db,
                user_id=session.user_id,
                type="credits_received",
                severity="success",
                title="VM kept running",
                body="Credits were added in time — your VM is still running.",
                action_url="/pods",
                dedupe_key=f"credit-grace-cleared:{session.id}:{now.isoformat()}",
                metadata={"pod_id": session.id},
            )
            resolved += 1
            continue

        try:
            await publish_billing_exhausted(session.pod_name or session.id, session.user_id)
        except Exception:
            # Leave credit_grace_until set so the next tick retries the kill.
            logger.exception("Could not publish billing.exhausted for pod %s", session.id)
            await db.rollback()
            continue

        session.credit_grace_until = None
        await db.commit()
        await create_notification_safely(
            db,
            user_id=session.user_id,
            type="vm_terminated",
            severity="error",
            title="VM stopped",
            body="Your VM was stopped because you ran out of credits.",
            action_url="/credits",
            dedupe_key=f"vm-terminated-credits:{session.id}",
            metadata={"pod_id": session.id},
        )
        resolved += 1

    return resolved


async def _run_once() -> None:
    """One monitor tick, serialised across uvicorn workers by an advisory lock."""
    async with async_session() as db:
        acquired = (
            await db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
        ).scalar()
        if not acquired:
            return
        try:
            await process_expired_graces(db)
        finally:
            await db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
            await db.commit()


async def _monitor_loop() -> None:
    interval = max(5.0, settings.credit_grace_monitor_interval_seconds)
    while True:
        try:
            await _run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Credit grace monitor tick failed; retrying next interval")
        await asyncio.sleep(interval)


_task: asyncio.Task | None = None


async def start_credit_grace_monitor() -> None:
    global _task
    if not settings.credit_grace_monitor_enabled:
        logger.info("Credit grace monitor disabled")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_monitor_loop())
    logger.info(
        "Credit grace monitor started — %.0fs grace, checked every %.0fs",
        settings.credit_grace_minutes,
        settings.credit_grace_monitor_interval_seconds,
    )


async def stop_credit_grace_monitor() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
