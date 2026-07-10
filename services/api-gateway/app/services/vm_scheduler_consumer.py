"""NATS consumer that nudges the VM admission scheduler when a pod stops.

The orchestrator publishes ``pod.stopped`` (core NATS, fire-and-forget) from
every path that frees cluster capacity: a normal terminate, the k8s watcher
observing a failed/deleted pod, and credit exhaustion. Any such message means
capacity may have freed, so we wake the admission loop immediately instead of
waiting for the next periodic tick.

No queue group: every worker receives the message and nudges its *local* loop.
Only the leader's loop actually admits; the others are cheap no-ops. This
guarantees the nudge reaches whichever worker currently holds leadership -- a
queue group would deliver to one arbitrary worker that is usually not the
leader, so the nudge would be wasted. Core NATS has no persistence, so the
periodic ``HOPPER_SCHEDULER_TICK_SECONDS`` tick remains the required backstop
for any nudge fired while no subscriber is up.
"""

import logging

from nats.aio.client import Client as NatsClient
from nats.aio.subscription import Subscription
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.vm_scheduler import nudge

logger = logging.getLogger(__name__)

# The orchestrator's real pod-stopped subject
# (services/orchestrator/internal/events/nats.go: SubjectPodStopped).
_SUBJECT = "pod.stopped"

_subscription: Subscription | None = None


async def _on_pod_stopped(msg) -> None:
    # The body is intentionally ignored: any pod.stopped is just a wake-up. The
    # loop re-reads DB state, so the message id (an orchestrator pod name, not a
    # gateway UUID) is irrelevant here.
    nudge()


async def start(
    nc: NatsClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Subscribe to pod.stopped and nudge the local scheduler on each message."""
    global _subscription
    _subscription = await nc.subscribe(_SUBJECT, cb=_on_pod_stopped)
    logger.info("VM scheduler nudge consumer started — subscribed to %s", _SUBJECT)


async def stop() -> None:
    """Unsubscribe from pod.stopped. Safe to call if never started."""
    global _subscription
    if _subscription is not None:
        try:
            await _subscription.unsubscribe()
        except Exception:
            logger.debug("pod.stopped unsubscribe failed", exc_info=True)
        _subscription = None
