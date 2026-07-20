from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserQuota(Base):
    """Per-user resource quota override (``user_quotas``).

    A row is an override; users without one fall back to the global defaults in
    config (default_max_concurrent_vms / default_max_workspace_gb). SRS
    FR-QUOTA-001/002, FR-HC-23.
    """

    __tablename__ = "user_quotas"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    max_concurrent_vms: Mapped[int] = mapped_column(Integer, nullable=False)
    max_workspace_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
