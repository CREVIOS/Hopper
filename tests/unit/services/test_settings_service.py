from app.models.user_setting import UserSetting
from app.services import settings_service


class FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class FakeDB:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.commits = 0

    async def execute(self, stmt):
        return FakeResult(self.existing)

    def add(self, obj):
        self.added.append(obj)
        self.existing = obj

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass


async def test_set_vscode_settings_creates_row_when_absent():
    db = FakeDB(existing=None)

    row = await settings_service.set_vscode_settings(db, "user-1", {"a": 1})

    assert isinstance(row, UserSetting)
    assert row.user_id == "user-1"
    assert row.vscode == {"a": 1}
    assert db.commits == 1
    assert len(db.added) == 1


async def test_set_vscode_settings_updates_existing_row():
    existing = UserSetting(id="s1", user_id="user-1", vscode={"old": True})
    db = FakeDB(existing=existing)

    row = await settings_service.set_vscode_settings(db, "user-1", {"new": True})

    assert row is existing
    assert row.vscode == {"new": True}
    assert db.commits == 1
    assert db.added == []  # updated in place, not inserted


async def test_get_user_settings_returns_none_when_absent():
    db = FakeDB(existing=None)
    assert await settings_service.get_user_settings(db, "user-1") is None
