"""User notifications: persistence, real-time fan-out, and NATS consumers.

Two halves:

1. ``notify()`` writes a Notification row (rolling window of 100 per user)
   and publishes it on NATS subject ``notify.user.<user_id>``. The SSE
   endpoint in the notifications router subscribes to that subject, so the
   push reaches every gateway worker/replica regardless of which one holds
   the browser's EventSource connection.

2. ``start_notification_consumer()`` subscribes (queue-grouped, so exactly
   one worker handles each event) to the orchestrator's pod lifecycle
   subjects and turns them into notifications:
     - pod.started → "VM is ready" (published by the K8s watcher when the
       pod actually reaches Running — not when the API accepted it)
     - pod.stopped → "VM terminated" for terminations the user did NOT
       initiate (user-initiated deletes already set the DB row to
       terminated synchronously, which dedupes them here)
     - pod.failed  → "VM failed to create"

Event pod references are messy for historical reasons: the orchestrator
keys fresh pods by its internal ``vm-<unixnano>`` name but the watcher
publishes the API UUID from the pod label, and events may carry either.
``resolve_session()`` accepts both.
"""

import json
import logging
import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import nats as nats_client
from app.core.database import async_session
from app.models.notification import Notification
from app.models.session import PodSession

logger = logging.getLogger(__name__)

# Rolling window of notifications kept per user.
MAX_PER_USER = 100


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "user_id": n.user_id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "data": n.data,
        "read": n.read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


async def notify(
    db: AsyncSession,
    user_id: str,
    *,
    type_: str = "info",
    title: str,
    body: str = "",
    data: dict | None = None,
    commit: bool = True,
) -> Notification:
    """Persist a notification and push it to the user's live SSE streams.

    Commits by default; pass commit=False to join a caller's transaction
    (the NATS push still happens immediately — it is fire-and-forget and
    must never fail the caller).
    """
    row = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        type=type_,
        title=title,
        body=body,
        data=data,
    )
    db.add(row)
    await db.flush()

    # Cap the per-user window. Runs on every insert — cheap at this scale
    # thanks to ix_notifications_user_created.
    keep = (
        select(Notification.id)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(MAX_PER_USER)
    )
    await db.execute(
        delete(Notification).where(
            Notification.user_id == user_id,
            Notification.id.not_in(keep),
        )
    )

    if commit:
        await db.commit()

    payload = _serialize(row)
    try:
        nc = nats_client.get_nc()
        await nc.publish(f"notify.user.{user_id}", json.dumps(payload).encode())
    except Exception:
        # A dropped live push is fine — the row is persisted and the bell
        # will show it on the next poll/page load.
        logger.warning("live notification push failed for user %s", user_id)

    return row


async def resolve_session(db: AsyncSession, pod_ref: str) -> PodSession | None:
    """Find a PodSession by either its API UUID or its K8s pod name.

    Orchestrator events carry whichever identifier the publishing code path
    had on hand (see module docstring), so match both columns.
    """
    result = await db.execute(
        select(PodSession).where(
            or_(PodSession.id == pod_ref, PodSession.pod_name == pod_ref)
        )
    )
    return result.scalars().first()


# ---------------------------------------------------------------------------
# NATS consumers: orchestrator lifecycle events → notifications
# ---------------------------------------------------------------------------


async def _handle_pod_started(msg) -> None:
    try:
        data = json.loads(msg.data)
        pod_ref = data["pod_id"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error("Malformed pod.started message: %s", e)
        return

    try:
        async with async_session() as db:
            session = await resolve_session(db, pod_ref)
            if session is None:
                logger.warning("pod.started for unknown pod %s", pod_ref)
                return
            # The DB is usually already "running" here — create_pod records
            # the orchestrator's optimistic state long before the container
            # actually starts. The watcher publishes pod.started exactly once
            # per observed Pending→Running phase transition, so notify
            # unconditionally and just repair a stale non-terminal state.
            if session.state in ("terminated", "failed"):
                return  # raced a termination — don't resurrect
            if session.state in ("pending", "creating"):
                session.state = "running"
            await notify(
                db,
                session.user_id,
                type_="success",
                title="VM is ready",
                body=f"Your {session.plan} VM is up — open VS Code or the terminal to start working.",
                data={"pod_id": session.id, "action": "open_vscode"},
                commit=False,
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to handle pod.started for %s", pod_ref)


_STOP_REASONS = {
    "credits_exhausted": (
        "warning",
        "VM terminated — credits exhausted",
        "Your VM was shut down because your credits ran out. Top up to launch a new one.",
    ),
    "deleted": (
        "info",
        "VM terminated",
        "Your VM was shut down by the platform.",
    ),
}


async def _handle_pod_stopped(msg) -> None:
    try:
        data = json.loads(msg.data)
        pod_ref = data["pod_id"]
        reason = data.get("reason", "")
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error("Malformed pod.stopped message: %s", e)
        return

    try:
        async with async_session() as db:
            session = await resolve_session(db, pod_ref)
            if session is None:
                return
            # Already terminal in the DB ⇒ either the user clicked Terminate
            # (the DELETE endpoint commits state=terminated before this event
            # lands) or a duplicate event — no notification either way.
            if session.state in ("terminated", "failed"):
                return
            session.state = "terminated"
            type_, title, body = _STOP_REASONS.get(
                reason,
                (
                    "warning",
                    "VM terminated",
                    "Your VM stopped unexpectedly. You can launch a new one from the dashboard.",
                ),
            )
            await notify(
                db,
                session.user_id,
                type_=type_,
                title=title,
                body=body,
                data={"pod_id": session.id, "reason": reason},
                commit=False,
            )
            await db.commit()
            logger.info("pod %s marked terminated (reason=%s)", session.id, reason or "n/a")
    except Exception:
        logger.exception("Failed to handle pod.stopped for %s", pod_ref)


async def _handle_pod_failed(msg) -> None:
    try:
        data = json.loads(msg.data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("Malformed pod.failed message: %s", e)
        return
    # CreatePod failures publish api_pod_id (the session UUID); older events
    # only had the orchestrator's internal name, which resolve_session can't
    # always match.
    pod_ref = data.get("api_pod_id") or data.get("pod_id", "")

    # State repair only, no notification: pod.failed is published exactly when
    # the gateway's create_pod call fails synchronously, and THAT path owns the
    # "VM failed to create" notification (a second one here would race it and
    # double-notify). This consumer just makes sure the DB row lands on
    # "failed" even if the request worker died mid-flight.
    try:
        async with async_session() as db:
            session = await resolve_session(db, pod_ref) if pod_ref else None
            if session is None or session.state in ("failed", "terminated"):
                return
            session.state = "failed"
            await db.commit()
            logger.info("pod %s marked failed from pod.failed event", session.id)
    except Exception:
        logger.exception("Failed to handle pod.failed for %s", pod_ref)


async def start_notification_consumer() -> None:
    """Subscribe to pod lifecycle events. Call once during app startup.

    Queue group: exactly one uvicorn worker (across all gateway replicas)
    turns a given event into a DB row — the same pattern as the billing and
    metrics consumers. The resulting live push goes out on notify.user.*,
    which every worker's SSE streams subscribe to individually.
    """
    nc = nats_client.get_nc()
    await nc.subscribe("pod.started", queue="notify-workers", cb=_handle_pod_started)
    await nc.subscribe("pod.stopped", queue="notify-workers", cb=_handle_pod_stopped)
    await nc.subscribe("pod.failed", queue="notify-workers", cb=_handle_pod_failed)
    logger.info(
        "Notification consumer started — pod.started, pod.stopped, pod.failed (queue=notify-workers)"
    )
