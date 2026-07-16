"""Notification center API + real-time SSE stream.

GET  /notifications          → recent notifications (rolling window) + unread count
POST /notifications/{id}/read → mark one read
POST /notifications/read-all  → mark all read
GET  /notifications/stream    → SSE: live pushes on NATS notify.user.<sub>

The stream subscribes per-connection (no queue group — every open tab on
every gateway worker/replica must receive the push). Auth happens at
connect time via the session cookie, same as the metrics SSE endpoint.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core import nats as nats_client
from app.dependencies import get_current_user, get_db
from app.models.notification import Notification
from app.schemas.user import TokenPayload

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "data": n.data,
        "read": n.read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("/")
async def list_notifications(
    limit: int = 50,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent notifications for the current user, newest first."""
    limit = max(1, min(limit, 100))
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.sub)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    items = result.scalars().all()
    unread_result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == current_user.sub, Notification.read.is_(False))
    )
    return {
        "notifications": [_serialize(n) for n in items],
        "unread_count": unread_result.scalar_one(),
    }


@router.post("/read-all")
async def mark_all_read(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark every notification for the current user as read."""
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.sub, Notification.read.is_(False))
        .values(read=True)
    )
    await db.commit()
    return {"message": "ok"}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    row = await db.get(Notification, notification_id)
    if row is None or row.user_id != current_user.sub:
        # Same 404 for "missing" and "not yours" — don't leak other users' ids.
        raise HTTPException(status_code=404, detail="Notification not found")
    row.read = True
    await db.commit()
    return {"message": "ok"}


@router.get("/stream")
async def stream_notifications(
    current_user: TokenPayload = Depends(get_current_user),
):
    """Live notification stream (SSE) for the current user."""
    user_id = current_user.sub

    async def event_generator():
        nc = nats_client.get_nc()
        queue: asyncio.Queue = asyncio.Queue()

        async def _on_msg(msg):
            await queue.put(msg.data)

        sub = await nc.subscribe(f"notify.user.{user_id}", cb=_on_msg)
        try:
            yield {"event": "connected", "data": json.dumps({"user_id": user_id})}
            while True:
                try:
                    raw = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": "notification", "data": raw.decode()}
                except asyncio.TimeoutError:
                    # Keepalive so proxies/browsers don't drop the connection.
                    yield {"event": "ping", "data": ""}
        finally:
            await sub.unsubscribe()

    return EventSourceResponse(event_generator())
