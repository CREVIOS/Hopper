"""Terminate expired VM sessions and record the action exactly once."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import nats as nats_client
from app.core.database import async_session
from app.models.audit import AuditLog
from app.models.session import PodSession
from app.services.orchestrator_client import orchestrator_client

logger = logging.getLogger(__name__)
ACTIVE_STATES = ("pending", "creating", "running", "stopping")


async def reap_expired_sessions(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    terminate=None,
    publish=None,
) -> list[str]:
    """Terminate all expired active sessions and return their IDs.

    Rows are locked with ``SKIP LOCKED`` so multiple API workers can safely run
    the reaper. State is committed before external notifications; a repeated run
    therefore cannot terminate or audit the same session twice.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    terminate = terminate or orchestrator_client.terminate_pod

    result = await db.execute(
        select(PodSession)
        .where(
            PodSession.expires_at.is_not(None),
            PodSession.expires_at <= now,
            PodSession.state.in_(ACTIVE_STATES),
        )
        .with_for_update(skip_locked=True)
    )
    expired = list(result.scalars().all())
    reaped: list[str] = []

    for session in expired:
        try:
            await terminate(session.pod_name)
        except Exception as exc:
            # Kubernetes deletion is idempotent; a missing namespace/pod should
            # not keep an already-expired database session alive forever.
            if "not found" not in str(exc).lower() and "already deleted" not in str(exc).lower():
                logger.exception("Could not terminate expired pod %s", session.pod_name)
                continue

        session.state = "terminated"
        session.updated_at = now
        db.add(
            AuditLog(
                id=str(uuid4()),
                user_id=session.user_id,
                action="session.reaped",
                resource_type="pod_session",
                resource_id=session.id,
                ip_address="system",
                status_code=200,
                metadata_={"reason": "expired", "pod_name": session.pod_name},
            )
        )
        reaped.append(session.id)

    if reaped:
        await db.commit()
        for pod_id in reaped:
            payload = json.dumps({"pod_id": pod_id, "reason": "expired"}).encode()
            if publish is not None:
                await publish("session.reaped", payload)
            else:
                try:
                    await nats_client.get_nc().publish("session.reaped", payload)
                except RuntimeError:
                    logger.warning("NATS unavailable while publishing session.reaped for %s", pod_id)
    return reaped


async def run_session_reaper(stop: asyncio.Event, interval_seconds: int = 30) -> None:
    """Run the reaper until ``stop`` is set."""
    while not stop.is_set():
        try:
            async with async_session() as db:
                await reap_expired_sessions(db)
        except Exception:
            logger.exception("Session reaper iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass


# --------------------------------------------------------------------------- #
# Orphan VM reconciliation
#
# The database is the source of truth for whether a VM is alive. But a k8s VM
# pod can outlive its session: a terminate whose orchestrator call silently
# no-ops (the manager keys pods by name at create time but by UUID after a
# restart-time reconcile, so Get() misses and DeletePod is never reached), a
# gateway crash between the DB write and the gRPC call, or an old bug. Worse,
# the orchestrator's startup reconcile re-adopts every running VM pod and
# restarts its billing ticker without consulting the DB — so a leaked pod is
# resurrected as "live" on the next restart and never dies.
#
# This reconciler closes the loop: it lists the real VM pods and tears down any
# whose session is no longer active, keeping cluster reality in sync with the
# DB regardless of how a pod leaked. Deletion is done directly against k8s
# (pod + SSH service + workspace PVC) so it does not depend on the
# orchestrator's in-memory state being correct.
# --------------------------------------------------------------------------- #

VM_NAMESPACE = "hopper"
VM_LABEL = "app=hopper-vm"
POD_ID_LABEL = "hopper.dev/pod-id"
# Don't reap a pod younger than this — a just-created pod can briefly exist
# before its session row settles into an active state.
ORPHAN_MIN_AGE_SECONDS = 180


async def _kubectl(*args: str, timeout: float = 20.0) -> tuple[int, str, str]:
    """Run kubectl and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "kubectl", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", "kubectl timed out"
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


async def _list_vm_pods() -> list[tuple[str, str, str]]:
    """Return [(pod_name, session_id, creation_timestamp)] for all VM pods."""
    rc, out, err = await _kubectl(
        "get", "pods", "-n", VM_NAMESPACE, "-l", VM_LABEL,
        "-o", (
            "jsonpath={range .items[*]}{.metadata.name}{'\\t'}"
            "{.metadata.labels." + POD_ID_LABEL.replace(".", "\\.") + "}{'\\t'}"
            "{.metadata.creationTimestamp}{'\\n'}{end}"
        ),
    )
    if rc != 0:
        logger.warning("orphan reaper: kubectl list failed: %s", err.strip())
        return []
    rows: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        name = parts[0]
        sid = parts[1] if len(parts) > 1 else ""
        ts = parts[2] if len(parts) > 2 else ""
        rows.append((name, sid, ts))
    return rows


async def _delete_vm_pod(pod_name: str) -> None:
    """Tear down a VM pod and its dependent SSH service + workspace PVC."""
    await _kubectl("delete", "pod", pod_name, "-n", VM_NAMESPACE,
                   "--ignore-not-found", "--grace-period=5")
    await _kubectl("delete", "svc", f"ssh-{pod_name}", "-n", VM_NAMESPACE,
                   "--ignore-not-found")
    await _kubectl("delete", "pvc", f"ws-{pod_name}", "-n", VM_NAMESPACE,
                   "--ignore-not-found")


def _pod_age_seconds(creation_ts: str, now: datetime) -> float:
    if not creation_ts:
        return float("inf")  # unknown age — treat as old (eligible)
    try:
        created = datetime.fromisoformat(creation_ts.replace("Z", "+00:00"))
        return (now - created).total_seconds()
    except ValueError:
        return float("inf")


async def reap_orphan_vm_pods(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    list_pods=None,
    delete=None,
) -> list[str]:
    """Delete VM pods whose session is no longer active. Returns reaped names."""
    now = now or datetime.now(timezone.utc)
    list_pods = list_pods or _list_vm_pods
    delete = delete or _delete_vm_pod

    pods = await list_pods()
    if not pods:
        return []

    ids = [sid for _, sid, _ in pods if sid]
    active_ids: set[str] = set()
    if ids:
        result = await db.execute(
            select(PodSession.id).where(
                PodSession.id.in_(ids),
                PodSession.state.in_(ACTIVE_STATES),
            )
        )
        active_ids = set(result.scalars().all())

    reaped: list[str] = []
    for pod_name, sid, ts in pods:
        # Keep pods backing an active session; skip label-less pods we can't
        # attribute; give brand-new pods a grace window.
        if sid and sid in active_ids:
            continue
        if not sid:
            continue
        if _pod_age_seconds(ts, now) < ORPHAN_MIN_AGE_SECONDS:
            continue
        try:
            await delete(pod_name)
            reaped.append(pod_name)
        except Exception:
            logger.exception("orphan reaper: failed to delete %s", pod_name)

    if reaped:
        logger.warning("orphan reaper: tore down %d leaked VM pods: %s", len(reaped), reaped)
    return reaped


async def run_orphan_reaper(stop: asyncio.Event, interval_seconds: int = 300) -> None:
    """Periodically reconcile k8s VM pods against DB session state."""
    while not stop.is_set():
        try:
            async with async_session() as db:
                await reap_orphan_vm_pods(db)
        except Exception:
            logger.exception("Orphan reaper iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
