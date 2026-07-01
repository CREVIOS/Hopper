import asyncio
import json
import logging
from contextlib import suppress
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import nats as nats_client
from app.core.database import async_session
from app.models.session import PodSession
from app.schemas.pod import VM_PLAN_RESOURCES
from app.services.credit_service import get_balance
from app.services.notification_service import create_notification_safely

logger = logging.getLogger(__name__)

LOW_CREDIT_THRESHOLDS_MINUTES = (60, 30, 10, 5)
GRACE_PERIOD = timedelta(minutes=5)
ACTIVE_STATES = ("pending", "creating", "running")


def hourly_rate_for_plan(plan: str) -> float:
    for vm_plan, resources in VM_PLAN_RESOURCES.items():
        if vm_plan.value == plan:
            return float(resources["credits_per_hour"])
    return 0.0


def warning_threshold_for_minutes(minutes_remaining: float) -> int | None:
    if minutes_remaining <= 0:
        return None
    bands = [(30, 60), (10, 30), (5, 10), (0, 5)]
    thresholds = [60, 30, 10, 5]
    for (lower, upper), threshold in zip(bands, thresholds, strict=True):
        if lower < minutes_remaining <= upper:
            return threshold
    return None


async def user_hourly_burn_rate(db: AsyncSession, user_id: str) -> float:
    plans = (
        await db.scalars(
            select(PodSession.plan).where(
                PodSession.user_id == user_id,
                PodSession.state.in_(ACTIVE_STATES),
            )
        )
    ).all()
    return sum(hourly_rate_for_plan(plan) for plan in plans)


async def get_billing_session(db: AsyncSession, pod_id: str) -> PodSession | None:
    return await db.scalar(
        select(PodSession).where(
            or_(PodSession.id == pod_id, PodSession.pod_name == pod_id)
        )
    )


async def maybe_create_credit_warning(
    db: AsyncSession,
    *,
    session: PodSession,
    balance: float,
) -> None:
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
        body=f"About {approx} minutes of VM time remaining. Save your work.",
        action_url="/credits",
        dedupe_key=f"credit-warning:{session.id}:{threshold}",
        metadata={
            "pod_id": session.id,
            "minutes_remaining": minutes_remaining,
            "threshold_minutes": threshold,
        },
    )


async def publish_billing_exhausted(pod_id: str, user_id: str) -> None:
    nc = nats_client.get_nc()
    await nc.publish(
        "billing.exhausted",
        json.dumps({"pod_id": pod_id, "user_id": user_id}).encode(),
    )


async def start_credit_grace(
    db: AsyncSession,
    *,
    session: PodSession,
    now: datetime | None = None,
) -> None:
    now = now or datetime.utcnow()
    if session.expires_at is None:
        session.expires_at = now + GRACE_PERIOD
        await db.commit()
        await db.refresh(session)

    await create_notification_safely(
        db,
        user_id=session.user_id,
        type="credit_grace",
        severity="error",
        title="Credits exhausted",
        body="Your VM will stop in 5 minutes unless credits are added.",
        action_url="/credits",
        dedupe_key=f"credit-grace:{session.id}:{session.expires_at.isoformat()}",
        metadata={
            "pod_id": session.id,
            "expires_at": session.expires_at.isoformat(),
        },
    )


async def process_expired_credit_graces(now: datetime | None = None) -> int:
    now = now or datetime.utcnow()
    processed = 0
    async with async_session() as db:
        sessions = (
            await db.scalars(
                select(PodSession).where(
                    PodSession.expires_at.is_not(None),
                    PodSession.expires_at <= now,
                    PodSession.state.in_(ACTIVE_STATES),
                )
            )
        ).all()

        for session in sessions:
            balance = await get_balance(db, session.user_id)
            minimum_next_tick = hourly_rate_for_plan(session.plan) / 60.0
            if balance >= minimum_next_tick and minimum_next_tick > 0:
                session.expires_at = None
                await db.commit()
                processed += 1
                continue

            try:
                await publish_billing_exhausted(session.pod_name or session.id, session.user_id)
            except Exception:
                logger.exception("Failed to publish billing.exhausted for pod %s", session.id)
                await db.rollback()
                continue

            session.expires_at = None
            await db.commit()
            processed += 1

    return processed


async def run_credit_grace_monitor(interval_seconds: int = 15) -> None:
    while True:
        try:
            await process_expired_credit_graces()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Credit grace monitor failed")
        await asyncio.sleep(interval_seconds)


async def stop_credit_grace_monitor(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
