"""Usage dashboard — historical metrics and consumption data."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.schemas.user import TokenPayload

router = APIRouter()

RANGE_MAP = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


@router.get("/{pod_id}")
async def get_pod_usage(
    pod_id: str,
    range: str = "1h",
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get time-series usage data for a pod.

    Uses TimescaleDB time_bucket for efficient aggregation.
    Falls back to simple GROUP BY if TimescaleDB is not available.
    """
    delta = RANGE_MAP.get(range, timedelta(hours=1))
    since = datetime.utcnow() - delta

    # Determine bucket size based on range
    if delta <= timedelta(hours=1):
        bucket = "1 minute"
    elif delta <= timedelta(hours=6):
        bucket = "5 minutes"
    elif delta <= timedelta(hours=24):
        bucket = "15 minutes"
    else:
        bucket = "1 hour"

    try:
        result = await db.execute(
            text("""
                SELECT time_bucket(:bucket, time) AS bucket,
                       avg(cpu_percent) as avg_cpu,
                       avg(memory_used_bytes) as avg_memory,
                       max(memory_limit_bytes) as memory_limit
                FROM metrics_samples
                WHERE pod_id = :pod_id AND time > :since
                GROUP BY bucket
                ORDER BY bucket
            """),
            {"bucket": bucket, "pod_id": pod_id, "since": since},
        )
    except Exception:
        # Fallback without time_bucket (vanilla Postgres)
        result = await db.execute(
            text("""
                SELECT date_trunc('minute', time) AS bucket,
                       avg(cpu_percent) as avg_cpu,
                       avg(memory_used_bytes) as avg_memory,
                       max(memory_limit_bytes) as memory_limit
                FROM metrics_samples
                WHERE pod_id = :pod_id AND time > :since
                GROUP BY bucket
                ORDER BY bucket
            """),
            {"pod_id": pod_id, "since": since},
        )

    rows = result.fetchall()
    return {
        "pod_id": pod_id,
        "range": range,
        "data": [
            {
                "time": row.bucket.isoformat() if row.bucket else None,
                "cpu_percent": float(row.avg_cpu or 0),
                "memory_used_bytes": int(row.avg_memory or 0),
                "memory_limit_bytes": int(row.memory_limit or 0),
            }
            for row in rows
        ],
    }


@router.get("/summary/me/series")
async def get_my_usage_series(
    range: str = "24h",
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated time-series across all of the current user's pods.

    Used by the dashboard to show busyness over time instead of a single
    snapshot. Bucket size scales with the requested range so the response
    stays small enough to render directly without client-side downsampling.
    """
    delta = RANGE_MAP.get(range, timedelta(hours=24))
    since = datetime.utcnow() - delta

    if delta <= timedelta(hours=1):
        bucket = "1 minute"
    elif delta <= timedelta(hours=6):
        bucket = "5 minutes"
    elif delta <= timedelta(hours=24):
        bucket = "15 minutes"
    else:
        bucket = "1 hour"

    try:
        result = await db.execute(
            text("""
                SELECT time_bucket(:bucket, time) AS bucket,
                       avg(cpu_percent) as avg_cpu,
                       avg(memory_used_bytes) as avg_memory,
                       max(memory_limit_bytes) as memory_limit
                FROM metrics_samples
                WHERE user_id = :user_id AND time > :since
                GROUP BY bucket
                ORDER BY bucket
            """),
            {"bucket": bucket, "user_id": current_user.sub, "since": since},
        )
    except Exception:
        result = await db.execute(
            text("""
                SELECT date_trunc('hour', time) AS bucket,
                       avg(cpu_percent) as avg_cpu,
                       avg(memory_used_bytes) as avg_memory,
                       max(memory_limit_bytes) as memory_limit
                FROM metrics_samples
                WHERE user_id = :user_id AND time > :since
                GROUP BY bucket
                ORDER BY bucket
            """),
            {"user_id": current_user.sub, "since": since},
        )

    rows = result.fetchall()
    return {
        "range": range,
        "data": [
            {
                "time": row.bucket.isoformat() if row.bucket else None,
                "cpu_percent": float(row.avg_cpu or 0),
                "memory_used_bytes": int(row.avg_memory or 0),
                "memory_limit_bytes": int(row.memory_limit or 0),
            }
            for row in rows
        ],
    }


@router.get("/summary/me")
async def get_my_usage_summary(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage summary for the current user."""
    result = await db.execute(
        text("""
            SELECT count(distinct pod_id) as pod_count,
                   avg(cpu_percent) as avg_cpu,
                   sum(memory_used_bytes) / count(*) as avg_memory
            FROM metrics_samples
            WHERE user_id = :user_id
              AND time > now() - interval '24 hours'
        """),
        {"user_id": current_user.sub},
    )
    row = result.fetchone()
    return {
        "pod_count": row.pod_count if row else 0,
        "avg_cpu_percent": float(row.avg_cpu or 0) if row else 0,
        "avg_memory_bytes": int(row.avg_memory or 0) if row else 0,
    }
