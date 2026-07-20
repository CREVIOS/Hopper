"""Idle auto-shutdown: stop VMs nobody is using, but warn first.

A VM that sits idle keeps billing its owner. This job finds those VMs and shuts
them down — but never silently, because our only activity signal is CPU, and CPU
is a *lossy* proxy for "someone is using this". A student reading code in VS Code
or thinking at a terminal prompt looks identical to an abandoned VM.

So the flow is warn, then wait, then kill:

    CPU below threshold for idle_window_minutes
        -> notify the user, stamp idle_shutdown_at = now + idle_grace_minutes
    activity resumes before the deadline
        -> clear the stamp, VM lives (and can be warned again later)
    still idle at the deadline
        -> terminate, and say why

``idle_shutdown_at`` doubles as the "already warned" flag: null means we are not
counting down on this VM, so a warning fires once per idle episode rather than
once per tick.

Deliberately its own column, like grace_expires_at — ``expires_at`` is the
session TTL that the session reaper enforces, and overloading it would make the
reaper kill VMs for the wrong reason.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import async_session
from app.models.metrics import MetricsSample
from app.models.session import PodSession
from app.services import port_forward
from app.services.notification_service import create_notification_safely
from app.services.orchestrator_client import orchestrator_client

logger = logging.getLogger(__name__)

_ADVISORY_LOCK_KEY = 907_314_005  # distinct from the reaper / credit monitor

# States representing a live VM that could be idle.
LIVE_STATES = ("pending", "creating", "running")


async def peak_cpu_since(db: AsyncSession, session: PodSession, since: datetime) -> float | None:
    """Highest CPU% this pod reported since ``since``, or None if it reported nothing.

    None is meaningfully different from 0.0: no samples means we have no idea what
    the VM is doing (a dead metrics pipeline looks exactly like an idle VM), and
    we must not terminate on ignorance. Callers treat None as "not idle".

    metrics_samples is keyed by the K8s pod name for fresh pods and by the session
    UUID once reconciled, so match on both.
    """
    peak = await db.scalar(
        select(func.max(MetricsSample.cpu_percent)).where(
            or_(
                MetricsSample.pod_id == session.id,
                MetricsSample.pod_id == session.pod_name,
            ),
            MetricsSample.time >= since,
        )
    )
    return None if peak is None else float(peak)


async def is_idle(db: AsyncSession, session: PodSession, now: datetime) -> bool:
    """Has this VM been below the CPU threshold for the whole idle window?"""
    window_start = now - timedelta(minutes=settings.idle_window_minutes)

    # Don't judge a VM that hasn't been up long enough to have a full window of
    # evidence — a freshly booted VM is often quiet before the user connects.
    if session.started_at is not None and session.started_at > window_start:
        return False

    peak = await peak_cpu_since(db, session, window_start)
    if peak is None:
        return False  # no telemetry — never kill on missing data

    return peak < settings.idle_cpu_percent


async def _terminate(session: PodSession) -> None:
    """Tear the VM down. Mirrors the session reaper so behaviour stays consistent."""
    try:
        await orchestrator_client.terminate_pod(session.pod_name)
    except Exception as e:
        logger.error("idle monitor: terminate pod %s failed: %s", session.pod_name, e)
        raise
    try:
        await port_forward.stop(session.pod_name)
    except Exception:
        pass
    session.state = "terminated"


async def _warn(db: AsyncSession, session: PodSession, now: datetime) -> None:
    """Start the countdown and tell the user, so they can rescue the VM."""
    session.idle_shutdown_at = now + timedelta(minutes=settings.idle_grace_minutes)
    await db.commit()

    minutes = int(settings.idle_grace_minutes)
    await create_notification_safely(
        db,
        user_id=session.user_id,
        type="vm_idle",
        severity="warning",
        title="VM looks idle",
        body=f"Your VM has been idle and stops in {minutes} minutes. "
             "Use it to keep it running.",
        action_url=f"/pods/{session.id}",
        # One warning per idle episode: the stamp is cleared when activity
        # resumes, so a later idle spell warns again under a new deadline.
        dedupe_key=f"vm-idle:{session.id}:{session.idle_shutdown_at.isoformat()}",
        metadata={
            "pod_id": session.id,
            "shutdown_at": session.idle_shutdown_at.isoformat(),
        },
    )


async def _shutdown(db: AsyncSession, session: PodSession) -> None:
    await _terminate(session)
    session.idle_shutdown_at = None
    await db.commit()

    await create_notification_safely(
        db,
        user_id=session.user_id,
        type="vm_terminated",
        severity="error",
        title="Idle VM stopped",
        body="Your VM was stopped because it was idle. Any unsaved work outside "
             "/workspace is gone; /workspace is preserved.",
        action_url="/pods",
        dedupe_key=f"vm-terminated-idle:{session.id}",
        metadata={"pod_id": session.id},
    )


async def _reprieve(db: AsyncSession, session: PodSession) -> None:
    """Activity came back before the deadline — call the whole thing off."""
    session.idle_shutdown_at = None
    await db.commit()
    logger.info("idle monitor: pod %s became active again — shutdown cancelled", session.id)


async def process_idle_sessions(db: AsyncSession, now: datetime | None = None) -> dict:
    """One pass over every live VM. Returns counts of what happened.

    ``now`` is injectable so tests don't have to sleep.
    """
    now = now or datetime.utcnow()
    sessions = (
        await db.scalars(select(PodSession).where(PodSession.state.in_(LIVE_STATES)))
    ).all()

    warned = shutdown = reprieved = 0

    for session in sessions:
        try:
            idle = await is_idle(db, session, now)

            if session.idle_shutdown_at is None:
                if idle:
                    await _warn(db, session, now)
                    warned += 1
                continue

            # Already counting down on this one.
            if not idle:
                await _reprieve(db, session)
                reprieved += 1
            elif now >= session.idle_shutdown_at:
                await _shutdown(db, session)
                shutdown += 1
        except Exception:
            # One bad pod must not stop the rest of the sweep. Leaving
            # idle_shutdown_at as-is means a failed kill is retried next tick.
            logger.exception("idle monitor: failed to process pod %s", session.id)
            await db.rollback()

    if warned or shutdown or reprieved:
        logger.info(
            "Idle monitor: warned=%d shutdown=%d reprieved=%d",
            warned, shutdown, reprieved,
        )
    return {"warned": warned, "shutdown": shutdown, "reprieved": reprieved}


async def _run_once() -> None:
    """One tick, serialised across uvicorn workers by an advisory lock."""
    async with async_session() as db:
        acquired = (
            await db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
        ).scalar()
        if not acquired:
            return
        try:
            await process_idle_sessions(db)
        finally:
            await db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
            await db.commit()


async def _monitor_loop() -> None:
    interval = max(15.0, settings.idle_monitor_interval_seconds)
    while True:
        try:
            await _run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Idle monitor tick failed; retrying next interval")
        await asyncio.sleep(interval)


_task: asyncio.Task | None = None


async def start_idle_monitor() -> None:
    global _task
    if not settings.idle_shutdown_enabled:
        logger.info("Idle auto-shutdown disabled")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_monitor_loop())
    logger.info(
        "Idle monitor started — CPU < %.1f%% for %.0fm warns, shutdown %.0fm later",
        settings.idle_cpu_percent,
        settings.idle_window_minutes,
        settings.idle_grace_minutes,
    )


async def stop_idle_monitor() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
