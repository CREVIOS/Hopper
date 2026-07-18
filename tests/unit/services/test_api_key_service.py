import hashlib
from datetime import datetime, timedelta

import pytest

from app.models.api_key import ApiKey

from app.services import api_key_service


def test_generate_token_shape_and_uniqueness():
    t1 = api_key_service.generate_token()
    t2 = api_key_service.generate_token()
    assert t1.startswith(api_key_service.TOKEN_PREFIX)
    assert t1 != t2
    # 32 random bytes urlsafe-encoded = 43 chars + the "hop_" prefix.
    assert len(t1) == len(api_key_service.TOKEN_PREFIX) + 43


def test_hash_token_is_sha256_hex():
    token = "hop_example"
    assert api_key_service.hash_token(token) == hashlib.sha256(token.encode()).hexdigest()
    # Deterministic: the DB lookup depends on it.
    assert api_key_service.hash_token(token) == api_key_service.hash_token(token)


def test_looks_like_api_key():
    assert api_key_service.looks_like_api_key("hop_abc123")
    assert not api_key_service.looks_like_api_key("eyJhbGciOi...")  # a JWT
    assert not api_key_service.looks_like_api_key("")


def test_prefix_is_displayable_slice_of_token():
    token = api_key_service.generate_token()
    prefix = token[: api_key_service.PREFIX_LEN]
    assert token.startswith(prefix)
    assert len(prefix) < len(token)  # never the whole secret


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one_or_none(self):
        if isinstance(self._rows, list):
            return self._rows[0] if self._rows else None
        return self._rows


class FakeDB:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = []

    async def execute(self, stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return FakeExecuteResult(self.execute_results.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


async def test_create_key_rejects_invalid_scope():
    with pytest.raises(ValueError) as exc_info:
        await api_key_service.create_key(FakeDB(), "user-1", "CLI", "admin")

    assert "scope must be one of" in str(exc_info.value)


async def test_create_key_enforces_per_user_limit():
    active = [
        ApiKey(id=str(index), user_id="user-1", name=f"key-{index}", prefix="hop_prefix", key_hash="h", scope="read_only")
        for index in range(api_key_service.MAX_KEYS_PER_USER)
    ]

    with pytest.raises(ValueError) as exc_info:
        await api_key_service.create_key(FakeDB(execute_results=[active]), "user-1", "CLI", "read_only")

    assert "API key limit reached" in str(exc_info.value)


async def test_create_key_persists_row_and_returns_plaintext(monkeypatch):
    monkeypatch.setattr("app.services.api_key_service.generate_token", lambda: "hop_secret_token")

    db = FakeDB(execute_results=[[]])
    row, token = await api_key_service.create_key(db, "user-1", "CLI", "full_access")

    assert token == "hop_secret_token"
    assert row.user_id == "user-1"
    assert row.prefix == "hop_secret_t"
    assert row.key_hash == api_key_service.hash_token(token)
    assert db.commits == 1
    assert db.refreshed == [row]


async def test_verify_key_returns_none_for_missing_or_revoked():
    assert await api_key_service.verify_key(FakeDB(execute_results=[None]), "hop_missing") is None

    revoked = ApiKey(
        id="key-1",
        user_id="user-1",
        name="CLI",
        prefix="hop_prefix",
        key_hash=api_key_service.hash_token("hop_secret"),
        scope="read_only",
        revoked_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    assert await api_key_service.verify_key(FakeDB(execute_results=[revoked]), "hop_secret") is None


async def test_verify_key_refreshes_last_used_at_when_stale():
    row = ApiKey(
        id="key-1",
        user_id="user-1",
        name="CLI",
        prefix="hop_prefix",
        key_hash=api_key_service.hash_token("hop_secret"),
        scope="read_only",
        last_used_at=datetime.utcnow() - api_key_service._LAST_USED_REFRESH - timedelta(seconds=1),
    )
    db = FakeDB(execute_results=[row])

    result = await api_key_service.verify_key(db, "hop_secret")

    assert result is row
    assert db.commits == 1
    assert row.last_used_at is not None


async def test_verify_key_skips_commit_when_last_used_is_recent():
    recent = datetime.utcnow()
    row = ApiKey(
        id="key-1",
        user_id="user-1",
        name="CLI",
        prefix="hop_prefix",
        key_hash=api_key_service.hash_token("hop_secret"),
        scope="read_only",
        last_used_at=recent,
    )
    db = FakeDB(execute_results=[row])

    result = await api_key_service.verify_key(db, "hop_secret")

    assert result is row
    assert row.last_used_at == recent
    assert db.commits == 0


async def test_verify_key_rolls_back_when_usage_hint_commit_fails():
    row = ApiKey(
        id="key-1",
        user_id="user-1",
        name="CLI",
        prefix="hop_prefix",
        key_hash=api_key_service.hash_token("hop_secret"),
        scope="read_only",
        last_used_at=None,
    )

    class BrokenDB(FakeDB):
        async def commit(self):
            raise RuntimeError("db down")

    db = BrokenDB(execute_results=[row])
    result = await api_key_service.verify_key(db, "hop_secret")

    assert result is row
    assert db.rollbacks == 1


async def test_revoke_key_is_idempotent_and_user_scoped():
    row = ApiKey(
        id="key-1",
        user_id="user-1",
        name="CLI",
        prefix="hop_prefix",
        key_hash="hash",
        scope="full_access",
    )
    db = FakeDB(execute_results=[row])

    assert await api_key_service.revoke_key(db, "user-1", "key-1") is True
    assert row.revoked_at is not None
    assert db.commits == 1

    already_revoked = ApiKey(
        id="key-1",
        user_id="user-1",
        name="CLI",
        prefix="hop_prefix",
        key_hash="hash",
        scope="full_access",
        revoked_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    db = FakeDB(execute_results=[already_revoked])
    assert await api_key_service.revoke_key(db, "user-1", "key-1") is True
    assert db.commits == 0

    assert await api_key_service.revoke_key(FakeDB(execute_results=[None]), "user-1", "missing") is False


async def test_list_keys_returns_all_rows():
    rows = [
        ApiKey(id="key-1", user_id="user-1", name="CLI", prefix="hop_prefix", key_hash="hash", scope="read_only"),
        ApiKey(id="key-2", user_id="user-1", name="CI", prefix="hop_prefi2", key_hash="hash2", scope="full_access"),
    ]

    result = await api_key_service.list_keys(FakeDB(execute_results=[rows]), "user-1")

    assert result == rows
