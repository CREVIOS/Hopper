from datetime import datetime, timedelta

from app.services import audit_retention


class FakeResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class FakeDB:
    """Minimal async DB double: records executed statements and commits."""

    def __init__(self, rowcount=0):
        self._rowcount = rowcount
        self.executed = []
        self.commits = 0

    async def execute(self, stmt):
        self.executed.append(stmt)
        return FakeResult(self._rowcount)

    async def commit(self):
        self.commits += 1


async def test_purge_disabled_when_retention_non_positive():
    # retention_days <= 0 means "retain forever": no DELETE must ever run.
    db = FakeDB(rowcount=5)
    for days in (0, -1):
        deleted = await audit_retention.purge_expired_audit_logs(db, days)
        assert deleted == 0
    assert db.executed == []
    assert db.commits == 0


async def test_purge_deletes_and_returns_rowcount():
    db = FakeDB(rowcount=7)
    deleted = await audit_retention.purge_expired_audit_logs(db, 90)
    assert deleted == 7
    assert len(db.executed) == 1
    assert db.commits == 1


async def test_purge_cutoff_is_now_minus_window():
    db = FakeDB(rowcount=0)
    fixed_now = datetime(2026, 7, 11, 12, 0, 0)
    await audit_retention.purge_expired_audit_logs(db, 90, now=fixed_now)

    stmt = db.executed[0]
    compiled = stmt.compile()
    cutoffs = [v for v in compiled.params.values() if isinstance(v, datetime)]
    assert cutoffs == [fixed_now - timedelta(days=90)]
