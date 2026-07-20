from app.models.user_workspace import UserWorkspace
from app.services import workspace_service


class FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class FakeDB:
    """Returns None until a row is added, then that row (one user per test)."""

    def __init__(self):
        self.rows = []
        self.commits = 0

    async def execute(self, stmt):
        return FakeResult(self.rows[-1] if self.rows else None)

    def add(self, obj):
        self.rows.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass


def test_plan_workspace_capacity_map():
    assert workspace_service.PLAN_WORKSPACE_GB == {"small": 20, "medium": 50, "large": 100}


def test_pvc_name_is_dns_safe_and_deterministic():
    name = workspace_service.pvc_name_for("A1B2-UUID")
    assert name == "ws-user-a1b2-uuid"  # lower-cased


async def test_get_or_create_workspace_creates_then_reuses():
    db = FakeDB()

    ws1 = await workspace_service.get_or_create_workspace(db, "user-1", "large")
    assert isinstance(ws1, UserWorkspace)
    assert ws1.user_id == "user-1"
    assert ws1.pvc_name == "ws-user-user-1"
    assert ws1.capacity_gb == 100  # large
    assert db.commits == 1

    # Second launch reuses the existing row — no new PVC/row, no extra commit.
    ws2 = await workspace_service.get_or_create_workspace(db, "user-1", "large")
    assert ws2 is ws1
    assert db.commits == 1


async def test_get_or_create_workspace_defaults_capacity_for_unknown_plan():
    db = FakeDB()
    ws = await workspace_service.get_or_create_workspace(db, "u2", "mystery")
    assert ws.capacity_gb == workspace_service.DEFAULT_WORKSPACE_GB


async def test_create_records_configured_storage_class(monkeypatch):
    # New workspaces are born on the configured class (Longhorn migration lever).
    monkeypatch.setattr(workspace_service.settings, "workspace_storage_class", "longhorn-workspace")
    db = FakeDB()
    ws = await workspace_service.get_or_create_workspace(db, "u3", "small")
    assert ws.storage_class == "longhorn-workspace"


async def test_create_default_storage_class_is_empty(monkeypatch):
    # Default "" == cluster default (local-path); byte-identical to pre-Longhorn.
    monkeypatch.setattr(workspace_service.settings, "workspace_storage_class", "")
    db = FakeDB()
    ws = await workspace_service.get_or_create_workspace(db, "u4", "small")
    assert ws.storage_class == ""


async def test_existing_row_keeps_recorded_class(monkeypatch):
    # An already-provisioned workspace keeps its recorded class even if the
    # configured default changed — the column is the per-user migration ledger.
    monkeypatch.setattr(workspace_service.settings, "workspace_storage_class", "longhorn-workspace")
    db = FakeDB()
    existing = UserWorkspace(
        id="w-existing", user_id="u5", pvc_name="ws-user-u5",
        storage_class="", capacity_gb=20,
    )
    db.rows.append(existing)
    ws = await workspace_service.get_or_create_workspace(db, "u5", "small")
    assert ws is existing
    assert ws.storage_class == ""      # unchanged
    assert db.commits == 0             # no write


def _seed(db, capacity_gb):
    row = UserWorkspace(
        id="w1", user_id="u", pvc_name="ws-user-u", storage_class="", capacity_gb=capacity_gb
    )
    db.rows.append(row)
    return row


# --- App-2: capacity reconcile (grow-only) + admin resize (FR-HC-30) ---

async def test_grow_reconciles_capacity_upward():
    db = FakeDB()
    row = _seed(db, 20)
    ws = await workspace_service.get_or_create_workspace(db, "u", "medium", capacity_gb=50)
    assert ws is row
    assert ws.capacity_gb == 50
    assert db.commits == 1


async def test_grow_clamped_by_quota_does_not_grow():
    db = FakeDB()
    _seed(db, 20)
    # Requested 50 exceeds the user's quota cap 30 → do not grow (stay at stored).
    ws = await workspace_service.get_or_create_workspace(db, "u", "medium", capacity_gb=50, max_capacity_gb=30)
    assert ws.capacity_gb == 20
    assert db.commits == 0


async def test_never_shrinks_on_launch():
    db = FakeDB()
    _seed(db, 100)
    ws = await workspace_service.get_or_create_workspace(db, "u", "small", capacity_gb=20)
    assert ws.capacity_gb == 100
    assert db.commits == 0


async def test_equal_capacity_is_noop():
    db = FakeDB()
    _seed(db, 50)
    ws = await workspace_service.get_or_create_workspace(db, "u", "medium", capacity_gb=50)
    assert ws.capacity_gb == 50
    assert db.commits == 0


async def test_resize_workspace_up_only():
    import pytest

    db = FakeDB()
    _seed(db, 20)
    ws = await workspace_service.resize_workspace(db, "u", 60)
    assert ws.capacity_gb == 60
    assert db.commits == 1

    with pytest.raises(workspace_service.ShrinkNotAllowed):
        await workspace_service.resize_workspace(db, "u", 10)

    empty = FakeDB()
    with pytest.raises(workspace_service.WorkspaceNotFound):
        await workspace_service.resize_workspace(empty, "nobody", 60)
