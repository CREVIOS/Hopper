from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from app.core.database import Base


class AlertSubscription(Base):
    """Per-user opt-in for telemetry-agent alerts.

    One row per user. The *sending* accounts (Resend for email, the Green API
    Telegram gateway for chat) are global platform config; this table holds each
    user's own destinations and the minimum severity they care about, so a single
    alert fans out to every subscribed user rather than one hard-coded recipient.
    """

    __tablename__ = "alert_subscriptions"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=expression.false()
    )
    # Blank = fall back to the user's account email (resolved when saving).
    email_address: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    telegram_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=expression.false()
    )
    # Telegram delivery is by phone number via the Green API Telegram instance.
    telegram_number: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    # Lowest severity this user wants delivered: info | warning | critical.
    min_severity: Mapped[str] = mapped_column(String, nullable=False, server_default="warning")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
