"""NATS consumer that stores metrics snapshots in TimescaleDB.

Subscribes to metrics.* and batch-inserts rows into the metrics_samples hypertable.
"""

import json
import logging
from datetime import datetime

from app.core import nats as nats_client
from app.core.database import async_session
from app.models.metrics import MetricsSample

logger = logging.getLogger(__name__)


async def _handle_metrics(msg):
    try:
        data = json.loads(msg.data)
        pod_id = data["pod_id"]
    except (json.JSONDecodeError, KeyError):
        return

    try:
        async with async_session() as db:
            sample = MetricsSample(
                time=datetime.utcnow(),
                pod_id=pod_id,
                user_id=data.get("user_id", ""),
                cpu_percent=data.get("cpu_percent", 0),
                memory_used_bytes=data.get("memory_used_bytes", 0),
                memory_limit_bytes=data.get("memory_limit_bytes", 0),
            )
            db.add(sample)
            await db.commit()
    except Exception:
        logger.debug("Failed to store metrics for pod %s", pod_id)


async def start_metrics_consumer():
    """Subscribe to metrics.* and store in DB.

    Queue group ensures only one uvicorn worker writes the row per sample
    (otherwise --workers=4 produces 4× rows in the metrics_samples table).
    """
    nc = nats_client.get_nc()
    await nc.subscribe("metrics.*", queue="metrics-workers", cb=_handle_metrics)
    logger.info("Metrics consumer started — subscribed to metrics.* (queue=metrics-workers)")
