"""NATS client for the API gateway.

Provides pub/sub connectivity used by the billing consumer and metrics streaming.
"""

import logging

import nats
from nats.aio.client import Client as NatsClient

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level singleton
nc: NatsClient | None = None


async def connect() -> NatsClient:
    """Connect to NATS server. Call once during app startup."""
    global nc
    nc = await nats.connect(
        settings.nats_url,
        max_reconnect_attempts=-1,
        reconnect_time_wait=2,
    )
    logger.info("Connected to NATS at %s", settings.nats_url)
    return nc


async def disconnect():
    """Drain and close the NATS connection. Call during app shutdown."""
    global nc
    if nc and nc.is_connected:
        await nc.drain()
        logger.info("NATS connection closed")
    nc = None


def get_nc() -> NatsClient:
    """Get the current NATS connection. Raises if not connected."""
    if nc is None or not nc.is_connected:
        raise RuntimeError("NATS not connected")
    return nc
