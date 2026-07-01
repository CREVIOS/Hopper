"""NATS client for the API gateway.

Provides pub/sub connectivity used by the billing consumer and metrics streaming.
Billing subjects are backed by JetStream so credit events survive API restarts.
"""

import json
import logging

import nats
from nats.aio.client import Client as NatsClient

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level singleton
nc: NatsClient | None = None
js = None
BILLING_STREAM = "BILLING"
BILLING_SUBJECTS = ["billing.*"]


async def connect() -> NatsClient:
    """Connect to NATS server. Call once during app startup."""
    global nc, js
    nc = await nats.connect(
        settings.nats_url,
        max_reconnect_attempts=-1,
        reconnect_time_wait=2,
    )
    js = nc.jetstream()
    await ensure_billing_stream()
    logger.info("Connected to NATS at %s", settings.nats_url)
    return nc


async def disconnect():
    """Drain and close the NATS connection. Call during app shutdown."""
    global nc, js
    if nc and nc.is_connected:
        await nc.drain()
        logger.info("NATS connection closed")
    nc = None
    js = None


def get_nc() -> NatsClient:
    """Get the current NATS connection. Raises if not connected."""
    if nc is None or not nc.is_connected:
        raise RuntimeError("NATS not connected")
    return nc


async def ensure_billing_stream():
    """Ensure the JetStream stream that stores billing events exists."""
    global js
    if js is None:
        js = get_nc().jetstream()
    try:
        await js.stream_info(BILLING_STREAM)
    except Exception:
        try:
            await js.add_stream(name=BILLING_STREAM, subjects=BILLING_SUBJECTS)
        except Exception as e:
            # Multiple uvicorn workers can race on first startup. If another
            # worker created the stream, continue; otherwise surface the fault.
            msg = str(e).lower()
            if "already" not in msg and "in use" not in msg:
                raise
    return js


async def publish_billing_event(subject: str, payload: dict) -> None:
    """Publish a billing event through JetStream and wait for server ack."""
    stream = await ensure_billing_stream()
    await stream.publish(subject, json.dumps(payload).encode())
