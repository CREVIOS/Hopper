import pytest

from app.schemas.user import TokenPayload
from app.services import vm_queue


def _payload() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="Test User",
        role="student",
        exp=1234567890,
    )


class FakeExecuteResult:
    def __init__(self, scalar):
        self._scalar = scalar

    def scalar_one(self):
        return self._scalar


class FakeDB:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])
        self.added = []
        self.commits = 0
        self.refreshed = []

    async def execute(self, stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return FakeExecuteResult(self.execute_results.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)
        obj.seq = 7


def test_resolve_plan_validates_enum():
    assert vm_queue._resolve_plan("small").value == "small"

    with pytest.raises(vm_queue.EnqueueError) as exc_info:
        vm_queue._resolve_plan("gpu-xl")

    assert exc_info.value.status_code == 422


def test_resolve_image_falls_back_to_default_template():
    assert vm_queue._resolve_image("java") == "hopper/vm-java:22.04"
    assert vm_queue._resolve_image("unknown") == vm_queue.VM_TEMPLATE_IMAGES[vm_queue.DEFAULT_TEMPLATE]


async def test_enqueue_vm_request_rejects_insufficient_credits(monkeypatch):
    async def fake_get_balance(db, user_id):
        return 0.0

    monkeypatch.setattr("app.services.vm_queue.get_balance", fake_get_balance)

    with pytest.raises(vm_queue.EnqueueError) as exc_info:
        await vm_queue.enqueue_vm_request(FakeDB(), _payload(), "small", "ubuntu")

    assert exc_info.value.status_code == 402
    assert "Insufficient credits" in exc_info.value.detail


async def test_enqueue_vm_request_persists_frozen_resources(monkeypatch):
    async def fake_get_balance(db, user_id):
        return 100.0

    monkeypatch.setattr("app.services.vm_queue.get_balance", fake_get_balance)
    db = FakeDB()

    entry = await vm_queue.enqueue_vm_request(db, _payload(), "medium", "python-ml", network_group="cse101")

    assert entry.plan == "medium"
    assert entry.image == "hopper/vm-python-ml:22.04"
    assert entry.cpu == "2"
    assert entry.memory == "4Gi"
    assert entry.network_group == "cse101"
    assert db.commits == 1
    assert db.refreshed == [entry]


async def test_queue_position_and_live_queue_count_return_ints():
    db = FakeDB(execute_results=[3, 5])
    entry = type("Entry", (), {"seq": 12})()

    assert await vm_queue.queue_position(db, entry) == 3
    assert await vm_queue.live_queue_count(db) == 5
