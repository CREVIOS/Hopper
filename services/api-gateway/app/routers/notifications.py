import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core import nats as nats_client
from app.dependencies import get_current_user, get_db
from app.models.notification import Notification
from app.schemas.notification import NotificationListResponse, NotificationResponse
from app.schemas.user import TokenPayload
from app.services.notification_service import (
    mark_notification_read,
    notification_subject,
    notification_to_response,
    unread_count,
)

router = APIRouter()


@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    limit = max(1, min(limit, 100))
    notifications = (
        await db.scalars(
            select(Notification)
            .where(Notification.user_id == current_user.sub)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
    ).all()
    return {
        "notifications": [notification_to_response(n) for n in notifications],
        "unread_count": await unread_count(db, current_user.sub),
    }


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def read_notification(
    notification_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notification = await mark_notification_read(
        db,
        user_id=current_user.sub,
        notification_id=notification_id,
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification_to_response(notification)


@router.get("/stream")
async def stream_notifications(
    current_user: TokenPayload = Depends(get_current_user),
):
    async def event_generator():
        nc = nats_client.get_nc()
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        async def _on_msg(msg):
            await queue.put(msg.data)

        sub = await nc.subscribe(notification_subject(current_user.sub), cb=_on_msg)
        try:
            yield {"event": "connected", "data": json.dumps({"status": "ok"})}
            while True:
                try:
                    raw = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": "notification", "data": raw.decode()}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            await sub.unsubscribe()

    return EventSourceResponse(event_generator())
