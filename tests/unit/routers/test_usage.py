from datetime import datetime
from types import SimpleNamespace

from app.routers.usage import RANGE_MAP, get_my_usage_summary, get_pod_usage
from app.schemas.user import TokenPayload


class FakeUsageResult:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class FakeDB:
    def __init__(self, result=None, side_effects=None):
        self.result = result
        self.side_effects = list(side_effects or [])
        self.calls = []

    async def execute(self, stmt, params):
        self.calls.append(params)
        if self.side_effects:
            effect = self.side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect
        return self.result


def _payload() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="Test User",
        role="student",
        exp=1234567890,
    )


def test_range_map_contains_expected_presets():
    assert set(RANGE_MAP) == {"1h", "6h", "24h", "7d"}


async def test_get_pod_usage_formats_rows():
    db = FakeDB(
        result=FakeUsageResult(
            rows=[
                SimpleNamespace(
                    bucket=datetime(2026, 1, 1, 12, 0, 0),
                    avg_cpu=50.5,
                    avg_memory=2048,
                    memory_limit=4096,
                )
            ]
        )
    )

    result = await get_pod_usage("pod-1", range="1h", current_user=_payload(), db=db)

    assert result["pod_id"] == "pod-1"
    assert result["range"] == "1h"
    assert result["data"][0]["cpu_percent"] == 50.5
    assert result["data"][0]["memory_limit_bytes"] == 4096


async def test_get_pod_usage_falls_back_when_primary_query_fails():
    fallback_result = FakeUsageResult(rows=[])
    db = FakeDB(side_effects=[Exception("no time_bucket"), fallback_result])

    result = await get_pod_usage("pod-1", range="7d", current_user=_payload(), db=db)

    assert result["range"] == "7d"
    assert len(db.calls) == 2


async def test_get_my_usage_summary_returns_zeroes_without_row():
    db = FakeDB(result=FakeUsageResult(row=None))

    result = await get_my_usage_summary(current_user=_payload(), db=db)

    assert result == {
        "pod_count": 0,
        "avg_cpu_percent": 0,
        "avg_memory_bytes": 0,
    }
