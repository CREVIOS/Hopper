from types import SimpleNamespace

import pytest

from app.models.notification import Notification
from app.services import notification_service


class FakeDB:
    """Records what was added/committed; select() results are scripted."""

    def __init__(self, existing=None):
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.existing = existing
        self.executed = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        pass

    async def scalar(self, stmt):
        return self.existing

    async def scalars(self, stmt):
        return SimpleNamespace(all=lambda: [])

    async def execute(self, stmt):
        self.executed.append(stmt)


def _notification(**overrides) -> Notification:
    defaults = dict(
        id="n-1",
        user_id="stu-1",
        type="credit_warning",
        severity="warning",
        title="Low credits",
        body="About 10 minutes left.",
        action_url="/credits",
        dedupe_key="credit-warning:pod-1:10",
        metadata_={"pod_id": "pod-1"},
        read_at=None,
    )
    return Notification(**{**defaults, **overrides})


# --- validation --------------------------------------------------------------


async def test_unknown_type_is_rejected(monkeypatch):
    monkeypatch.setattr(notification_service, "publish_notification", _noop)

    with pytest.raises(ValueError, match="unknown notification type"):
        await notification_service.create_notification(
            FakeDB(), user_id="u", type="not_a_type", severity="info",
            title="t", body="b",
        )


async def test_unknown_severity_is_rejected(monkeypatch):
    monkeypatch.setattr(notification_service, "publish_notification", _noop)

    with pytest.raises(ValueError, match="unknown notification severity"):
        await notification_service.create_notification(
            FakeDB(), user_id="u", type="credit_warning", severity="catastrophic",
            title="t", body="b",
        )


async def _noop(*args, **kwargs):
    pass


# --- dedupe ------------------------------------------------------------------


async def test_dedupe_key_returns_the_existing_row_instead_of_a_duplicate(monkeypatch):
    """The billing tick runs every minute; without this the bell would flood."""
    monkeypatch.setattr(notification_service, "publish_notification", _noop)

    existing = _notification()
    db = FakeDB(existing=existing)

    result = await notification_service.create_notification(
        db,
        user_id="stu-1",
        type="credit_warning",
        severity="warning",
        title="Low credits",
        body="About 10 minutes left.",
        dedupe_key="credit-warning:pod-1:10",
    )

    assert result is existing
    assert db.added == []      # nothing new written
    assert db.commits == 0


async def test_a_new_notification_is_written_and_published(monkeypatch):
    published = []

    async def fake_publish(n):
        published.append(n)

    monkeypatch.setattr(notification_service, "publish_notification", fake_publish)

    db = FakeDB(existing=None)
    result = await notification_service.create_notification(
        db,
        user_id="stu-1",
        type="credits_received",
        severity="success",
        title="Credits received",
        body="10 credits.",
        dedupe_key="credits-received:t-1",
    )

    assert db.added == [result]
    assert db.commits == 1
    assert published == [result]  # pushed live over NATS for the bell


# --- failure isolation -------------------------------------------------------


async def test_create_safely_swallows_errors_and_rolls_back(monkeypatch):
    """A notification must never take down the billing tick or a credit transfer."""

    async def boom(db, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(notification_service, "create_notification", boom)

    db = FakeDB()
    result = await notification_service.create_notification_safely(
        db, user_id="stu-1", type="credit_warning", severity="warning",
        title="t", body="b",
    )

    assert result is None
    assert db.rollbacks == 1


async def test_create_safely_never_raises_even_if_the_rollback_fails(monkeypatch):
    """A session broken enough to fail create_notification can fail rollback too.
    If that escaped, it would blow up a credit transfer that already committed."""

    async def boom(db, **kwargs):
        raise RuntimeError("db exploded")

    class BrokenDB(FakeDB):
        async def rollback(self):
            raise RuntimeError("rollback exploded too")

    monkeypatch.setattr(notification_service, "create_notification", boom)

    result = await notification_service.create_notification_safely(
        BrokenDB(), user_id="stu-1", type="credit_warning", severity="warning",
        title="t", body="b",
    )

    assert result is None  # swallowed, not raised


# --- read tracking -----------------------------------------------------------


async def test_marking_read_stamps_read_at_once(monkeypatch):
    notification = _notification()
    db = FakeDB(existing=notification)

    first = await notification_service.mark_notification_read(
        db, user_id="stu-1", notification_id="n-1"
    )
    stamped = first.read_at

    second = await notification_service.mark_notification_read(
        db, user_id="stu-1", notification_id="n-1"
    )

    assert stamped is not None
    assert second.read_at == stamped  # idempotent — not re-stamped
    assert db.commits == 1


async def test_marking_someone_elses_notification_read_returns_none():
    db = FakeDB(existing=None)  # the user-scoped query finds nothing

    result = await notification_service.mark_notification_read(
        db, user_id="attacker", notification_id="n-1"
    )

    assert result is None


# --- SSE subject -------------------------------------------------------------


def test_notification_subject_is_a_safe_per_user_nats_token():
    """User ids can contain characters NATS treats as subject separators."""
    subject = notification_service.notification_subject("user@cs.du.ac.bd")

    assert subject.startswith("notifications.")
    token = subject.removeprefix("notifications.")
    assert "." not in token and "*" not in token and ">" not in token


def test_notification_subjects_differ_per_user():
    a = notification_service.notification_subject("stu-1")
    b = notification_service.notification_subject("stu-2")

    assert a != b
