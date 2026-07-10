"""Audit-log retention housekeeping (NFR-NF-014).

Periodically deletes ``audit_logs`` rows older than a configurable window
(default 90 days). There is no general scheduler in this service, so the job is
a lightweight asyncio loop launched from the app lifespan — mirroring how the
billing/metrics consumers are started.

The purge itself is a single indexed ``DELETE`` (``audit_logs.created_at`` is
indexed by migration 005). Because the gateway runs multiple uvicorn workers, a
Postgres advisory lock ensures only one worker actually runs a given purge —
the same guard pattern used by the credit and ssh-key services.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, text

from app.config import settings
from app.core.database import async_session
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

# Arbitrary but stable 64-bit key for the session-level advisory lock. Distinct
# from any other advisory lock in the codebase so purges never contend with
# unrelated work.
_ADVISORY_LOCK_KEY = 907_314_002


async def purge_expired_audit_logs(db, retention_days: int, now: datetime | None = None) -> int:
    """Delete audit rows older than ``retention_days``; return the count removed.

    A non-positive ``retention_days`` means "retain forever": no DELETE is
    issued and 0 is returned. ``now`` is injectable so the cutoff is
    deterministic under test.
    """
    if retention_days <= 0:
        return 0

    reference = now or datetime.utcnow()
    cutoff = reference - timedelta(days=retention_days)

    result = await db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
    await db.commit()
    return result.rowcount or 0


async def _run_once() -> None:
    """Open a session, take the advisory lock, and purge once.

    If another worker already holds the lock we skip silently — it is doing the
    purge for this interval.
    """
    async with async_session() as db:
        acquired = (
            await db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
        ).scalar()
        if not acquired:
            return
        try:
            deleted = await purge_expired_audit_logs(db, settings.audit_retention_days)
            if deleted:
                logger.info(
                    "Audit retention: purged %d rows older than %d days",
                    deleted,
                    settings.audit_retention_days,
                )
        finally:
            await db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
            await db.commit()


async def _retention_loop() -> None:
    interval = max(60.0, settings.audit_retention_interval_hours * 3600.0)
    while True:
        try:
            await _run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Audit retention purge failed; will retry next interval")
        await asyncio.sleep(interval)


_task: asyncio.Task | None = None


async def start_audit_retention() -> None:
    """Launch the retention loop as a background task. No-op if disabled."""
    global _task
    if settings.audit_retention_days <= 0:
        logger.info("Audit retention disabled (audit_retention_days <= 0)")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_retention_loop())
    logger.info(
        "Audit retention started — purging rows older than %d days every %.1fh",
        settings.audit_retention_days,
        settings.audit_retention_interval_hours,
    )


async def stop_audit_retention() -> None:
    """Cancel the background task during shutdown."""
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
