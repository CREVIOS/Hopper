"""Issue and validate one-time email codes (signup verify + password reset).

Codes are numeric, stored only as a SHA-256 hash, single-use, expiring, and
attempt-capped. Issuing a new code for an (email, purpose) supersedes any prior
unconsumed codes so only the latest is valid.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_code import EmailCode

VERIFY_EMAIL = "verify_email"
PASSWORD_RESET = "password_reset"


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _random_code() -> str:
    n = settings.email_code_length
    # Zero-padded numeric code in [0, 10**n).
    return f"{secrets.randbelow(10 ** n):0{n}d}"


async def issue_code(db: AsyncSession, email: str, purpose: str) -> str:
    """Create a fresh code for (email, purpose), invalidating older unconsumed
    ones. Returns the plaintext code (to email). Caller commits."""
    email = email.lower().strip()
    now = datetime.utcnow()
    # Supersede any still-live codes for this email+purpose.
    await db.execute(
        update(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    code = _random_code()
    db.add(
        EmailCode(
            id=str(uuid.uuid4()),
            email=email,
            purpose=purpose,
            code_hash=_hash(code),
            expires_at=now + timedelta(seconds=settings.email_code_ttl_seconds),
        )
    )
    return code


async def verify_code(db: AsyncSession, email: str, purpose: str, code: str) -> bool:
    """Validate and consume a code. Returns True on success. Wrong/expired/
    exhausted codes return False (and increment the attempt counter). Caller
    commits."""
    email = email.lower().strip()
    code = (code or "").strip()
    now = datetime.utcnow()
    result = await db.execute(
        select(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
        )
        .order_by(EmailCode.created_at.desc())
    )
    row = result.scalars().first()
    if row is None:
        return False
    if row.expires_at < now:
        return False
    if row.attempts >= settings.email_code_max_attempts:
        return False
    if not secrets.compare_digest(row.code_hash, _hash(code)):
        row.attempts += 1
        return False
    row.consumed_at = now
    return True
