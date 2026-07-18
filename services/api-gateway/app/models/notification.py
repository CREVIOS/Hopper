from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Notification(Base):
    """A user-facing notification (VM lifecycle, credit alerts, transfers).

    Backs the in-app notification center. The service layer keeps only the
    newest 100 rows per user — treat this as a rolling window, not an audit
    trail (audit_logs is the durable record).
    """

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # success | warning | error | info — maps 1:1 to toast styling.
    type: Mapped[str] = mapped_column(String, nullable=False, default="info")
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Structured payload for client actions (e.g. {"pod_id": ...}).
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
