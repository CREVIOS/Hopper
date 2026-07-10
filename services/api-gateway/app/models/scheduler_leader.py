from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SchedulerLeader(Base):
    """Single-row lease table for pooler-safe scheduler leader election.

    One row (id='vm-scheduler') is seeded by the migration. Gateway workers
    contend for leadership by writing their instance id into ``holder`` with a
    future ``expires_at``; only the current holder (or any worker once the
    lease has expired) runs the self-driven admission tick, so exactly one
    loop is active across all uvicorn workers.
    """

    __tablename__ = "scheduler_leader"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    holder: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
