from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmailCode(Base):
    """A one-time numeric code emailed to a user for a specific purpose.

    Codes are stored as a SHA-256 hash (never plaintext). One code per
    (email, purpose) is kept active at a time — issuing a new one supersedes
    the previous unconsumed rows. `attempts` caps brute-force guessing.
    """

    __tablename__ = "email_codes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # "verify_email" | "password_reset"
    purpose: Mapped[str] = mapped_column(String, nullable=False)
    code_hash: Mapped[str] = mapped_column(String, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
