import base64
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import nats as nats_client
from app.models.notification import Notification

logger = logging.getLogger(__name__)

MAX_NOTIFICATIONS_PER_USER = 100
VALID_SEVERITIES = {"success", "warning", "error", "info"}
VALID_TYPES = {
    "credit_warning",
    "credit_grace",
    "credits_received",
    "vm_ready",
    "vm_terminated",
    "vm_failed",
}


def notification_subject(user_id: str) -> str:
    token = base64.urlsafe_b64encode(user_id.encode()).decode().rstrip("=")
    return f"notifications.{token}"


def notification_to_response(notification: Notification) -> dict[str, Any]:
    return {
        "id": notification.id,
        "type": notification.type,
        "severity": notification.severity,
        "title": notification.title,
        "body": notification.body,
        "action_url": notification.action_url,
        "metadata": notification.metadata_ or {},
        "read_at": notification.read_at,
        "created_at": notification.created_at,
    }


def notification_to_event(notification: Notification) -> dict[str, Any]:
    data = notification_to_response(notification)
    for key in ("read_at", "created_at"):
        if data[key] is not None:
            data[key] = data[key].isoformat()
    return data


async def publish_notification(notification: Notification) -> None:
    try:
        nc = nats_client.get_nc()
        await nc.publish(
            notification_subject(notification.user_id),
            json.dumps(notification_to_event(notification)).encode(),
        )
    except RuntimeError:
        logger.debug("NATS unavailable; notification %s stored only", notification.id)
    except Exception:
        logger.exception("Failed to publish notification %s", notification.id)


async def prune_notifications(db: AsyncSession, user_id: str) -> None:
    old_ids = (
        await db.scalars(
            select(Notification.id)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(MAX_NOTIFICATIONS_PER_USER)
        )
    ).all()
    if old_ids:
        await db.execute(delete(Notification).where(Notification.id.in_(old_ids)))


async def create_notification(
    db: AsyncSession,
    *,
    user_id: str,
    type: str,
    severity: str,
    title: str,
    body: str,
    action_url: str | None = None,
    dedupe_key: str | None = None,
    metadata: dict | None = None,
    publish: bool = True,
) -> Notification:
    if type not in VALID_TYPES:
        raise ValueError(f"unknown notification type: {type}")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"unknown notification severity: {severity}")

    if dedupe_key:
        existing = await db.scalar(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.dedupe_key == dedupe_key,
            )
        )
        if existing is not None:
            return existing

    notification = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        type=type,
        severity=severity,
        title=title,
        body=body,
        action_url=action_url,
        dedupe_key=dedupe_key,
        metadata_=metadata or {},
    )
    db.add(notification)
    await db.flush()
    await prune_notifications(db, user_id)
    await db.commit()
    await db.refresh(notification)
    if publish:
        await publish_notification(notification)
    return notification


async def create_notification_safely(
    db: AsyncSession,
    **kwargs,
) -> Notification | None:
    try:
        return await create_notification(db, **kwargs)
    except Exception:
        logger.exception("Failed to create notification")
        await db.rollback()
        return None


async def unread_count(db: AsyncSession, user_id: str) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return int(count or 0)


async def mark_notification_read(
    db: AsyncSession,
    *,
    user_id: str,
    notification_id: str,
) -> Notification | None:
    notification = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    if notification is None:
        return None
    if notification.read_at is None:
        notification.read_at = datetime.utcnow()
        await db.commit()
        await db.refresh(notification)
    return notification
