"""Background CPU/RAM admission scheduler.

The gateway runs multiple uvicorn workers, each executing the app lifespan, so
a naive periodic loop would run N times. Leadership is therefore elected via a
single-row lease table (scheduler_leader): exactly one worker holds the lease
at a time and only that worker admits queued VMs.

The leader runs an FCFS admission pass every ``HOPPER_SCHEDULER_TICK_SECONDS``
and immediately whenever a pod stops (a ``pod.stopped`` NATS nudge sets
``NUDGE``). Admission is head-of-line: if the oldest queued entry does not fit
the free capacity, the pass stops without backfilling smaller entries behind it
(a documented v2 limitation -- fair FCFS is preferred over throughput here).

Capacity is computed gateway-side from the orchestrator's ListNodes plus the
scheduling requests of live PodSessions, minus a configurable system reserve
(see app.services.vm_capacity). If the orchestrator is unreachable the pass is
skipped (fail-open): queued entries simply wait for the next tick.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.session import PodSession
from app.models.ssh_key import SSHKey
from app.models.user_workspace import UserWorkspace
from app.models.vm_plan import VmPlanRow
from app.models.vm_queue_entry import VmQueueEntry
from app.services import plan_service, quota_service, vm_capacity, workspace_service
from app.services.orchestrator_client import OrchestratorClient

logger = logging.getLogger(__name__)


# Primary key of the single lease row seeded by the migration.
_LEADER_ID = "vm-scheduler"
# PodSession states that hold real cluster capacity right now.
_LIVE_VM_STATES = ("pending", "creating", "running")
# Namespace the router uses for every VM; mirrored here for parity.
_NAMESPACE = "hopper"

# Cluster-wide advisory lock for admission. Every capacity reservation (the sync
# POST fast-path AND the loop) serializes on it, so two admitters can never both
# consume the last slot (TOCTOU over-admit). It is a pg_advisory_XACT_lock, held
# only for the short reservation transaction -- never across an orchestrator gRPC
# call. Fixed arbitrary key.
_ADMISSION_LOCK_KEY = 0x484F5050_45525F31

# The per-user concurrent-VM cap the router enforces (429). The admission loop
# MUST honor it too, or the queue would silently circumvent it.
MAX_CONCURRENT_VMS_PER_USER = 3

# An entry claimed ('admitting') but never materialized within this window is
# assumed to have crashed mid-admit; the reaper requeues it so it never wedges.
_ADMITTING_TIMEOUT_S = 120

# Process-local wake-up signal. The pod-stopped consumer sets it so the loop
# reacts to freed capacity without waiting for the next tick. Every worker has
# its own NUDGE; only the leader's loop acts on it.
NUDGE = asyncio.Event()


def nudge() -> None:
    """Wake the local admission loop for one immediate pass."""
    NUDGE.set()


@dataclass(frozen=True)
class _LiveVm:
    """Minimal view of a live VM for capacity math (satisfies vm_capacity's
    _VmLike protocol: .cpu/.memory are the plan limits, .disk the workspace
    size resolved from the plan)."""

    cpu: str
    memory: str
    disk: str = "0"


def _storage_reserves() -> tuple[int, int]:
    """(total, reserve) storage pool in bytes from settings."""
    total = vm_capacity.parse_mem_bytes(settings.cluster_storage_total)
    reserve = vm_capacity.parse_mem_bytes(settings.cluster_reserve_storage)
    return total, reserve


async def _plan_workspace_gb(db: AsyncSession) -> dict[str, int]:
    """plan name -> workspace_gb, from the DB plan catalogue (the real PVC size,
    not the legacy VM_PLAN_RESOURCES 'disk' hint)."""
    rows = await db.execute(select(VmPlanRow.name, VmPlanRow.workspace_gb))
    return {name: gb for name, gb in rows.all()}


async def _workspace_capacity_gb(db: AsyncSession, user_id: str) -> int | None:
    """The user's current workspace capacity in GiB, or None if they have no
    workspace PVC yet (so a first launch is charged the full plan size)."""
    return await db.scalar(
        select(UserWorkspace.capacity_gb).where(UserWorkspace.user_id == user_id)
    )


async def acquire_or_renew_leadership(
    db: AsyncSession, instance_id: str, ttl_s: int
) -> bool:
    """Atomically take or renew the scheduler lease. Returns True if we hold it.

    A single conditional UPDATE is pooler-safe (no session-scoped advisory lock
    that a transaction pooler could hand to another backend): we win only if the
    lease is free (holder NULL), expired, or already ours, and we always push
    ``expires_at`` forward with the server clock so clock skew between workers
    never matters. The row is defensively seeded so a missing seed row can never
    starve the scheduler.
    """
    await db.execute(
        text(
            "INSERT INTO scheduler_leader (id, holder, expires_at) "
            "VALUES (:id, NULL, NULL) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": _LEADER_ID},
    )
    result = await db.execute(
        text(
            "UPDATE scheduler_leader "
            # make_interval positional args: secs is the 7th, avoiding named-arg
            # syntax that varies across Postgres versions.
            "SET holder = :me, "
            "    expires_at = now() + make_interval(0, 0, 0, 0, 0, 0, :ttl) "
            "WHERE id = :id "
            "  AND (holder IS NULL OR expires_at < now() OR holder = :me) "
            "RETURNING holder"
        ),
        {"me": instance_id, "ttl": ttl_s, "id": _LEADER_ID},
    )
    row = result.first()
    await db.commit()
    return row is not None


async def release_leadership(db: AsyncSession, instance_id: str) -> None:
    """Release the lease if we still hold it, so failover is immediate."""
    await db.execute(
        text(
            "UPDATE scheduler_leader SET holder = NULL, expires_at = NULL "
            "WHERE id = :id AND holder = :me"
        ),
        {"id": _LEADER_ID, "me": instance_id},
    )
    await db.commit()


async def fetch_nodes(orch: OrchestratorClient):
    """List schedulable node capacity via the orchestrator (gRPC). Returns None on
    any failure -- the fail-open signal so admission never blocks when the
    orchestrator is unreachable. Deliberately called OUTSIDE the admission lock."""
    try:
        return await orch.list_nodes()
    except Exception as exc:
        logger.warning("ListNodes failed (fail-open): %s", exc)
        return None


async def _free_from_nodes(db: AsyncSession, nodes) -> vm_capacity.Capacity:
    """Free capacity = pre-fetched node allocatable minus the scheduling requests
    of every live PodSession minus the configured reserve. Call while holding the
    admission lock so the live-VM sum is consistent with the reservation about to
    be written."""
    live = (
        await db.execute(
            select(PodSession.user_id, PodSession.cpu, PodSession.memory, PodSession.plan).where(
                PodSession.state.in_(_LIVE_VM_STATES)
            )
        )
    ).all()
    live_vms = [_LiveVm(cpu=cpu, memory=memory) for _uid, cpu, memory, _plan in live]

    # Real workspace-storage demand: every provisioned PVC (survives a stop) plus
    # the marginal size for live users whose plan outgrew — or who don't yet have
    # — a PVC. This replaces the old "live VMs × legacy plan disk", which ignored
    # stopped VMs' PVCs and undercounted the true size.
    plan_gb = await _plan_workspace_gb(db)
    ws_rows = (
        await db.execute(select(UserWorkspace.user_id, UserWorkspace.capacity_gb))
    ).all()
    live_user_plan_gb = [(uid, plan_gb.get(plan, 0)) for uid, _cpu, _mem, plan in live]
    used_storage_b = vm_capacity.aggregate_workspace_demand_b(ws_rows, live_user_plan_gb)

    reserve_cpu_m = vm_capacity.parse_cpu_millis(settings.cluster_reserve_cpu)
    reserve_mem_b = vm_capacity.parse_mem_bytes(settings.cluster_reserve_memory)
    total_storage_b, reserve_storage_b = _storage_reserves()
    return vm_capacity.compute_capacity(
        nodes, live_vms, reserve_cpu_m, reserve_mem_b,
        total_storage_b=total_storage_b, reserve_storage_b=reserve_storage_b,
        used_storage_b=used_storage_b,
    )


async def current_capacity(
    db: AsyncSession, orch: OrchestratorClient
) -> vm_capacity.Capacity | None:
    """Best-effort free capacity for the availability readout (unlocked read).
    None if the orchestrator is down."""
    nodes = await fetch_nodes(orch)
    if nodes is None:
        return None
    return await _free_from_nodes(db, nodes)


async def _lock_admission(db: AsyncSession) -> None:
    """Take the cluster-wide admission lock for the current transaction."""
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADMISSION_LOCK_KEY})


async def _user_live_count(db: AsyncSession, user_id: str) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(PodSession).where(
                PodSession.user_id == user_id, PodSession.state.in_(_LIVE_VM_STATES)
            )
        )
        or 0
    )


async def _reserve_pod_session(
    db: AsyncSession, user_id: str, plan: str, image: str, cpu: str, memory: str,
    network_group: str | None = None,
) -> str:
    """Insert a PodSession(pending) that RESERVES capacity (it is immediately
    counted by _free_from_nodes). Returns its pod_id. Must run inside the
    admission-locked txn so the reservation is atomic with the capacity read."""
    pod_id = str(uuid.uuid4())
    db.add(
        PodSession(
            id=pod_id, user_id=user_id, plan=plan, image=image, cpu=cpu, memory=memory,
            namespace=_NAMESPACE, pod_name=f"vm-{pod_id[:8]}", state="pending",
            network_group=network_group,
            # Stamp the session TTL now so both the sync fast-path and queued
            # (overflow) VMs are reaped like any other launch; a reserved row
            # would otherwise have no expiry (FR-HC-27).
            expires_at=datetime.utcnow() + timedelta(hours=settings.session_ttl_hours),
        )
    )
    await db.flush()
    return pod_id


async def reserve_sync_slot(
    db: AsyncSession, nodes, user_id: str, plan: str, image: str, cpu: str, memory: str,
    network_group: str | None = None,
) -> str | None:
    """POST /pods/ fast-path: under the admission lock, reserve a slot IFF the
    queue is empty AND the plan fits AND the user is under cap. Returns the
    reserved pod_id (caller then creates the pod) or None (caller enqueues).
    ``nodes`` is pre-fetched so no gRPC runs under the lock."""
    await _lock_admission(db)
    queued = int(
        await db.scalar(
            select(func.count()).select_from(VmQueueEntry).where(
                VmQueueEntry.state.in_(("queued", "admitting"))
            )
        )
        or 0
    )
    if queued > 0:  # never jump ahead of anyone already waiting (FCFS)
        await db.rollback()
        return None
    cap = await _free_from_nodes(db, nodes)
    plan_gb = (await _plan_workspace_gb(db)).get(plan, 0)
    req_storage_b = vm_capacity.marginal_workspace_demand_b(
        plan_gb, await _workspace_capacity_gb(db, user_id)
    )
    if not vm_capacity.plan_fits(cap, cpu, memory) or req_storage_b > cap.free_storage_b():
        await db.rollback()
        return None
    if await _user_live_count(db, user_id) >= MAX_CONCURRENT_VMS_PER_USER:
        await db.rollback()
        return None
    pod_id = await _reserve_pod_session(
        db, user_id, plan, image, cpu, memory, network_group=network_group
    )
    await db.commit()  # releases the advisory lock; persists the reservation
    return pod_id


async def _requeue_stuck_admitting(db: AsyncSession, orch: OrchestratorClient) -> int:
    """Recover entries claimed ('admitting') but never materialized (a crash
    between reservation and pod creation): if the reserved pod never became real,
    drop the reservation and requeue; if it did, finalize 'active'. Prevents a
    permanent wedge. (A crash in the ~ms between create_pod returning and the
    session update can still orphan one pod -- documented v2 limitation, since
    HEAD pod names are non-deterministic.)"""
    rows = (
        await db.execute(
            text(
                "SELECT e.id, e.pod_session_id, s.pod_name FROM vm_queue_entries e "
                "LEFT JOIN pod_sessions s ON s.id = e.pod_session_id "
                "WHERE e.state = 'admitting' "
                "  AND e.admitted_at < now() - make_interval(0,0,0,0,0,0,:t)"
            ),
            {"t": _ADMITTING_TIMEOUT_S},
        )
    ).all()
    recovered = 0
    for entry_id, pod_session_id, pod_name in rows:
        live = False
        if pod_name:
            try:
                status = await orch.get_pod_status(pod_name)
                live = bool(getattr(status, "exists", False))
            except Exception:
                live = False
        if live:
            await db.execute(
                text("UPDATE vm_queue_entries SET state='active' WHERE id=:id AND state='admitting'"),
                {"id": entry_id},
            )
        else:
            # Clear the entry's FK reference BEFORE deleting the orphan session,
            # or the DELETE violates vm_queue_entries_pod_session_id_fkey.
            await db.execute(
                text(
                    "UPDATE vm_queue_entries SET state='queued', pod_session_id=NULL, "
                    "admitted_at=NULL WHERE id=:id AND state='admitting'"
                ),
                {"id": entry_id},
            )
            if pod_session_id:
                await db.execute(
                    text("DELETE FROM pod_sessions WHERE id=:sid AND state='pending'"),
                    {"sid": pod_session_id},
                )
        recovered += 1
    # Close the read txn with a commit (not a rollback: rollback expires every
    # ORM object in a shared session, which would break callers holding entries).
    # A commit with no changes is a harmless no-op.
    await db.commit()
    return recovered


async def reconcile_pass(db: AsyncSession, orch: OrchestratorClient) -> dict:
    """Admit head-of-line queued entries FCFS while capacity allows.

    The reservation phase (capacity read + atomic entry claim + PodSession insert)
    runs under the cluster-wide admission lock in one short txn, so no two
    admitters -- another worker's loop, or a racing sync POST -- can consume the
    same slot or double-admit an entry. The slow create_pod gRPC calls run AFTER
    the lock is released, against the already-reserved sessions. A too-big front
    entry stops the pass (head-of-line, no backfill); a user at their cap is
    skipped without blocking the line.
    """
    await _requeue_stuck_admitting(db, orch)

    nodes = await fetch_nodes(orch)
    if nodes is None:
        return {"admitted": 0, "capacity": False}

    # ---- Phase 1: reserve fitting entries under the admission lock ----
    await _lock_admission(db)
    cap = await _free_from_nodes(db, nodes)
    free_cpu_m, free_mem_b = cap.free_cpu_m(), cap.free_mem_b()
    free_storage_b = cap.free_storage_b()
    entries = (
        await db.execute(
            select(VmQueueEntry).where(VmQueueEntry.state == "queued").order_by(VmQueueEntry.seq.asc())
        )
    ).scalars().all()

    # Plan sizes + each queued user's existing PVC capacity, fetched once so the
    # per-entry storage demand is the MARGINAL size (0 for a relaunch whose PVC
    # already exists), consistent with _free_from_nodes' aggregate accounting.
    plan_gb = await _plan_workspace_gb(db)
    ws_caps = {
        uid: cap
        for uid, cap in (
            await db.execute(select(UserWorkspace.user_id, UserWorkspace.capacity_gb))
        ).all()
    }

    # (entry_id, pod_id, user_id, plan, image, cpu, memory, network_group)
    # captured BEFORE commit so Phase 2 never touches a possibly-expired ORM object.
    reserved: list[tuple] = []
    user_counts: dict[str, int] = {}
    for entry in entries:
        req_cpu_m = vm_capacity.cpu_request_millis(entry.cpu)
        req_mem_b = vm_capacity.mem_request_bytes(entry.memory)
        req_storage_b = vm_capacity.marginal_workspace_demand_b(
            plan_gb.get(entry.plan, 0), ws_caps.get(entry.user_id)
        )
        if req_cpu_m > free_cpu_m or req_mem_b > free_mem_b or req_storage_b > free_storage_b:
            break  # head-of-line: a too-big front entry stops the pass
        count = user_counts.get(entry.user_id)
        if count is None:
            count = await _user_live_count(db, entry.user_id)
        if count >= MAX_CONCURRENT_VMS_PER_USER:
            continue  # user at cap: skip without blocking the line
        claimed = (
            await db.execute(
                text(
                    "UPDATE vm_queue_entries SET state='admitting', admitted_at=now() "
                    "WHERE id=:id AND state='queued' RETURNING id"
                ),
                {"id": entry.id},
            )
        ).first()
        if claimed is None:
            continue  # cancelled or claimed by another admitter since the select
        pod_id = await _reserve_pod_session(
            db, entry.user_id, entry.plan, entry.image, entry.cpu, entry.memory,
            network_group=entry.network_group,
        )
        await db.execute(
            text("UPDATE vm_queue_entries SET pod_session_id=:pid WHERE id=:id"),
            {"pid": pod_id, "id": entry.id},
        )
        reserved.append(
            (entry.id, pod_id, entry.user_id, entry.plan, entry.image, entry.cpu,
             entry.memory, entry.network_group)
        )
        free_cpu_m -= req_cpu_m
        free_mem_b -= req_mem_b
        free_storage_b -= req_storage_b
        user_counts[entry.user_id] = count + 1

    await db.commit()  # releases the lock; persists every reservation

    # ---- Phase 2: materialize each reservation (gRPC, unlocked) ----
    admitted = 0
    for entry_id, pod_id, user_id, plan, image, cpu, memory, network_group in reserved:
        try:
            # Bill at the plan's current DB rate — same as the synchronous launch
            # path (pods._provision_pod) — so admin pricing changes reach queued
            # VMs too. If the plan row has since vanished, 0.0 lets the
            # orchestrator fall back to its built-in map rather than block admission.
            plan_row = await plan_service.get_plan(db, plan)
            # Queue-admitted VMs get the SAME persistent workspace + SSH keys the
            # synchronous launch path gives (pods._provision_pod). Without this a
            # VM that waited in the queue came up with no /workspace and no keys.
            keys = list(
                (await db.execute(select(SSHKey.public_key).where(SSHKey.user_id == user_id)))
                .scalars().all()
            )
            quota = await quota_service.get_effective_quota(db, user_id)
            ws = await workspace_service.get_or_create_workspace(
                db, user_id, plan,
                capacity_gb=plan_row.workspace_gb if plan_row else None,
                max_capacity_gb=quota["max_workspace_gb"],
            )
            resp = await orch.create_pod(
                user_id=user_id, plan=plan, image=image, cpu=cpu, memory=memory,
                pod_id=pod_id,
                workspace_pvc_name=ws.pvc_name,
                workspace_capacity_gb=ws.capacity_gb,
                storage_class=ws.storage_class or "",
                authorized_keys=keys,
                credits_per_hour=float(plan_row.credits_per_hour) if plan_row else 0.0,
                network_group=network_group or "",
            )
        except Exception as exc:
            logger.error("Admission create_pod failed entry=%s: %s", entry_id, exc)
            await db.execute(
                text("UPDATE pod_sessions SET state='failed' WHERE id=:id"), {"id": pod_id}
            )
            await db.execute(
                text(
                    "UPDATE vm_queue_entries SET state='failed', last_error=:e WHERE id=:id"
                ),
                {"e": str(exc)[:500], "id": entry_id},
            )
            await db.commit()
            continue
        await db.execute(
            text(
                "UPDATE pod_sessions SET state=:st, pod_name=:pn, ssh_port=:sp, "
                "vscode_port=:vp, ssh_password=:pw WHERE id=:id"
            ),
            {
                "st": resp.state, "pn": resp.id, "sp": resp.ssh_port or None,
                "vp": resp.vscode_port or None, "pw": resp.ssh_password or None, "id": pod_id,
            },
        )
        await db.execute(
            text("UPDATE vm_queue_entries SET state='active' WHERE id=:id"), {"id": entry_id}
        )
        await db.commit()
        admitted += 1

    return {"admitted": admitted, "queued": len(entries), "capacity": True}


def _lease_ttl_seconds(tick_s: int) -> int:
    """Lease TTL comfortably longer than one tick so a busy pass never lets the
    lease lapse and hand leadership to another worker mid-flight."""
    return max(tick_s * 3, tick_s + 5)


async def run_scheduler_forever(
    session_factory: async_sessionmaker[AsyncSession], orch: OrchestratorClient
) -> None:
    """Leader-gated admission loop. Runs until cancelled; never dies on error.

    Each iteration: contend for leadership, run a pass if leader, then wait for
    either a NUDGE or the tick timeout. Any per-iteration exception is logged and
    swallowed so a transient DB/orchestrator blip cannot kill the only scheduler.
    Leadership is released on cancellation so a redeploy fails over instantly.
    """
    instance_id = str(uuid.uuid4())
    tick = settings.scheduler_tick_seconds
    ttl = _lease_ttl_seconds(tick)
    logger.info(
        "VM admission scheduler starting (instance=%s, tick=%ss)", instance_id, tick
    )
    try:
        while True:
            try:
                async with session_factory() as db:
                    if await acquire_or_renew_leadership(db, instance_id, ttl):
                        summary = await reconcile_pass(db, orch)
                        if summary.get("admitted"):
                            logger.info(
                                "VM scheduler admitted %d queued VM(s)",
                                summary["admitted"],
                            )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("VM scheduler pass failed; continuing")

            try:
                await asyncio.wait_for(NUDGE.wait(), timeout=tick)
            except asyncio.TimeoutError:
                pass
            finally:
                NUDGE.clear()
    except asyncio.CancelledError:
        logger.info("VM admission scheduler cancelled; releasing leadership")
        try:
            async with session_factory() as db:
                await release_leadership(db, instance_id)
        except Exception:
            logger.warning(
                "Failed to release scheduler leadership on shutdown", exc_info=True
            )
        raise
