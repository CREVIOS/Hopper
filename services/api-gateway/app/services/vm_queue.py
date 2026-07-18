"""Enqueue and inspect CPU/RAM VM admission-queue entries.

When the cluster is full a POST /pods/ request cannot be satisfied
synchronously, so instead of failing we persist the request as a 'queued'
``VmQueueEntry``. The background admission loop (app.services.vm_scheduler)
promotes queued entries FCFS as capacity frees.

This module only owns queue bookkeeping: validation, credit precheck, insert,
and position/count queries. It performs no capacity math and never calls the
orchestrator -- that is the scheduler's job.
"""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vm_queue_entry import VmQueueEntry
from app.schemas.pod import (
    DEFAULT_TEMPLATE,
    VM_TEMPLATE_IMAGES,
)
from app.schemas.user import TokenPayload
from app.services import plan_service
from app.services.credit_service import get_balance

logger = logging.getLogger(__name__)

# Entries that still occupy a slot in the queue: 'queued' waiting to be
# admitted and 'admitting' mid-flight through the orchestrator create call.
_LIVE_QUEUE_STATES = ("queued", "admitting")


class EnqueueError(Exception):
    """Raised when a VM request cannot be queued.

    Carries an HTTP status code + detail so the router can translate it into
    an HTTPException without re-deriving the failure reason. Mirrors the codes
    the synchronous create path already returns (402 for credits, 422 for a
    bad plan).
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _resolve_image(template: str) -> str:
    """Resolve a friendly template key to a container image tag.

    Identical to CreatePodRequest.resolved_image() for the template case:
    unknown templates fall back to the default ubuntu image so a queued entry
    always carries a concrete image the scheduler can hand to the orchestrator.
    """
    return VM_TEMPLATE_IMAGES.get(template, VM_TEMPLATE_IMAGES[DEFAULT_TEMPLATE])


async def enqueue_vm_request(
    db: AsyncSession, user: TokenPayload, plan: str, template: str,
    network_group: str | None = None,
) -> VmQueueEntry:
    """Validate and persist a 'queued' VM request for later admission.

    Runs the same credit precheck as the synchronous create path so a caller
    who can never afford the VM is rejected up front rather than sitting in the
    queue. The plan's resource limits are frozen onto the entry so the
    scheduler admits exactly what was requested even if plan defaults change.
    """
    plan_row = await plan_service.get_plan(db, plan, active_only=True)
    if plan_row is None:
        raise EnqueueError(422, f"Unknown VM plan: {plan}")
    credits_per_hour = float(plan_row.credits_per_hour)

    balance = await get_balance(db, user.sub)
    if balance < credits_per_hour:
        raise EnqueueError(
            402,
            f"Insufficient credits. Need {credits_per_hour}, "
            f"have {balance:.2f}",
        )

    entry = VmQueueEntry(
        id=str(uuid.uuid4()),
        user_id=user.sub,
        plan=plan,
        template=template,
        image=_resolve_image(template),
        cpu=plan_row.cpu,
        memory=plan_row.memory,
        state="queued",
        network_group=network_group,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    logger.info(
        "Queued VM request %s user=%s plan=%s seq=%s",
        entry.id, user.sub, entry.plan, entry.seq,
    )
    return entry


async def queue_position(db: AsyncSession, entry: VmQueueEntry) -> int:
    """1-based FCFS position of ``entry`` among currently 'queued' entries.

    Counts queued entries with a ``seq`` at or before this one. While the entry
    itself is still 'queued' the count includes it, so a freshly enqueued entry
    at the head returns 1.
    """
    result = await db.execute(
        select(func.count())
        .select_from(VmQueueEntry)
        .where(VmQueueEntry.state == "queued", VmQueueEntry.seq <= entry.seq)
    )
    return int(result.scalar_one())


async def live_queue_count(db: AsyncSession) -> int:
    """Number of entries still occupying the queue ('queued' + 'admitting')."""
    result = await db.execute(
        select(func.count())
        .select_from(VmQueueEntry)
        .where(VmQueueEntry.state.in_(_LIVE_QUEUE_STATES))
    )
    return int(result.scalar_one())
