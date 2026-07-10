from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VmQueueEntry(Base):
    """A pending VM create request that could not be admitted synchronously.

    Rows are created with state 'queued' when the cluster is full. The
    background admission loop scans them FCFS by ``seq`` (a gapless,
    monotonically increasing identity key) and promotes each to a real
    PodSession when capacity frees, transitioning through 'admitting' to
    'active' (or 'failed' on error).
    """

    __tablename__ = "vm_queue_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String, nullable=False)
    template: Mapped[str] = mapped_column(String, nullable=False)
    image: Mapped[str] = mapped_column(String, nullable=False)
    cpu: Mapped[str] = mapped_column(String, nullable=False)
    memory: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(
        String, nullable=False, default="queued", server_default="queued"
    )
    seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True, start=1), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pod_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("pod_sessions.id"), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
