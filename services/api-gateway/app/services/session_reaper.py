"""Terminate expired VM sessions and record the action exactly once."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import nats as nats_client
from app.core.database import async_session
from app.models.audit import AuditLog
from app.models.session import PodSession
from app.services.orchestrator_client import orchestrator_client

logger = logging.getLogger(__name__)
ACTIVE_STATES = ("pending", "creating", "running", "stopping")


async def reap_expired_sessions(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    terminate=None,
    publish=None,
) -> list[str]:
    """Terminate all expired active sessions and return their IDs.

    Rows are locked with ``SKIP LOCKED`` so multiple API workers can safely run
    the reaper. State is committed before external notifications; a repeated run
    therefore cannot terminate or audit the same session twice.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    terminate = terminate or orchestrator_client.terminate_pod

    result = await db.execute(
        select(PodSession)
        .where(
            PodSession.expires_at.is_not(None),
            PodSession.expires_at <= now,
            PodSession.state.in_(ACTIVE_STATES),
        )
        .with_for_update(skip_locked=True)
    )
    expired = list(result.scalars().all())
    reaped: list[str] = []

    for session in expired:
        try:
            await terminate(session.pod_name)
        except Exception as exc:
            # Kubernetes deletion is idempotent; a missing namespace/pod should
            # not keep an already-expired database session alive forever.
            if "not found" not in str(exc).lower() and "already deleted" not in str(exc).lower():
                logger.exception("Could not terminate expired pod %s", session.pod_name)
                continue

        session.state = "terminated"
        session.updated_at = now
        db.add(
            AuditLog(
                id=str(uuid4()),
                user_id=session.user_id,
                action="session.reaped",
                resource_type="pod_session",
                resource_id=session.id,
                ip_address="system",
                status_code=200,
                metadata_={"reason": "expired", "pod_name": session.pod_name},
            )
        )
        reaped.append(session.id)

    if reaped:
        await db.commit()
        for pod_id in reaped:
            payload = json.dumps({"pod_id": pod_id, "reason": "expired"}).encode()
            if publish is not None:
                await publish("session.reaped", payload)
            else:
                try:
                    await nats_client.get_nc().publish("session.reaped", payload)
                except RuntimeError:
                    logger.warning("NATS unavailable while publishing session.reaped for %s", pod_id)
    return reaped


async def run_session_reaper(stop: asyncio.Event, interval_seconds: int = 30) -> None:
    """Run the reaper until ``stop`` is set."""
    while not stop.is_set():
        try:
            async with async_session() as db:
                await reap_expired_sessions(db)
        except Exception:
            logger.exception("Session reaper iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
