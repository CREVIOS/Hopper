from datetime import datetime

from sqlalchemy import String, BigInteger, Numeric, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MetricsSample(Base):
    __tablename__ = "metrics_samples"

    time: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    pod_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    cpu_percent: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    memory_used_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    memory_limit_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
