from app.config import settings
from app.models.user_quota import UserQuota
from app.services import quota_service


class _Result:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class FakeDB:
    def __init__(self, row):
        self._row = row

    async def execute(self, stmt):
        return _Result(self._row)


async def test_effective_quota_falls_back_to_config_defaults():
    q = await quota_service.get_effective_quota(FakeDB(None), "u1")
    assert q == {
        "max_concurrent_vms": settings.default_max_concurrent_vms,
        "max_workspace_gb": settings.default_max_workspace_gb,
        "is_custom": False,
    }


async def test_effective_quota_uses_override_row():
    row = UserQuota(user_id="u1", max_concurrent_vms=10, max_workspace_gb=500)
    q = await quota_service.get_effective_quota(FakeDB(row), "u1")
    assert q == {"max_concurrent_vms": 10, "max_workspace_gb": 500, "is_custom": True}
