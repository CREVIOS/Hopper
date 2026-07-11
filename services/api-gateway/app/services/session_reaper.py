"""Session-expiry reaper (FR-HC-27).

`pod_sessions.expires_at` is set at launch and extended via /extend, but nothing
enforced it — an expired VM kept running (and billing) until credits ran out.
This background job periodically terminates VMs whose TTL has passed.

Same shape as the audit-retention job: a lifespan-launched asyncio loop guarded
by a Postgres advisory lock so only one uvicorn worker reaps per tick.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select, text

from app.config import settings
from app.core.database import async_session
from app.models.session import PodSession
from app.services import port_forward
from app.services.orchestrator_client import orchestrator_client

logger = logging.getLogger(__name__)

_ADVISORY_LOCK_KEY = 907_314_003

# States that represent a live VM eligible for reaping once past its TTL.
_LIVE_STATES = ("pending", "creating", "running")


async def find_expired_sessions(db, now: datetime) -> list[PodSession]:
    """Return live sessions whose expires_at is in the past."""
    result = await db.execute(
        select(PodSession).where(
            PodSession.state.in_(_LIVE_STATES),
            PodSession.expires_at.is_not(None),
            PodSession.expires_at < now,
        )
    )
    return list(result.scalars().all())


async def _terminate(session: PodSession) -> None:
    try:
        await orchestrator_client.terminate_pod(session.pod_name)
    except Exception as e:
        logger.error("session reaper: terminate pod %s failed: %s", session.pod_name, e)
    try:
        await port_forward.stop(session.pod_name)
    except Exception:
        pass
    session.state = "terminated"


async def reap_expired_sessions(db, now: datetime | None = None) -> int:
    """Terminate all expired live sessions; return the count reaped.

    ``now`` is injectable for deterministic tests.
    """
    now = now or datetime.utcnow()
    expired = await find_expired_sessions(db, now)
    for session in expired:
        await _terminate(session)
    if expired:
        await db.commit()
        logger.info("Session reaper: terminated %d expired VM(s)", len(expired))
    return len(expired)


async def _run_once() -> None:
    async with async_session() as db:
        acquired = (
            await db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
        ).scalar()
        if not acquired:
            return
        try:
            await reap_expired_sessions(db)
        finally:
            await db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
            await db.commit()


async def _reaper_loop() -> None:
    interval = max(10.0, settings.session_reaper_interval_seconds)
    while True:
        try:
            await _run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Session reaper tick failed; will retry next interval")
        await asyncio.sleep(interval)


_task: asyncio.Task | None = None


async def start_session_reaper() -> None:
    global _task
    if not settings.session_reaper_enabled:
        logger.info("Session reaper disabled")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_reaper_loop())
    logger.info(
        "Session reaper started — terminating expired VMs every %.0fs",
        settings.session_reaper_interval_seconds,
    )


async def stop_session_reaper() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
