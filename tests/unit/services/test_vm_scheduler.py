from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services import vm_scheduler


class ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class ExecuteResult:
    def __init__(self, rows=None, first_value=None, scalar=None):
        self._rows = rows
        self._first_value = first_value
        self._scalar = scalar

    def first(self):
        return self._first_value

    def scalars(self):
        return ScalarResult(self._rows)

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, execute_results=None, scalar_results=None):
        self.execute_results = list(execute_results or [])
        self.scalar_results = list(scalar_results or [])
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self.executed = []

    async def execute(self, stmt, params=None):
        self.executed.append((stmt, params))
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        result = self.execute_results.pop(0)
        if callable(result):
            return result(stmt, params)
        return result

    async def scalar(self, stmt):
        if not self.scalar_results:
            raise AssertionError("unexpected scalar call")
        result = self.scalar_results.pop(0)
        return result(stmt) if callable(result) else result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def flush(self):
        self.flushes += 1


class FakeNode:
    def __init__(self, ready=True, cpu="4", mem="8Gi", name="node-1"):
        self.ready = ready
        self.cpu_allocatable = cpu
        self.memory_allocatable = mem
        self.name = name


def test_storage_reserves_reads_settings(monkeypatch):
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_storage_total", "100Gi")
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_reserve_storage", "10Gi")

    total, reserve = vm_scheduler._storage_reserves()

    assert total == 100 * 1024**3
    assert reserve == 10 * 1024**3


def test_storage_pool_falls_back_to_config_when_unmeasured(monkeypatch):
    # Longhorn absent → nodes carry no storage_capacity_bytes → configured pool.
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_storage_total", "150Gi")
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_storage_replica_factor", 2)

    assert vm_scheduler._storage_pool_b([FakeNode(True), FakeNode(False)]) == 150 * 1024**3


def test_storage_pool_prefers_measured_over_config(monkeypatch):
    # Measured capacity supersedes the config total; replica_factor=1 ⇒ full sum.
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_storage_total", "10Gi")
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_storage_replica_factor", 1)
    nodes = [
        SimpleNamespace(ready=True, storage_capacity_bytes=100 * 1024**3),
        SimpleNamespace(ready=True, storage_capacity_bytes=60 * 1024**3),
        # not-ready node's capacity is excluded from the pool.
        SimpleNamespace(ready=False, storage_capacity_bytes=999 * 1024**3),
    ]

    assert vm_scheduler._storage_pool_b(nodes) == 160 * 1024**3


def test_storage_pool_divides_measured_by_replica_factor(monkeypatch):
    # 2 replicas ⇒ half the raw capacity is usable logical space.
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_storage_replica_factor", 2)
    nodes = [
        SimpleNamespace(ready=True, storage_capacity_bytes=100 * 1024**3),
        SimpleNamespace(ready=True, storage_capacity_bytes=60 * 1024**3),
    ]

    assert vm_scheduler._storage_pool_b(nodes) == (160 * 1024**3) // 2


async def test_acquire_and_release_leadership():
    db = FakeDB(execute_results=[ExecuteResult(), ExecuteResult(first_value=("holder",))])

    assert await vm_scheduler.acquire_or_renew_leadership(db, "inst-1", 30) is True
    assert db.commits == 1

    db = FakeDB(execute_results=[ExecuteResult()])
    await vm_scheduler.release_leadership(db, "inst-1")
    assert db.commits == 1


async def test_fetch_nodes_returns_none_on_failure():
    class BrokenOrch:
        async def list_nodes(self):
            raise RuntimeError("down")

    assert await vm_scheduler.fetch_nodes(BrokenOrch()) is None


async def test_free_from_nodes_and_current_capacity(monkeypatch):
    # _free_from_nodes issues, in order: (1) live sessions (user_id,cpu,mem,plan),
    # (2) plan catalogue (name,workspace_gb), (3) all workspace rows (user_id,cap).
    live = [("u1", "1", "2Gi", "small"), ("u2", "2", "4Gi", "medium")]
    plans = [("small", 20), ("medium", 50), ("large", 100)]
    ws_rows = [("u1", 20), ("u3", 100)]  # u1 live+has PVC; u3 stopped but PVC persists
    db = FakeDB(execute_results=[
        ExecuteResult(rows=live), ExecuteResult(rows=plans), ExecuteResult(rows=ws_rows),
    ])
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_reserve_cpu", "500m")
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_reserve_memory", "1Gi")
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_storage_total", "500Gi")
    monkeypatch.setattr("app.services.vm_scheduler.settings.cluster_reserve_storage", "5Gi")

    capacity = await vm_scheduler._free_from_nodes(db, [FakeNode(True, "8", "16Gi"), FakeNode(False)])

    assert capacity.total_cpu_m == 8000
    assert capacity.used_cpu_m > 0
    # base = u1(20)+u3(100)=120; live deltas: u1 small(20)-20=0, u2 medium(50)-none=50
    # → 170 GiB. Counts u3's stopped PVC and u2's not-yet-provisioned workspace.
    assert capacity.used_storage_b == 170 * 1024**3

    async def fake_fetch_nodes(orch):
        return ["nodes"]

    async def fake_free(db, nodes):
        return "cap"

    monkeypatch.setattr(vm_scheduler, "fetch_nodes", fake_fetch_nodes)
    monkeypatch.setattr(vm_scheduler, "_free_from_nodes", fake_free)
    assert await vm_scheduler.current_capacity(FakeDB(), object()) == "cap"


async def test_user_live_count_and_reserve_pod_session():
    db = FakeDB(scalar_results=[2])
    assert await vm_scheduler._user_live_count(db, "user-1") == 2

    db = FakeDB()
    pod_id = await vm_scheduler._reserve_pod_session(
        db, "user-1", "small", "img", "1", "2Gi", network_group="team1"
    )

    assert pod_id
    assert db.flushes == 1
    assert db.added[0].network_group == "team1"


async def test_reserve_sync_slot_branches(monkeypatch):
    async def fake_lock(db):
        return None

    monkeypatch.setattr(vm_scheduler, "_lock_admission", fake_lock)
    async def fake_free_from_nodes(db, nodes):
        return SimpleNamespace(free_storage_b=lambda: 1 << 60)  # storage never the blocker here

    async def fake_plan_gb(db):
        return {"small": 20}

    async def fake_ws_cap(db, user_id):
        return None

    monkeypatch.setattr(vm_scheduler, "_free_from_nodes", fake_free_from_nodes)
    monkeypatch.setattr(vm_scheduler, "_plan_workspace_gb", fake_plan_gb)
    monkeypatch.setattr(vm_scheduler, "_workspace_capacity_gb", fake_ws_cap)
    monkeypatch.setattr("app.services.vm_scheduler.vm_capacity.plan_fits", lambda cap, cpu, mem: True)

    async def fake_user_live_count_zero(db, user_id):
        return 0

    async def fake_reserve_sync(*args, **kwargs):
        return "pod-1"

    monkeypatch.setattr(vm_scheduler, "_user_live_count", fake_user_live_count_zero)
    monkeypatch.setattr(vm_scheduler, "_reserve_pod_session", fake_reserve_sync)

    db = FakeDB(scalar_results=[1])
    assert await vm_scheduler.reserve_sync_slot(db, [FakeNode()], "user-1", "small", "img", "1", "2Gi") is None
    assert db.rollbacks == 1

    db = FakeDB(scalar_results=[0])
    monkeypatch.setattr("app.services.vm_scheduler.vm_capacity.plan_fits", lambda cap, cpu, mem: False)
    assert await vm_scheduler.reserve_sync_slot(db, [FakeNode()], "user-1", "small", "img", "1", "2Gi") is None
    assert db.rollbacks == 1

    db = FakeDB(scalar_results=[0])
    monkeypatch.setattr("app.services.vm_scheduler.vm_capacity.plan_fits", lambda cap, cpu, mem: True)
    async def fake_user_at_cap(db, user_id):
        return vm_scheduler.MAX_CONCURRENT_VMS_PER_USER

    monkeypatch.setattr(vm_scheduler, "_user_live_count", fake_user_at_cap)
    assert await vm_scheduler.reserve_sync_slot(db, [FakeNode()], "user-1", "small", "img", "1", "2Gi") is None
    assert db.rollbacks == 1

    async def fake_user_live_count(db, user_id):
        return 0

    async def fake_reserve(*args, **kwargs):
        return "pod-1"

    monkeypatch.setattr(vm_scheduler, "_user_live_count", fake_user_live_count)
    monkeypatch.setattr(vm_scheduler, "_reserve_pod_session", fake_reserve)
    db = FakeDB(scalar_results=[0])
    assert await vm_scheduler.reserve_sync_slot(db, [FakeNode()], "user-1", "small", "img", "1", "2Gi") == "pod-1"
    assert db.commits == 1


async def test_requeue_stuck_admitting_recovers_live_and_orphaned_entries():
    rows = [("entry-live", "pod-live", "k8s-live"), ("entry-dead", "pod-dead", "k8s-dead")]
    db = FakeDB(execute_results=[ExecuteResult(rows=rows), ExecuteResult(), ExecuteResult(), ExecuteResult(), ExecuteResult()])

    class Orch:
        async def get_pod_status(self, pod_name):
            return SimpleNamespace(exists=pod_name == "k8s-live")

    recovered = await vm_scheduler._requeue_stuck_admitting(db, Orch())

    assert recovered == 2
    assert db.commits == 1


async def test_reconcile_pass_handles_capacity_failures_and_materialization(monkeypatch):
    async def fake_requeue(db, orch):
        return 0

    monkeypatch.setattr(vm_scheduler, "_requeue_stuck_admitting", fake_requeue)
    async def fake_fetch_none(orch):
        return None

    monkeypatch.setattr(vm_scheduler, "fetch_nodes", fake_fetch_none)
    assert await vm_scheduler.reconcile_pass(FakeDB(), object()) == {"admitted": 0, "capacity": False}

    entries = [
        SimpleNamespace(id="e1", user_id="user-1", plan="small", image="img", cpu="1", memory="2Gi", seq=1, network_group=None),
        SimpleNamespace(id="e2", user_id="user-2", plan="small", image="img", cpu="1", memory="2Gi", seq=2, network_group="team"),
    ]

    class Capacity:
        def free_cpu_m(self):
            return 10000

        def free_mem_b(self):
            return 10000 * 1024**3

        def free_storage_b(self):
            return 10000 * 1024**3

    async def fake_fetch_nodes(orch):
        return [FakeNode()]

    async def fake_lock(db):
        return None

    async def fake_backfill(db, orch):
        return 0

    async def fake_free_from_nodes(db, nodes):
        return Capacity()

    counts = {"user-1": 0, "user-2": 0}

    async def fake_user_count(db, user_id):
        return counts[user_id]

    reserved_ids = iter(["pod-1", "pod-2"])

    async def fake_reserve(db, user_id, plan, image, cpu, memory, network_group=None):
        return next(reserved_ids)

    def execute_result(stmt, params):
        sql = str(stmt)
        if "SELECT vm_queue_entries.id" in sql or "FROM vm_queue_entries" in sql and "ORDER BY" in sql:
            return ExecuteResult(rows=entries)
        if "RETURNING id" in sql:
            return ExecuteResult(first_value=("claimed",))
        if "ssh_keys" in sql:
            return ExecuteResult(rows=[])       # queue-admit fetches the user's SSH keys
        if "vm_plans" in sql:
            return ExecuteResult(rows=[("small", 20)])   # plan workspace sizes
        if "user_workspaces" in sql:
            return ExecuteResult(rows=[])                 # no existing PVCs
        return ExecuteResult()

    async def fake_get_plan(db, name):
        return SimpleNamespace(credits_per_hour=1.0, workspace_gb=20)

    async def fake_quota(db, user_id):
        return {"max_concurrent_vms": 3, "max_workspace_gb": 100}

    async def fake_workspace(db, user_id, plan, capacity_gb=None, max_capacity_gb=None):
        return SimpleNamespace(
            pvc_name=f"ws-user-{user_id}", capacity_gb=capacity_gb or 20, storage_class=""
        )

    monkeypatch.setattr(vm_scheduler, "fetch_nodes", fake_fetch_nodes)
    monkeypatch.setattr(vm_scheduler, "_lock_admission", fake_lock)
    monkeypatch.setattr(vm_scheduler, "_free_from_nodes", fake_free_from_nodes)
    monkeypatch.setattr(vm_scheduler, "_user_live_count", fake_user_count)
    monkeypatch.setattr(vm_scheduler, "_reserve_pod_session", fake_reserve)
    monkeypatch.setattr(vm_scheduler.plan_service, "get_plan", fake_get_plan)
    monkeypatch.setattr(vm_scheduler.quota_service, "get_effective_quota", fake_quota)
    monkeypatch.setattr(vm_scheduler.workspace_service, "get_or_create_workspace", fake_workspace)
    db = FakeDB(execute_results=[execute_result] * 20)

    class Orch:
        def __init__(self):
            self.calls = []

        async def create_pod(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["pod_id"] == "pod-2":
                raise RuntimeError("boom")
            return SimpleNamespace(state="running", id="vm-real", ssh_port=22, vscode_port=8080, ssh_password="pw")

    orch = Orch()
    summary = await vm_scheduler.reconcile_pass(db, orch)

    assert summary["queued"] == 2
    assert summary["admitted"] == 1
    assert db.commits >= 2
    # The plan's DB rate is forwarded on the queue-admission path too, not just
    # the synchronous launch — so queued VMs bill at admin-set pricing.
    assert orch.calls[0]["credits_per_hour"] == 1.0
    # Queue-admitted VMs also get their persistent workspace + SSH keys (the fix).
    assert orch.calls[0]["workspace_pvc_name"] == "ws-user-user-1"
    assert orch.calls[0]["workspace_capacity_gb"] == 20
    assert orch.calls[0]["storage_class"] == ""
    assert "authorized_keys" in orch.calls[0]


def test_lease_ttl_seconds_has_minimum_buffer():
    assert vm_scheduler._lease_ttl_seconds(30) == 90
    assert vm_scheduler._lease_ttl_seconds(1) == 6
