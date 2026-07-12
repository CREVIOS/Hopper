"""NATS consumer for billing events from the orchestrator.

Subscribes to:
  - billing.deducted  → deduct credits from the user's ledger
  - billing.exhausted → mark the pod as terminated in the DB

Publishes:
  - billing.exhausted → when a deduction fails due to insufficient credits

Idempotency: each message carries a `tx_id` (orchestrator-supplied,
deterministic per (pod_id, tick_seq)). The credit_service writes a row
keyed on tx_id with a UNIQUE constraint, so a redelivery is a noop.

Error handling:
  - ValueError: insufficient credits → publish billing.exhausted, ACK message
  - sqlalchemy OperationalError / asyncpg transient: NAK so JetStream redelivers
  - Any other: log + ACK (don't redeliver garbage forever)
"""

import json
import logging

from nats.errors import NotJSMessageError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import settings
from app.core import nats as nats_client
from app.core.database import async_session
from app.models.session import PodSession
from app.services import credit_alerts
from app.services.credit_service import deduct_credits, get_balance
from app.services.notification_service import create_notification_safely

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
            await deduct_credits(
                db, user_id, amount,
                description=f"vm_usage:{pod_id}",
                tx_id=tx_id,
            )
            logger.debug(
                "Deducted %.4f credits user=%s pod=%s tx=%s",
                amount, user_id, pod_id, tx_id,
            )
            # Warn the user before the lights go out (FR-HC-18). Best-effort:
            # a failed notification must never fail the billing tick itself.
            try:
                session = await credit_alerts.get_billing_session(db, pod_id)
                if session is not None:
                    balance = await get_balance(db, user_id)
                    # They paid this tick, so any earlier grace window is over.
                    if session.credit_grace_until is not None:
                        session.credit_grace_until = None
                        await db.commit()
                    await credit_alerts.maybe_warn_low_credits(
                        db, session=session, balance=balance
                    )
            except Exception:
                logger.exception("Low-credit warning failed for pod %s", pod_id)
        await _safe_ack(msg)
    except IntegrityError:
        # Duplicate tx_id — already applied. Safe to ack.
        logger.info("billing tx %s already applied — idempotent skip", tx_id)
        await _safe_ack(msg)
    except ValueError:
        # Out of credits. Rather than killing the VM on the spot, open a grace
        # window and tell the user; credit_alerts' monitor terminates it only if
        # they haven't topped up by the deadline. With credit_grace_minutes = 0
        # we fall back to the original terminate-immediately behaviour.
        logger.warning("Credits exhausted for user %s, pod %s", user_id, pod_id)
        try:
            async with async_session() as db:
                session = await credit_alerts.get_billing_session(db, pod_id)
                if session is not None and settings.credit_grace_minutes > 0:
                    await credit_alerts.start_credit_grace(db, session=session)
                    await _safe_ack(msg)
                    return
        except Exception:
            # If grace can't be started we must still stop the VM, or it would
            # keep running for free.
            logger.exception("Could not start credit grace for pod %s — terminating", pod_id)

        nc = nats_client.get_nc()
        await nc.publish(
            "billing.exhausted",
            json.dumps({"pod_id": pod_id, "user_id": user_id}).encode(),
        )
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
            # The orchestrator's billing event carries whatever id the in-memory
            # pod manager holds: the API UUID for reconciled pods, but the K8s
            # name ("vm-<unixNano>") for freshly-created pods that haven't been
            # through a reconcile yet. Match on either so a credit-exhausted VM
            # is reliably flipped to `terminated` in both cases (previously the
            # id-only lookup missed fresh pods, leaving the row stuck "running").
            result = await db.execute(
                select(PodSession).where(
                    or_(PodSession.id == pod_id, PodSession.pod_name == pod_id)
                )
            )
            session = result.scalars().first()
            # "stopped" is excluded deliberately: a stopped VM has no pod and is
            # not billing, so a late/in-flight exhausted message must not flip it
            # to terminated and rob the user of the resume they still have.
            if session and session.state not in ("terminated", "failed", "stopped"):
                session.state = "terminated"
                session.credit_grace_until = None
                await db.commit()
                logger.info("Pod %s terminated due to credit exhaustion", pod_id)

                # Tell the user why their VM vanished. Deduped per pod, so the
                # grace monitor and this handler can't both notify twice.
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
