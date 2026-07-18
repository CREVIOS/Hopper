from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApiKey(Base):
    """A scoped API key for programmatic access (CLI, scripts).

    Only the SHA-256 hash of the secret is stored; the plaintext token
    (``hop_<random>``) is returned exactly once at creation. ``prefix`` keeps
    the first characters of the token so a user can tell keys apart in the
    list view. Revocation is a soft delete (``revoked_at``) so the row stays
    for auditability.
    """

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # "read_only" (GET/HEAD only) or "full_access" (everything the user can do
    # with a session, except managing API keys themselves).
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="read_only", server_default="read_only"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
