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
    # Number of user-initiated TTL extensions applied (FR-HC-27 caps this at 3).
    extension_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    # Credit-exhaustion grace deadline (FR-HC-18). Set on the first failed billing
    # tick; the VM is only terminated once this passes (cleared if the user tops
    # up and a later tick succeeds). NULL = not in grace. Deliberately NOT
    # expires_at: that is the session TTL, and overloading it would make the
    # session reaper kill the VM at the grace deadline and destroy the real TTL.
    grace_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Idle auto-shutdown (FR-HC-31). Set when a VM has looked idle for long
    # enough and the user has been warned; the VM is terminated once this passes.
    # Cleared the moment real activity resumes, so it doubles as the "warned"
    # flag — null means we are not currently counting down on this VM.
    idle_shutdown_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    state: Mapped[str] = mapped_column(String, default="pending")
    # Network isolation group (HOP-19 18.3). VMs sharing a group can reach
    # each other over the pod network; NULL = fully isolated (the default).
    network_group: Mapped[str | None] = mapped_column(String(32), nullable=True)
    credits_charged: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
