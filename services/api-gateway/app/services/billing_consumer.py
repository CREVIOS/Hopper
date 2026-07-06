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
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core import nats as nats_client
from app.core.database import async_session
from app.models.session import PodSession
from app.services.credit_service import deduct_credits

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
        await _safe_ack(msg)
    except IntegrityError:
        # Duplicate tx_id — already applied. Safe to ack.
        logger.info("billing tx %s already applied — idempotent skip", tx_id)
        await _safe_ack(msg)
    except ValueError:
        logger.warning("Credits exhausted for user %s, pod %s", user_id, pod_id)
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
            result = await db.execute(
                select(PodSession).where(PodSession.id == pod_id)
            )
            session = result.scalar_one_or_none()
            if session and session.state not in ("terminated", "failed"):
                session.state = "terminated"
                await db.commit()
                logger.info("Pod %s terminated due to credit exhaustion", pod_id)
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
