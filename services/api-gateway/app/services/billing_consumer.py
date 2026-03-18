"""NATS consumer for billing events from the orchestrator.

Subscribes to:
  - billing.deducted  → deduct credits from the user's ledger
  - billing.exhausted → mark the pod as terminated in the DB

Publishes:
  - billing.exhausted → when a deduction fails due to insufficient credits
"""

import json
import logging

from app.core import nats as nats_client
from app.core.database import async_session
from app.services.credit_service import deduct_credits
from app.models.session import PodSession

from sqlalchemy import select

logger = logging.getLogger(__name__)


async def _handle_billing_deducted(msg):
    """Process a billing tick: deduct credits from the user's account."""
    try:
        data = json.loads(msg.data)
        pod_id = data["pod_id"]
        amount = float(data["amount"])
        user_id = data["user_id"]
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Malformed billing.deducted message: %s", e)
        return

    try:
        async with async_session() as db:
            await deduct_credits(
                db, user_id, amount,
                description=f"vm_usage:{pod_id}",
            )
            logger.debug("Deducted %.4f credits from user %s for pod %s", amount, user_id, pod_id)
    except ValueError:
        # Insufficient credits — tell orchestrator to kill the pod
        logger.warning("Credits exhausted for user %s, pod %s", user_id, pod_id)
        nc = nats_client.get_nc()
        await nc.publish(
            "billing.exhausted",
            json.dumps({"pod_id": pod_id, "user_id": user_id}).encode(),
        )
    except Exception:
        logger.exception("Failed to deduct credits for pod %s", pod_id)


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
    """Subscribe to billing events. Call once during app startup."""
    nc = nats_client.get_nc()
    await nc.subscribe("billing.deducted", cb=_handle_billing_deducted)
    await nc.subscribe("billing.exhausted", cb=_handle_billing_exhausted)
    logger.info("Billing consumer started — subscribed to billing.deducted, billing.exhausted")
