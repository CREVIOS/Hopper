from datetime import datetime

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: str
    type: str
    severity: str
    title: str
    body: str
    action_url: str | None = None
    metadata: dict = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
