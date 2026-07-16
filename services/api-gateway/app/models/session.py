from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PodSession(Base):
    __tablename__ = "pod_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String, nullable=False)
    image: Mapped[str] = mapped_column(String, nullable=False, default="hopper/vm-ubuntu:22.04")
    cpu: Mapped[str] = mapped_column(String, nullable=False, default="1")
    memory: Mapped[str] = mapped_column(String, nullable=False, default="2Gi")
    namespace: Mapped[str] = mapped_column(String, nullable=False)
    pod_name: Mapped[str] = mapped_column(String, nullable=False)
    vscode_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ssh_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ssh_password: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Credit-exhaustion grace deadline. Set on the first failed billing tick;
    # the VM is only terminated once this passes (cleared if the user tops up
    # and a later tick succeeds). NULL = not in grace.
    grace_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    state: Mapped[str] = mapped_column(String, default="pending")
    credits_charged: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
