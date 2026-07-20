from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserWorkspace(Base):
    """Per-user persistent workspace (FR-HC-28).

    Exactly one row per user. Records the K8s PVC (name, capacity, storage
    class) that backs the user's /workspace. The orchestrator creates the PVC
    lazily on first launch, mounts it read-write every session, and never
    deletes it in the session lifecycle — only an explicit admin action
    (FR-HC-30) may. `used_gb` is refreshed by the metrics path (best-effort).
    """

    __tablename__ = "user_workspaces"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    pvc_name: Mapped[str] = mapped_column(String, nullable=False)
    storage_class: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    capacity_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    used_gb: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_mounted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
