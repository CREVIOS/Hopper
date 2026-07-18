"""Unit tests for the orphan VM reconciler (session_reaper.reap_orphan_vm_pods)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.session_reaper import reap_orphan_vm_pods


class _FakeResult:
    def __init__(self, ids):
        self._ids = ids

    def scalars(self):
        return self

    def all(self):
        return list(self._ids)


class _FakeDB:
    """Minimal stand-in: returns the given active session ids from execute()."""

    def __init__(self, active_ids):
        self._active = active_ids

    async def execute(self, _query):
        return _FakeResult(self._active)


def _ts(seconds_ago: int, now: datetime) -> str:
    return (now - timedelta(seconds=seconds_ago)).isoformat().replace("+00:00", "Z")


@pytest.mark.asyncio
async def test_reaps_only_pods_whose_session_is_inactive():
    now = datetime.now(timezone.utc)
    pods = [
        ("vm-alive", "sess-alive", _ts(3600, now)),      # active session -> keep
        ("vm-dead", "sess-dead", _ts(3600, now)),        # terminated session -> reap
        ("vm-missing", "sess-gone", _ts(3600, now)),     # no session row -> reap
    ]
    deleted: list[str] = []

    async def fake_delete(name):
        deleted.append(name)

    db = _FakeDB(active_ids={"sess-alive"})  # only the alive one is active
    reaped = await reap_orphan_vm_pods(
        db, now=now, list_pods=lambda: _aw(pods), delete=fake_delete
    )

    assert set(reaped) == {"vm-dead", "vm-missing"}
    assert set(deleted) == {"vm-dead", "vm-missing"}
    assert "vm-alive" not in deleted


@pytest.mark.asyncio
async def test_skips_young_pods_and_labelless_pods():
    now = datetime.now(timezone.utc)
    pods = [
        ("vm-fresh", "sess-fresh", _ts(30, now)),   # inactive but too young -> skip
        ("vm-nolabel", "", _ts(3600, now)),         # no pod-id label -> skip
        ("vm-old", "sess-old", _ts(3600, now)),     # inactive + old -> reap
    ]
    deleted: list[str] = []

    async def fake_delete(name):
        deleted.append(name)

    db = _FakeDB(active_ids=set())  # none active
    reaped = await reap_orphan_vm_pods(
        db, now=now, list_pods=lambda: _aw(pods), delete=fake_delete
    )

    assert reaped == ["vm-old"]
    assert deleted == ["vm-old"]


@pytest.mark.asyncio
async def test_no_pods_is_noop():
    db = _FakeDB(active_ids=set())
    reaped = await reap_orphan_vm_pods(db, list_pods=lambda: _aw([]), delete=None)
    assert reaped == []


async def _aw(value):
    """Wrap a plain value in an awaitable for the injected list_pods callable."""
    return value
