"""API keys for programmatic access (HOP-19 18.1).

Token format: ``hop_<43 urlsafe-random chars>`` (256 bits of entropy). Only
the SHA-256 hex digest is persisted; lookup is by digest, so verification is
a single indexed equality query and a DB dump alone cannot be replayed as
credentials. ``prefix`` (the first 12 chars of the token) is stored so users
can identify keys in the list view.

Scopes:
    read_only    — GET/HEAD/OPTIONS only.
    full_access  — everything the owning user could do with a session, except
                   managing API keys themselves (a leaked key must not be able
                   to mint or destroy keys — that always requires a session).
"""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "hop_"
PREFIX_LEN = 12  # chars of the full token kept for display, e.g. "hop_AbCd1234"
SCOPES = ("read_only", "full_access")
MAX_KEYS_PER_USER = 10

# Refresh last_used_at at most this often per key — it is a usage hint for
# the owner, not an audit log, and writing on every request would turn each
# API call into a DB write.
_LAST_USED_REFRESH = timedelta(seconds=60)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def looks_like_api_key(value: str) -> bool:
    return value.startswith(TOKEN_PREFIX)


async def create_key(
    db: AsyncSession, user_id: str, name: str, scope: str
) -> tuple[ApiKey, str]:
    """Create a key for ``user_id`` and return (row, plaintext token).

    The plaintext token is NOT stored — this is the only time it exists
    server-side. Raises ValueError on invalid scope or per-user key cap.
    """
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}")

    active = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
    )
    if len(active.scalars().all()) >= MAX_KEYS_PER_USER:
        raise ValueError(f"API key limit reached ({MAX_KEYS_PER_USER} active keys)")

    token = generate_token()
    row = ApiKey(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        prefix=token[:PREFIX_LEN],
        key_hash=hash_token(token),
        scope=scope,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row, token


async def verify_key(db: AsyncSession, token: str) -> ApiKey | None:
    """Resolve a presented token to its active ApiKey row, or None.

    Also refreshes ``last_used_at`` (throttled). The commit here is safe:
    verification runs in its own short-lived session before any request
    handler state exists.
    """
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_token(token)))
    row = result.scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None

    now = datetime.utcnow()
    if row.last_used_at is None or (now - row.last_used_at) >= _LAST_USED_REFRESH:
        row.last_used_at = now
        try:
            await db.commit()
        except Exception:  # pragma: no cover - usage hint only, never fail auth
            logger.warning("api-key last_used_at update failed", exc_info=True)
            await db.rollback()
    return row


async def revoke_key(db: AsyncSession, user_id: str, key_id: str) -> bool:
    """Soft-revoke ``key_id`` if it belongs to ``user_id``. Idempotent."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    if row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        await db.commit()
    return True


async def list_keys(db: AsyncSession, user_id: str) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())
