"""Live integration tests for the CPU/RAM admission queue against real Postgres.

Exercises the queue + scheduler service modules end to end on the local
Postgres at localhost:5433 (migrated to head 011):

  * app.services.vm_capacity  -- pure capacity math + plan_fits
  * app.services.vm_queue     -- enqueue / position / count
  * app.services.vm_scheduler -- current_capacity, admit, reconcile_pass,
                                 leader election

A FakeOrchestratorClient stands in for the gRPC orchestrator: list_nodes
returns configurable Ready nodes, create_pod echoes an id of "vm-<pod_id>",
terminate_pod is a no-op. No orchestrator process is required.

Each test starts from a clean slate: vm_queue_entries and pod_sessions are
truncated (seq identity reset to 1) and the scheduler_leader lease is cleared,
so FCFS seq/position assertions are deterministic.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import uuid

from app.config import settings
from app.models.session import PodSession
from app.schemas.pod import VM_PLAN_RESOURCES, VmPlan
from app.schemas.user import TokenPayload
from app.services import vm_capacity, vm_scheduler
from app.services.credit_service import add_credits
from app.services.orchestrator_client import NodeInfoResponse, PodStatusResponse
from app.services.vm_queue import (
    enqueue_vm_request,
    live_queue_count,
    queue_position,
)

# Live VM states counted against capacity (mirrors vm_scheduler._LIVE_VM_STATES).
_LIVE_VM_STATES = ("pending", "creating", "running")


# --------------------------------------------------------------------------- #
# Fakes and helpers
# --------------------------------------------------------------------------- #
@dataclass
class FakeOrchestratorClient:
    """Stand-in for OrchestratorClient used by the scheduler under test.

    * ``list_nodes`` returns the configured Ready/NotReady nodes, or raises when
      ``fail_list_nodes`` is set (simulating an unreachable orchestrator so the
      fail-open path can be exercised).
    * ``create_pod`` records the call and returns a PodStatusResponse whose id is
      "vm-<pod_id>", exactly as the real orchestrator names the K8s pod.
    * ``terminate_pod`` is a no-op that records the pod name.
    """

    nodes: list[NodeInfoResponse] = field(default_factory=list)
    fail_list_nodes: bool = False
    created: list[str] = field(default_factory=list)
    terminated: list[str] = field(default_factory=list)
    # pod_names get_pod_status should report as still live (for the reaper test).
    live_pods: set = field(default_factory=set)

    async def list_nodes(self) -> list[NodeInfoResponse]:
        if self.fail_list_nodes:
            raise RuntimeError("orchestrator unreachable")
        return list(self.nodes)

    async def get_pod_status(self, pod_name: str):
        from types import SimpleNamespace

        return SimpleNamespace(exists=pod_name in self.live_pods, state="running")

    async def create_pod(
        self,
        user_id: str,
        plan: str,
        image: str,
        cpu: str,
        memory: str,
        disk: str = "",
        pod_id: str = "",
    ) -> PodStatusResponse:
        self.created.append(pod_id)
        return PodStatusResponse(
            id=f"vm-{pod_id}",
            state="running",
            ssh_port=2222,
            vscode_port=8443,
            message="ok",
            ssh_password="s3cret",
        )

    async def terminate_pod(self, pod_id: str) -> bool:
        self.terminated.append(pod_id)
        return True


def _node(cpu_alloc: str, mem_alloc: str, *, ready: bool = True, name: str = "node-1") -> NodeInfoResponse:
    """A Ready (by default) node whose allocatable == capacity for simplicity."""
    return NodeInfoResponse(
        name=name,
        cpu_capacity=cpu_alloc,
        memory_capacity=mem_alloc,
        cpu_allocatable=cpu_alloc,
        memory_allocatable=mem_alloc,
        pod_count=0,
        ready=ready,
    )


def _token(sub: str) -> TokenPayload:
    return TokenPayload(
        sub=sub,
        email=f"{sub}@test.local",
        name=sub,
        role="student",
        exp=9_999_999_999,
        email_verified=True,
    )


async def _fund(db: AsyncSession, sub: str, credits: float = 100.0) -> None:
    """Give a user enough credit to clear the enqueue precheck."""
    await add_credits(db, sub, credits, description="test_seed")


def _small_cpu() -> str:
    return VM_PLAN_RESOURCES[VmPlan.SMALL]["cpu"]


def _small_mem() -> str:
    return VM_PLAN_RESOURCES[VmPlan.SMALL]["memory"]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(settings.database_url, poolclass=NullPool)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _clean(engine):
    """Reset queue/pod tables and the leader lease before every test."""
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE vm_queue_entries, pod_sessions RESTART IDENTITY CASCADE")
        )
        await conn.execute(
            text("UPDATE scheduler_leader SET holder = NULL, expires_at = NULL")
        )
    yield


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncSession:
    async with session_factory() as session:
        yield session


# --------------------------------------------------------------------------- #
# 1. Free capacity + empty queue: admissible immediately, queue stays empty
# --------------------------------------------------------------------------- #
async def test_free_capacity_empty_queue_is_admissible(db: AsyncSession) -> None:
    """Plenty of headroom + no queue -> plan fits and a reconcile pass is a
    no-op that leaves the queue empty (the router would create synchronously)."""
    orch = FakeOrchestratorClient(nodes=[_node("16", "64Gi")])

    cap = await vm_scheduler.current_capacity(db, orch)
    assert cap is not None
    assert vm_capacity.plan_fits(cap, _small_cpu(), _small_mem()) is True

    summary = await vm_scheduler.reconcile_pass(db, orch)
    assert summary["capacity"] is True
    assert summary["admitted"] == 0
    assert summary["queued"] == 0
    assert await live_queue_count(db) == 0


async def test_free_capacity_reconcile_admits_a_queued_entry(db: AsyncSession) -> None:
    """When capacity is free, an entry that lands in the queue is admitted on the
    next pass (proves reconcile drains rather than sitting idle)."""
    orch = FakeOrchestratorClient(nodes=[_node("16", "64Gi")])
    await _fund(db, "u-free")

    entry = await enqueue_vm_request(db, _token("u-free"), "small", "ubuntu")
    assert entry.state == "queued"

    summary = await vm_scheduler.reconcile_pass(db, orch)
    assert summary["admitted"] == 1

    await db.refresh(entry)
    assert entry.state == "active"
    assert await live_queue_count(db) == 0


# --------------------------------------------------------------------------- #
# 2. Exhausted capacity: plan does not fit, requests enqueue FCFS
# --------------------------------------------------------------------------- #
async def test_exhausted_capacity_enqueues_fcfs(db: AsyncSession) -> None:
    """A full cluster (free memory == 0 after reserve) does not fit a new VM, so
    requests enqueue; seq is gapless/monotonic and position is 1-based FCFS."""
    # Node memory 2Gi, default reserve 2Gi -> free memory 0 -> nothing fits.
    orch = FakeOrchestratorClient(nodes=[_node("8", "2Gi")])

    cap = await vm_scheduler.current_capacity(db, orch)
    assert cap is not None
    assert cap.free_mem_b() == 0
    assert vm_capacity.plan_fits(cap, _small_cpu(), _small_mem()) is False

    await _fund(db, "u-a")
    await _fund(db, "u-b")
    await _fund(db, "u-c")
    e1 = await enqueue_vm_request(db, _token("u-a"), "small", "ubuntu")
    e2 = await enqueue_vm_request(db, _token("u-b"), "small", "ubuntu")
    e3 = await enqueue_vm_request(db, _token("u-c"), "small", "ubuntu")

    # Gapless, monotonically increasing seq in insertion order.
    seqs = [e1.seq, e2.seq, e3.seq]
    assert seqs == list(range(seqs[0], seqs[0] + 3))

    # 1-based FCFS position.
    assert await queue_position(db, e1) == 1
    assert await queue_position(db, e2) == 2
    assert await queue_position(db, e3) == 3
    assert await live_queue_count(db) == 3

    # The cluster is full, so a pass admits nothing (head does not fit).
    summary = await vm_scheduler.reconcile_pass(db, orch)
    assert summary["admitted"] == 0


# --------------------------------------------------------------------------- #
# 3. Head-of-line: no backfill; a terminated VM frees the next admission
# --------------------------------------------------------------------------- #
async def test_head_of_line_blocks_without_backfill(db: AsyncSession) -> None:
    """A large entry that does not fit blocks the head; a small entry behind it
    is NOT backfilled even though it would fit the free capacity."""
    # Node 5Gi mem, reserve 2Gi -> free 3Gi: fits SMALL (2Gi) but not LARGE (8Gi).
    orch = FakeOrchestratorClient(nodes=[_node("8", "5Gi")])
    await _fund(db, "u-large")
    await _fund(db, "u-small")

    big = await enqueue_vm_request(db, _token("u-large"), "large", "ubuntu")
    small = await enqueue_vm_request(db, _token("u-small"), "small", "ubuntu")

    summary = await vm_scheduler.reconcile_pass(db, orch)
    assert summary["admitted"] == 0  # blocked at head, no backfill

    await db.refresh(big)
    await db.refresh(small)
    assert big.state == "queued"
    assert small.state == "queued"


async def test_terminated_vm_frees_capacity_for_next_entry(db: AsyncSession) -> None:
    """FCFS admits one at a time when capacity fits exactly one; terminating the
    admitted VM frees room so the next pass admits the following entry."""
    # Node 4Gi mem, reserve 2Gi -> free 2Gi: room for exactly one SMALL (2Gi).
    orch = FakeOrchestratorClient(nodes=[_node("8", "4Gi")])
    await _fund(db, "u-1")
    await _fund(db, "u-2")

    first = await enqueue_vm_request(db, _token("u-1"), "small", "ubuntu")
    second = await enqueue_vm_request(db, _token("u-2"), "small", "ubuntu")

    # Pass 1: only the head fits.
    summary1 = await vm_scheduler.reconcile_pass(db, orch)
    assert summary1["admitted"] == 1
    await db.refresh(first)
    await db.refresh(second)
    assert first.state == "active"
    assert second.state == "queued"

    # A no-op pass while still full admits nothing more.
    assert (await vm_scheduler.reconcile_pass(db, orch))["admitted"] == 0
    await db.refresh(second)
    assert second.state == "queued"

    # Terminate the admitted VM -> capacity frees.
    admitted_session = await db.get(PodSession, first.pod_session_id)
    assert admitted_session is not None
    admitted_session.state = "terminated"
    await db.commit()

    # Pass 2: the next entry now fits.
    summary2 = await vm_scheduler.reconcile_pass(db, orch)
    assert summary2["admitted"] == 1
    await db.refresh(second)
    assert second.state == "active"
    assert await live_queue_count(db) == 0


# --------------------------------------------------------------------------- #
# 4. Leader election: single winner, renew, no early steal, expiry failover
# --------------------------------------------------------------------------- #
async def test_leader_election_single_winner_and_renew(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Exactly one instance acquires the lease; it can renew; a second instance
    cannot steal it before the TTL expires."""
    async with session_factory() as db_a:
        assert await vm_scheduler.acquire_or_renew_leadership(db_a, "instance-A", 30) is True

    async with session_factory() as db_b:
        assert await vm_scheduler.acquire_or_renew_leadership(db_b, "instance-B", 30) is False

    # The holder renews successfully.
    async with session_factory() as db_a:
        assert await vm_scheduler.acquire_or_renew_leadership(db_a, "instance-A", 30) is True

    # The non-leader still cannot steal before TTL.
    async with session_factory() as db_b:
        assert await vm_scheduler.acquire_or_renew_leadership(db_b, "instance-B", 30) is False


async def test_leader_lease_expiry_allows_failover(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Once the lease TTL lapses, another instance takes over; an explicit
    release also hands leadership over immediately."""
    async with session_factory() as db_a:
        assert await vm_scheduler.acquire_or_renew_leadership(db_a, "instance-A", 1) is True

    await asyncio.sleep(1.3)  # let the 1s lease expire (server clock)

    async with session_factory() as db_b:
        assert await vm_scheduler.acquire_or_renew_leadership(db_b, "instance-B", 30) is True

    # B releases -> a fresh instance can acquire straight away.
    async with session_factory() as db_b:
        await vm_scheduler.release_leadership(db_b, "instance-B")
    async with session_factory() as db_c:
        assert await vm_scheduler.acquire_or_renew_leadership(db_c, "instance-C", 30) is True


# --------------------------------------------------------------------------- #
# 5. admit(): builds a PodSession named after the orchestrator id; entry active
# --------------------------------------------------------------------------- #
async def test_admit_builds_pod_session_and_marks_active(db: AsyncSession) -> None:
    """admit promotes a queued entry: it creates a PodSession whose pod_name is
    the orchestrator-returned id (vm-<...>) and flips the entry to 'active'."""
    orch = FakeOrchestratorClient(nodes=[_node("16", "64Gi")])
    await _fund(db, "u-admit")

    entry = await enqueue_vm_request(db, _token("u-admit"), "small", "ubuntu")
    summary = await vm_scheduler.reconcile_pass(db, orch)
    assert summary["admitted"] == 1

    await db.refresh(entry)
    assert entry.state == "active"
    assert entry.pod_session_id is not None

    session = await db.get(PodSession, entry.pod_session_id)
    assert session is not None
    # admit passes pod_id (== the new PodSession.id) to create_pod, and the fake
    # orchestrator returns id == "vm-<pod_id>"; pod_name must be that returned id.
    assert orch.created == [session.id]
    assert session.pod_name == f"vm-{session.id}"
    assert session.state in _LIVE_VM_STATES
    assert session.user_id == "u-admit"
    assert session.cpu == _small_cpu()
    assert session.memory == _small_mem()


# --------------------------------------------------------------------------- #
# Fail-open: orchestrator down -> capacity None, pass skipped (queue waits)
# --------------------------------------------------------------------------- #
async def test_orchestrator_down_fails_open(db: AsyncSession) -> None:
    """When ListNodes raises, current_capacity is None and reconcile_pass skips
    the pass (fail-open) instead of erroring; queued entries simply wait."""
    orch = FakeOrchestratorClient(fail_list_nodes=True)
    await _fund(db, "u-down")
    entry = await enqueue_vm_request(db, _token("u-down"), "small", "ubuntu")

    assert await vm_scheduler.current_capacity(db, orch) is None

    summary = await vm_scheduler.reconcile_pass(db, orch)
    assert summary["capacity"] is False
    assert summary["admitted"] == 0

    await db.refresh(entry)
    assert entry.state == "queued"


# --------------------------------------------------------------------------- #
# Concurrency-safety fixes (from the adversarial review)
# --------------------------------------------------------------------------- #
async def _running_vm(db: AsyncSession, user_id: str, plan: str = "small") -> str:
    """Insert a live (running) PodSession so it counts toward capacity + cap."""
    res = VM_PLAN_RESOURCES[VmPlan(plan)]
    pid = f"run-{uuid.uuid4().hex[:8]}"
    db.add(
        PodSession(
            id=pid, user_id=user_id, plan=plan, image="img", cpu=res["cpu"],
            memory=res["memory"], namespace="hopper", pod_name=f"vm-{pid}", state="running",
        )
    )
    await db.commit()
    return pid


async def test_loop_enforces_per_user_cap(db: AsyncSession) -> None:
    """The admission loop must honor the same 3-concurrent-VM-per-user cap the
    router enforces: a user already at 3 running VMs is skipped, and a different
    user's queued entry is admitted instead."""
    orch = FakeOrchestratorClient(nodes=[_node("64", "256Gi")])  # abundant capacity
    for _ in range(3):
        await _running_vm(db, "u-capped")
    await _fund(db, "u-capped")
    await _fund(db, "u-free")

    capped = await enqueue_vm_request(db, _token("u-capped"), "small", "ubuntu")
    freed = await enqueue_vm_request(db, _token("u-free"), "small", "ubuntu")

    summary = await vm_scheduler.reconcile_pass(db, orch)
    assert summary["admitted"] == 1
    await db.refresh(capped)
    await db.refresh(freed)
    assert capped.state == "queued", "user at their 3-VM cap must not be admitted"
    assert freed.state == "active", "a different user under cap should be admitted"


async def test_cancelled_entry_is_not_admitted(db: AsyncSession) -> None:
    """An atomic claim (WHERE state='queued') means a queued entry cancelled just
    before a pass is never resurrected/admitted."""
    orch = FakeOrchestratorClient(nodes=[_node("64", "256Gi")])
    await _fund(db, "u-cancel")
    entry = await enqueue_vm_request(db, _token("u-cancel"), "small", "ubuntu")
    # Cancel it (as DELETE /pods/queue/{id} would).
    await db.execute(
        text("UPDATE vm_queue_entries SET state='cancelled' WHERE id=:id"), {"id": entry.id}
    )
    await db.commit()

    summary = await vm_scheduler.reconcile_pass(db, orch)
    assert summary["admitted"] == 0
    await db.refresh(entry)
    assert entry.state == "cancelled"
    assert orch.created == [], "a cancelled entry must never create a pod"


async def test_stuck_admitting_entry_is_requeued(db: AsyncSession) -> None:
    """An entry stuck in 'admitting' past the timeout with no real pod is requeued
    (and its unstarted reservation dropped), so a crash mid-admit never wedges."""
    orch = FakeOrchestratorClient(nodes=[_node("64", "256Gi")])  # live_pods empty
    await _fund(db, "u-stuck")
    entry = await enqueue_vm_request(db, _token("u-stuck"), "small", "ubuntu")
    # Simulate a crashed admit: a pending reservation + an old 'admitting' claim.
    sid = await _running_vm(db, "u-stuck")
    await db.execute(text("UPDATE pod_sessions SET state='pending' WHERE id=:s"), {"s": sid})
    await db.execute(
        text(
            "UPDATE vm_queue_entries SET state='admitting', pod_session_id=:s, "
            "admitted_at = now() - interval '10 minutes' WHERE id=:id"
        ),
        {"s": sid, "id": entry.id},
    )
    await db.commit()

    await vm_scheduler.reconcile_pass(db, orch)
    await db.refresh(entry)
    # Recovered out of the wedged 'admitting' state (requeued, then re-admitted in
    # the same pass since capacity is abundant -- either outcome is correct).
    assert entry.state in ("queued", "active"), f"stuck entry not recovered: {entry.state}"
    # The unstarted (orphan) reservation was dropped either way.
    assert await db.get(PodSession, sid) is None
