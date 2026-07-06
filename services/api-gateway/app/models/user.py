from datetime import datetime

from sqlalchemy import String, DateTime, Boolean, func, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="student")
    # A self-service "I am a Teacher" signup lands as a student with this flag
    # set until an admin approves (→ professor) or rejects it.
    pending_teacher: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    university_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
