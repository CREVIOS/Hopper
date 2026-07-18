"""Idle-detection agent — protect students from credit exhaustion.

An abandoned VM keeps burning credits while doing nothing. This agent watches
each running VM across several dimensions, warns the user, and (only if the VM
still looks abandoned after a grace period) terminates it.

Multi-dimensional idleness
--------------------------
A VM is "active" if ANY of these hold:
  * CPU usage >= ``idle_cpu_threshold_percent`` (read from the NATS metrics
    stream that the orchestrator already publishes on ``metrics.<pod>``);
  * an activity heartbeat arrived recently — the in-VM agent
    (images/hopper-vm) reports established SSH sessions, code-server
    websockets, and shell activity (``/tmp/active``) via
    ``POST /pods/{id}/heartbeat``.
A VM is "abandoned" when it has been continuously inactive for
``idle_cpu_window_seconds`` AND still holds credits (an already-zero balance is
left to the normal ``billing.exhausted`` path).

Warning & grace flow
--------------------
On abandonment we publish ``notification.idle_warning`` to NATS JetStream and
flip the row to ``warned``. The in-VM agent learns of the warning from its next
heartbeat response and broadcasts it to every terminal via ``wall``. If no
activity cancels it within ``idle_grace_seconds``, we call
``PodOrchestrator.TerminatePod``.

State & concurrency
-------------------
State lives in the ``pod_idle_state`` table (existing TimescaleDB — no new
external dependency) so it is correct across uvicorn workers and survives
restarts. Every transition is an atomic claim UPDATE guarded on the current
phase, so exactly one worker acts on a given VM even though several run the
scanner. No distributed locks required.

FAIL-SAFE
---------
Termination is refused unless we still have *fresh* metrics proving idleness
(``last_seen_at`` recent), NATS is connected, and the orchestrator call
succeeds. If the metrics feed or the NATS broker drops out, ``last_seen_at``
goes stale and no VM is ever killed — the default is always to keep student
workloads alive.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.core import nats as nats_client
from app.core.database import async_session
from app.models.audit import AuditLog
from app.models.idle_state import PodIdleState
from app.models.session import PodSession
from app.schemas.pod import VM_PLAN_RESOURCES, VmPlan
from app.services.credit_service import get_balance
from app.services.orchestrator_client import orchestrator_client

logger = logging.getLogger(__name__)

_NOTIFY_STREAM = "HOPPER_NOTIFICATIONS"
_notify_stream_ready = False

# Per-worker caches (advisory only; the DB row is authoritative).
_meta_cache: dict[str, dict] = {}          # metric id -> {pod_id, pod_name, plan, user_id}
_flush_at: dict[str, float] = {}           # pod_id -> last DB flush (monotonic)

_scanner_task: asyncio.Task | None = None


# --------------------------------------------------------------------------- #
# Per-pod heartbeat token — shared with the sandbox provisioner. Defined in
# app.services.pod_token (single source of truth) and re-exported here so
# existing callers (routers/pods.py) keep importing it from idle_agent.
# --------------------------------------------------------------------------- #
from app.services.pod_token import make_pod_token, verify_pod_token  # noqa: E402,F401


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _nats_connected() -> bool:
    return nats_client.nc is not None and nats_client.nc.is_connected


def _plan_rate(plan: str) -> float:
    try:
        return float(VM_PLAN_RESOURCES[VmPlan(plan)]["credits_per_hour"])
    except (KeyError, ValueError):
        return 1.0


def _warning_message(minutes: int) -> str:
    return (
        "⚠️  SYSTEM WARNING: This VM appears idle and will "
        f"auto-terminate in {minutes} minutes to save your credits.\n"
        "Type any command or run:  touch /tmp/active   to cancel."
    )


async def _resolve_pod(metric_id: str) -> dict | None:
    """Map a metric identifier (pod_name or UUID) to a running PodSession."""
    if metric_id in _meta_cache:
        return _meta_cache[metric_id]
    async with async_session() as db:
        row = (
            await db.execute(
                select(PodSession)
                .where(
                    or_(PodSession.pod_name == metric_id, PodSession.id == metric_id),
                    PodSession.state == "running",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
    if row is None:
        return None  # not cached: a pod may become running later
    meta = {
        "pod_id": row.id,
        "pod_name": row.pod_name,
        "plan": row.plan,
        "user_id": row.user_id,
    }
    _meta_cache[metric_id] = meta
    return meta


def _should_flush(pod_id: str) -> bool:
    now = time.monotonic()
    if now - _flush_at.get(pod_id, 0.0) >= settings.idle_flush_seconds:
        _flush_at[pod_id] = now
        return True
    return False


async def _publish_notification(subject: str, data: dict) -> None:
    """Publish to JetStream (creating the notifications stream once), with a
    core-NATS fallback so consumers still get the event if JetStream is off."""
    if not _nats_connected():
        return
    nc = nats_client.nc
    payload = json.dumps(data).encode()
    global _notify_stream_ready
    try:
        js = nc.jetstream()
        if not _notify_stream_ready:
            try:
                await js.add_stream(name=_NOTIFY_STREAM, subjects=["notification.*"])
            except Exception:
                pass  # already exists / created concurrently
            _notify_stream_ready = True
        await js.publish(subject, payload)
    except Exception:
        try:
            await nc.publish(subject, payload)
        except Exception:
            logger.debug("notification publish failed: %s", subject)


# --------------------------------------------------------------------------- #
# Ingest: metrics stream + activity heartbeats
# --------------------------------------------------------------------------- #
async def observe_metric(raw: bytes) -> None:
    """Handle one NATS metrics sample: refresh liveness for its pod."""
    try:
        data = json.loads(raw)
        metric_id = str(data["pod_id"])
        cpu = float(data.get("cpu_percent", 0) or 0)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return

    meta = await _resolve_pod(metric_id)
    if meta is None:
        return

    active = cpu >= settings.idle_cpu_threshold_percent
    if active:
        _flush_at[meta["pod_id"]] = time.monotonic()
    elif not _should_flush(meta["pod_id"]):
        # Throttle idle-sample writes; the idle window is minutes, not seconds.
        return

    now = datetime.utcnow()
    stmt = pg_insert(PodIdleState).values(
        pod_id=meta["pod_id"],
        user_id=meta["user_id"],
        pod_name=meta["pod_name"],
        plan=meta["plan"],
        phase="active",
        last_active_at=now,
        last_seen_at=now,
        warned_at=None,
    )
    set_: dict = {
        "last_seen_at": now,
        "user_id": stmt.excluded.user_id,
        "pod_name": stmt.excluded.pod_name,
        "plan": stmt.excluded.plan,
        "updated_at": now,
    }
    if active:
        # CPU activity refreshes liveness and cancels any pending warning.
        set_["last_active_at"] = now
        set_["phase"] = "active"
        set_["warned_at"] = None
    stmt = stmt.on_conflict_do_update(index_elements=["pod_id"], set_=set_)

    try:
        async with async_session() as db:
            await db.execute(stmt)
            await db.commit()
    except Exception:
        logger.debug("observe_metric upsert failed for %s", meta["pod_id"])


async def record_heartbeat(pod_id: str, active: bool) -> dict:
    """Record an activity heartbeat from the in-VM agent (or the browser).

    An ``active`` beat refreshes liveness and cancels a pending warning. The
    response tells the caller the current verdict so the VM can ``wall`` a
    warning. Unknown pods (never seen a metric) are simply reported active —
    there is nothing to cancel.
    """
    now = datetime.utcnow()
    async with async_session() as db:
        row = await db.get(PodIdleState, pod_id)
        if row is None:
            return {"status": "active", "seconds_remaining": 0, "message": ""}
        if active:
            row.last_active_at = now
            if row.phase == "warned":
                row.phase = "active"
                row.warned_at = None
                logger.info("idle: warning cancelled by heartbeat for %s", pod_id)
            row.updated_at = now
            await db.commit()

        status = row.phase
        seconds = 0
        message = ""
        if status == "warned" and row.warned_at:
            elapsed = (now - row.warned_at).total_seconds()
            seconds = max(0, int(settings.idle_grace_seconds - elapsed))
            message = _warning_message(max(1, seconds // 60))
    if active and status == "warned":
        await _publish_notification(
            "notification.idle_cancelled", {"pod_id": pod_id}
        )
    return {"status": status, "seconds_remaining": seconds, "message": message}


# --------------------------------------------------------------------------- #
# Scanner: warn -> terminate (runs on every worker; transitions are atomic)
# --------------------------------------------------------------------------- #
async def _emit_warning(db, row: PodIdleState, balance: float) -> None:
    minutes = max(1, settings.idle_grace_seconds // 60)
    rate = _plan_rate(row.plan)
    credits_left_minutes = int((balance / rate) * 60) if rate > 0 else 0
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            user_id=row.user_id,
            action="idle_warning",
            resource_type="pod",
            resource_id=row.pod_id,
            ip_address="-",
            status_code=200,
        )
    )
    await db.commit()
    await _publish_notification(
        "notification.idle_warning",
        {
            "pod_id": row.pod_id,
            "user_id": row.user_id,
            "grace_seconds": settings.idle_grace_seconds,
            "balance": balance,
            "credits_left_minutes": credits_left_minutes,
            "message": _warning_message(minutes),
        },
    )
    logger.info(
        "idle: warned pod=%s user=%s (balance=%.2f, ~%dm of credits left)",
        row.pod_id, row.user_id, balance, credits_left_minutes,
    )


async def _do_terminate(row: PodIdleState) -> bool:
    """Best-effort terminate via the orchestrator. Returns True only on success
    so the caller never marks a VM dead that is actually still running."""
    try:
        await orchestrator_client.terminate_pod(row.pod_name)
    except Exception:
        logger.exception("idle: TerminatePod failed for %s — keeping alive", row.pod_id)
        return False
    try:
        from app.services import port_forward

        await port_forward.stop(row.pod_name)
    except Exception:
        pass
    return True


async def _scan_once() -> None:
    now = datetime.utcnow()
    idle_before = now - timedelta(seconds=settings.idle_cpu_window_seconds)
    fresh_after = now - timedelta(seconds=settings.idle_metrics_stale_seconds)
    grace_deadline = now - timedelta(seconds=settings.idle_grace_seconds)
    forget_before = now - timedelta(seconds=settings.idle_forget_seconds)

    async with async_session() as db:
        # 0. Recovery: un-stick any 'terminating' row a crashed worker left behind.
        await db.execute(
            update(PodIdleState)
            .where(
                PodIdleState.phase == "terminating",
                PodIdleState.updated_at < now - timedelta(seconds=2 * settings.idle_check_interval_seconds),
            )
            .values(phase="warned", updated_at=now)
        )
        await db.commit()

        # 1. WARN: idle long enough, metrics still fresh, still has credits.
        candidates = (
            await db.execute(
                select(PodIdleState).where(
                    PodIdleState.phase == "active",
                    PodIdleState.last_active_at < idle_before,
                    PodIdleState.last_seen_at >= fresh_after,
                )
            )
        ).scalars().all()
        for row in candidates:
            balance = await get_balance(db, row.user_id)
            if balance <= 0:
                continue  # true exhaustion is billing.exhausted's job
            claimed = (
                await db.execute(
                    update(PodIdleState)
                    .where(PodIdleState.pod_id == row.pod_id, PodIdleState.phase == "active")
                    .values(phase="warned", warned_at=now, updated_at=now)
                )
            ).rowcount
            await db.commit()
            if claimed == 1:
                await _emit_warning(db, row, balance)

        # 2. TERMINATE: past grace, still idle, still fresh — with fail-safes.
        candidates = (
            await db.execute(
                select(PodIdleState).where(
                    PodIdleState.phase == "warned",
                    PodIdleState.warned_at < grace_deadline,
                    PodIdleState.last_active_at < idle_before,
                    PodIdleState.last_seen_at >= fresh_after,
                )
            )
        ).scalars().all()
        for row in candidates:
            if not _nats_connected():
                # Fail-safe: a dropped broker must never trigger a kill.
                logger.warning("idle: NATS down — refusing to terminate %s", row.pod_id)
                continue
            claimed = (
                await db.execute(
                    update(PodIdleState)
                    .where(PodIdleState.pod_id == row.pod_id, PodIdleState.phase == "warned")
                    .values(phase="terminating", updated_at=now)
                )
            ).rowcount
            await db.commit()
            if claimed != 1:
                continue  # another worker owns it

            if await _do_terminate(row):
                sess = await db.get(PodSession, row.pod_id)
                if sess and sess.state not in ("terminated", "failed"):
                    sess.state = "terminated"
                db.add(
                    AuditLog(
                        id=str(uuid.uuid4()),
                        user_id=row.user_id,
                        action="idle_terminate",
                        resource_type="pod",
                        resource_id=row.pod_id,
                        ip_address="-",
                        status_code=200,
                    )
                )
                await db.execute(
                    PodIdleState.__table__.delete().where(PodIdleState.pod_id == row.pod_id)
                )
                await db.commit()
                await _publish_notification(
                    "notification.idle_terminated",
                    {"pod_id": row.pod_id, "user_id": row.user_id},
                )
                logger.info("idle: terminated abandoned VM %s (user=%s)", row.pod_id, row.user_id)
            else:
                # Orchestrator failed — revert and retry next tick (stay alive).
                await db.execute(
                    update(PodIdleState)
                    .where(PodIdleState.pod_id == row.pod_id)
                    .values(phase="warned", updated_at=now)
                )
                await db.commit()

        # 3. Reactivate any warned row that saw activity (belt-and-suspenders).
        await db.execute(
            update(PodIdleState)
            .where(PodIdleState.phase == "warned", PodIdleState.last_active_at >= idle_before)
            .values(phase="active", warned_at=None, updated_at=now)
        )
        # 4. Forget rows for pods that stopped emitting metrics long ago.
        await db.execute(
            PodIdleState.__table__.delete().where(PodIdleState.last_seen_at < forget_before)
        )
        await db.commit()


async def _run_scanner() -> None:
    logger.info(
        "Idle agent scanner running (cpu<%.1f%% for %ds, grace %ds, tick %ds)",
        settings.idle_cpu_threshold_percent,
        settings.idle_cpu_window_seconds,
        settings.idle_grace_seconds,
        settings.idle_check_interval_seconds,
    )
    while True:
        try:
            await _scan_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("idle scanner tick failed")
        await asyncio.sleep(settings.idle_check_interval_seconds)


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
async def start_idle_agent() -> None:
    if not settings.idle_agent_enabled:
        logger.info("Idle agent disabled (HOPPER_IDLE_AGENT_ENABLED=false)")
        return

    async def _on_metric(msg):
        await observe_metric(msg.data)

    nc = nats_client.get_nc()
    # Own subscription + queue group, independent of the storage consumer.
    await nc.subscribe("metrics.*", queue="idle-workers", cb=_on_metric)

    global _scanner_task
    _scanner_task = asyncio.create_task(_run_scanner())
    logger.info("Idle agent started — subscribed to metrics.* (queue=idle-workers)")


async def stop_idle_agent() -> None:
    global _scanner_task
    if _scanner_task is not None:
        _scanner_task.cancel()
        try:
            await _scanner_task
        except (asyncio.CancelledError, Exception):
            pass
        _scanner_task = None
