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
