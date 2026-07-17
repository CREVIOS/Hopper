from datetime import datetime, timedelta

from app.services import verification


class FakeResult:
    def __init__(self, row):
        self._row = row

    def scalars(self):
        return self

    def first(self):
        return self._row


class FakeDB:
    def __init__(self, row=None):
        self.row = row
        self.executed = []
        self.added = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return FakeResult(self.row)

    def add(self, obj):
        self.added.append(obj)


class FakeRow:
    def __init__(self, *, expires_at, attempts=0, code_hash="", consumed_at=None, created_at=None):
        self.expires_at = expires_at
        self.attempts = attempts
        self.code_hash = code_hash
        self.consumed_at = consumed_at
        self.created_at = created_at or datetime.utcnow()


async def test_issue_code_invalidates_previous_unconsumed_codes_and_adds_new_row(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr("app.services.verification._random_code", lambda: "123456")
    monkeypatch.setattr("app.services.verification.uuid.uuid4", lambda: "code-id")
    monkeypatch.setattr("app.services.verification.settings.email_code_ttl_seconds", 300)

    code = await verification.issue_code(db, " USER@example.com ", verification.VERIFY_EMAIL)

    assert code == "123456"
    assert len(db.executed) == 1
    assert len(db.added) == 1
    created = db.added[0]
    assert created.id == "code-id"
    assert created.email == "user@example.com"
    assert created.purpose == verification.VERIFY_EMAIL
    assert created.code_hash == verification._hash("123456")


async def test_verify_code_returns_false_when_no_active_row():
    db = FakeDB(row=None)

    result = await verification.verify_code(
        db, "user@example.com", verification.VERIFY_EMAIL, "123456"
    )

    assert result is False


async def test_verify_code_rejects_expired_code():
    row = FakeRow(expires_at=datetime.utcnow() - timedelta(seconds=1))
    db = FakeDB(row=row)

    result = await verification.verify_code(
        db, "user@example.com", verification.VERIFY_EMAIL, "123456"
    )

    assert result is False
    assert row.consumed_at is None


async def test_verify_code_rejects_after_max_attempts(monkeypatch):
    row = FakeRow(
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        attempts=5,
    )
    db = FakeDB(row=row)
    monkeypatch.setattr("app.services.verification.settings.email_code_max_attempts", 5)

    result = await verification.verify_code(
        db, "user@example.com", verification.VERIFY_EMAIL, "123456"
    )

    assert result is False


async def test_verify_code_increments_attempts_on_wrong_code():
    row = FakeRow(
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        attempts=1,
        code_hash=verification._hash("654321"),
    )
    db = FakeDB(row=row)

    result = await verification.verify_code(
        db, "user@example.com", verification.VERIFY_EMAIL, "123456"
    )

    assert result is False
    assert row.attempts == 2
    assert row.consumed_at is None


async def test_verify_code_consumes_matching_code():
    row = FakeRow(
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        attempts=0,
        code_hash=verification._hash("123456"),
    )
    db = FakeDB(row=row)

    result = await verification.verify_code(
        db, " USER@example.com ", verification.VERIFY_EMAIL, " 123456 "
    )

    assert result is True
    assert row.consumed_at is not None
