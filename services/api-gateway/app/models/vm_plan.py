from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VmPlanRow(Base):
    """Admin-configurable VM plan catalogue (table ``vm_plans``).

    The runtime source of truth for plan resources + pricing, replacing the
    values previously hardcoded across the gateway, the Go orchestrator, and the
    frontend. ``name`` is the stable key used everywhere a plan is referenced
    (pod_sessions.plan, the CreatePod gRPC call, the k8s label).
    """

    __tablename__ = "vm_plans"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    cpu: Mapped[str] = mapped_column(String, nullable=False)
    memory: Mapped[str] = mapped_column(String, nullable=False)
    disk: Mapped[str] = mapped_column(String, nullable=False)
    credits_per_hour: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    workspace_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    # Soft-delete flag: an inactive plan is hidden from the picker and cannot be
    # used for new pods, but existing pods on it keep billing correctly.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
