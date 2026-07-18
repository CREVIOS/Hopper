"""NATS consumer for billing events from the orchestrator.

Subscribes to:
  - billing.deducted  → deduct credits from the user's ledger; emit low-credit
    warnings as the balance crosses configured thresholds
  - billing.exhausted → mark the pod as terminated in the DB

Publishes:
  - billing.warning   → when the projected runtime remaining crosses a
    configured threshold (also pushed to the user as a notification)
  - billing.exhausted → when a deduction fails due to insufficient credits
    AND the grace period has expired. The first failed tick starts a grace
    countdown (default 5 min) and warns the user instead of killing the VM
    instantly; the deadline is cleared if a later tick succeeds (top-up).

Idempotency: each message carries a `tx_id` (orchestrator-supplied,
deterministic per (pod_id, tick_seq)). The credit_service writes a row
keyed on tx_id with a UNIQUE constraint, so a redelivery is a noop.

Error handling:
  - ValueError: insufficient credits → grace period logic (see above), ACK
  - sqlalchemy OperationalError / asyncpg transient: NAK so JetStream redelivers
  - Any other: log + ACK (don't redeliver garbage forever)
"""

import json
import logging
from datetime import datetime, timedelta

from nats.errors import NotJSMessageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import settings
from app.core import nats as nats_client
from app.core.database import async_session
from app.models.session import PodSession
from app.schemas.pod import VM_PLAN_RESOURCES, VmPlan
from app.services.credit_service import deduct_credits
from app.services.notification_service import notify, resolve_session

logger = logging.getLogger(__name__)


async def _safe_ack(msg) -> None:
    """Core NATS subscriptions are not JetStream — ack() raises NotJSMessageError."""
    try:
        await msg.ack()
    except NotJSMessageError:
        pass


async def _safe_nak(msg, *, delay: int = 0) -> None:
    try:
        await msg.nak(delay=delay)
    except NotJSMessageError:
        logger.warning(
            "Cannot NAK non-JetStream billing message — DB retry will not redeliver"
        )


async def _burn_per_minute(db, user_id: str) -> float:
    """Credits/minute the user is currently burning across running VMs."""
    result = await db.execute(
        select(PodSession.plan).where(
            PodSession.user_id == user_id,
            PodSession.state == "running",
        )
    )
    total_per_hour = 0.0
    for (plan,) in result.all():
        try:
            total_per_hour += VM_PLAN_RESOURCES[VmPlan(plan)]["credits_per_hour"]
        except (KeyError, ValueError):
            logger.warning("unknown plan %r while computing burn rate", plan)
    return total_per_hour / 60.0


async def _maybe_warn_low_credits(db, user_id: str, pod_id: str, transfer) -> None:
    """Emit a low-credit warning when the balance crosses a threshold.

    Thresholds are expressed as minutes of runtime remaining at the current
    burn rate. Because the balance decreases monotonically between top-ups
    and the deduction path serialises ledger writes per account (advisory
    lock), exactly one tick observes each crossing — no dedup table needed.
    A top-up raises the projected runtime again, which re-arms thresholds
    naturally.
    """
    prev_balance = getattr(transfer, "previous_user_balance", None)
    new_balance = getattr(transfer, "new_user_balance", None)
    if prev_balance is None or new_balance is None:
        return  # idempotent replay — the original tick already warned

    burn = await _burn_per_minute(db, user_id)
    if burn <= 0:
        return
    prev_minutes = prev_balance / burn
    new_minutes = new_balance / burn

    # Find the largest threshold this tick crossed (skip any it was already
    # below — e.g. a freshly-launched VM starting under 30 min shouldn't fire
    # the 60-min warning).
    crossed = None
    for threshold in sorted(settings.credit_warning_minutes, reverse=True):
        if new_minutes <= threshold < prev_minutes:
            crossed = threshold
            break
    if crossed is None:
        return

    remaining = max(int(new_minutes), 0)
    logger.info(
        "low-credit warning user=%s: ~%d min remaining (threshold %d)",
        user_id, remaining, crossed,
    )
    try:
        nc = nats_client.get_nc()
        await nc.publish(
            "billing.warning",
            json.dumps({
                "user_id": user_id,
                "pod_id": pod_id,
                "threshold_minutes": crossed,
                "minutes_remaining": remaining,
                "balance": new_balance,
            }).encode(),
        )
    except Exception:
        logger.warning("failed to publish billing.warning for user %s", user_id)
    await notify(
        db,
        user_id,
        type_="warning",
        title="Low credits",
        body=f"About {remaining} minutes of runtime remaining at your current usage. "
             "Save your work or top up your credits.",
        data={"minutes_remaining": remaining, "threshold": crossed},
    )


async def _handle_exhausted_tick(pod_id: str, user_id: str) -> None:
    """A billing tick failed for lack of credits: run the grace-period logic.

    First failed tick stamps grace_expires_at and warns the user. Subsequent
    ticks are no-ops until the deadline passes, then billing.exhausted is
    published (orchestrator kills the pod, _handle_billing_exhausted marks
    the DB row). A successful deduction in between clears the deadline.
    """
    async with async_session() as db:
        session = await resolve_session(db, pod_id)
        if session is None or session.state in ("terminated", "failed"):
            return

        now = datetime.utcnow()
        if session.grace_expires_at is None:
            grace = timedelta(minutes=settings.credit_grace_minutes)
            session.grace_expires_at = now + grace
            await notify(
                db,
                user_id,
                type_="warning",
                title="Credits exhausted — VM stopping soon",
                body=f"Your credits have run out. Your VM will shut down in about "
                     f"{settings.credit_grace_minutes} minutes — save your work now. "
                     "Topping up credits will keep it running.",
                data={"pod_id": session.id, "grace_minutes": settings.credit_grace_minutes},
                commit=False,
            )
            await db.commit()
            logger.warning(
                "grace period started for pod %s (user %s), terminates after %s",
                session.id, user_id, session.grace_expires_at,
            )
            return

        if now < session.grace_expires_at:
            return  # still in grace — skip this tick

        logger.warning("grace expired for pod %s (user %s) — terminating", session.id, user_id)
        nc = nats_client.get_nc()
        await nc.publish(
            "billing.exhausted",
            json.dumps({"pod_id": pod_id, "user_id": user_id}).encode(),
        )


async def _handle_billing_deducted(msg):
    """Process a billing tick: deduct credits idempotently from the ledger."""
    try:
        data = json.loads(msg.data)
        pod_id = data["pod_id"]
        amount = float(data["amount"])
        user_id = data["user_id"]
        tx_id = data.get("tx_id")  # required for idempotency
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error("Malformed billing.deducted message: %s", e)
        # Bad message — ack so it doesn't redeliver forever.
        await _safe_ack(msg)
        return

    if not tx_id:
        logger.warning("billing.deducted without tx_id pod=%s — accepting (legacy)", pod_id)

    try:
        async with async_session() as db:
            transfer = await deduct_credits(
                db, user_id, amount,
                description=f"vm_usage:{pod_id}",
                tx_id=tx_id,
            )
            logger.debug(
                "Deducted %.4f credits user=%s pod=%s tx=%s",
                amount, user_id, pod_id, tx_id,
            )
            # Successful tick ⇒ the user has credits again — clear any
            # pending grace deadline so a top-up rescues the VM.
            session = await resolve_session(db, pod_id)
            if session is not None and session.grace_expires_at is not None:
                session.grace_expires_at = None
                await db.commit()
                logger.info("grace period cleared for pod %s (top-up)", session.id)
            await _maybe_warn_low_credits(db, user_id, pod_id, transfer)
        await _safe_ack(msg)
    except IntegrityError:
        # Duplicate tx_id — already applied. Safe to ack.
        logger.info("billing tx %s already applied — idempotent skip", tx_id)
        await _safe_ack(msg)
    except ValueError:
        try:
            await _handle_exhausted_tick(pod_id, user_id)
        except Exception:
            logger.exception("grace-period handling failed for pod %s", pod_id)
        await _safe_ack(msg)
    except OperationalError:
        # Transient DB blip — let JetStream redeliver after backoff.
        logger.exception("Transient DB error on billing tick pod=%s — NAK", pod_id)
        await _safe_nak(msg, delay=10)
    except Exception:
        # Unknown failure — log loudly and ack so the queue doesn't pile up.
        logger.exception("Failed to deduct credits for pod %s — ack and skip", pod_id)
        await _safe_ack(msg)


async def _handle_billing_exhausted(msg):
    """When credits run out, mark the pod as terminated in the DB."""
    try:
        data = json.loads(msg.data)
        pod_id = data["pod_id"]
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Malformed billing.exhausted message: %s", e)
        return

    try:
        async with async_session() as db:
            # resolve_session matches both the API UUID and the K8s pod name —
            # billing events may carry either depending on whether the
            # orchestrator restarted since the pod was created.
            session = await resolve_session(db, pod_id)
            if session and session.state not in ("terminated", "failed"):
                session.state = "terminated"
                await notify(
                    db,
                    session.user_id,
                    type_="warning",
                    title="VM terminated — credits exhausted",
                    body="Your VM was shut down because your credits ran out. "
                         "Top up to launch a new one.",
                    data={"pod_id": session.id, "reason": "credits_exhausted"},
                    commit=False,
                )
                await db.commit()
                logger.info("Pod %s terminated due to credit exhaustion", session.id)
    except Exception:
        logger.exception("Failed to handle billing.exhausted for pod %s", pod_id)


async def start_billing_consumer():
    """Subscribe to billing events. Call once during app startup.

    Both subscriptions use a NATS *queue group* so that only one of the
    uvicorn workers (we run with --workers=4) processes a given message.
    Without the queue group every worker handles every message, which is
    why users saw 4 identical debit rows per minute on the credits page.
    """
    nc = nats_client.get_nc()
    await nc.subscribe(
        "billing.deducted", queue="billing-workers", cb=_handle_billing_deducted
    )
    await nc.subscribe(
        "billing.exhausted", queue="billing-workers", cb=_handle_billing_exhausted
    )
    logger.info("Billing consumer started — billing.deducted, billing.exhausted (queue=billing-workers)")
