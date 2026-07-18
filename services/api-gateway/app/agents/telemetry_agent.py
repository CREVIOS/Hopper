"""FEATURE 2 — Always-on telemetry / monitoring agent.

A background worker that, on a fixed cadence:

  1. **Collects** system + application telemetry — host CPU / memory / disk
     (via ``psutil`` when installed, else ``/proc`` + ``shutil``) and app health
     straight from Postgres (VM pods by state, recent failures, error rate).
  2. **Analyses** the snapshot against thresholds and derives a severity
     (``info`` / ``warning`` / ``critical``) plus human findings. Optionally a
     free open-source LLM (``HermesAgent`` from :mod:`app.agents.free_agents`)
     phrases the summary — no paid API.
  3. **Alerts** — when severity ≥ ``settings.telemetry_alert_min_severity`` it
     dispatches the report to Email / WhatsApp via :mod:`app.agents.alerting`.

Orchestration: if ``langgraph`` is installed we run a real ``StateGraph``
(collect → analyse → alert), which is the doc's preferred cyclic/stateful
engine; otherwise we run the identical steps sequentially. Either way the public
entry point is :func:`run_once`.

Continuous execution: :func:`start_telemetry_agent` schedules ``run_once`` on an
interval using ``APScheduler`` if available, else a plain ``asyncio`` task loop.
Call it from the FastAPI lifespan (already wired in ``app.main``). For a
standalone worker / cron box, run ``python -m app.agents.telemetry_agent``.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text

from app.config import settings

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}

# Latest run, exposed to the API router for a quick health view.
_latest: dict | None = None


# --------------------------------------------------------------------------- #
# 1. COLLECT
# --------------------------------------------------------------------------- #
@dataclass
class TelemetrySnapshot:
    ts: str
    cpu_percent: float
    mem_percent: float
    disk_percent: float
    pods_by_state: dict[str, int] = field(default_factory=dict)
    recent_failures: int = 0
    error_rate: float = 0.0
    collection_errors: list[str] = field(default_factory=list)


def _host_metrics() -> tuple[float, float, float]:
    """(cpu%, mem%, disk%) — psutil if present, else best-effort stdlib."""
    try:
        import psutil  # type: ignore

        return (
            float(psutil.cpu_percent(interval=0.3)),
            float(psutil.virtual_memory().percent),
            float(psutil.disk_usage("/").percent),
        )
    except ModuleNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("psutil metrics failed: %s", exc)

    # Stdlib fallback — disk is exact; cpu/mem are coarse from /proc.
    cpu = mem = 0.0
    try:
        total, used, _free = shutil.disk_usage("/")
        disk = round(used / total * 100, 1)
    except Exception:  # noqa: BLE001
        disk = 0.0
    try:
        with open("/proc/meminfo") as f:
            info = {}
            for line in f:
                k, _, v = line.partition(":")
                info[k] = float(v.strip().split()[0])
        if info.get("MemTotal"):
            mem = round((1 - info.get("MemAvailable", 0) / info["MemTotal"]) * 100, 1)
    except Exception:  # noqa: BLE001
        pass
    try:
        load1, *_ = os.getloadavg()
        cpu = round(min(100.0, load1 / (os.cpu_count() or 1) * 100), 1)
    except Exception:  # noqa: BLE001
        pass
    return cpu, mem, disk


async def _app_metrics() -> tuple[dict[str, int], int, float, list[str]]:
    """VM pods by state, recent failures, and a failure error-rate, from Postgres."""
    from app.core.database import async_session

    errors: list[str] = []
    pods_by_state: dict[str, int] = {}
    recent_failures = 0
    error_rate = 0.0
    try:
        async with async_session() as db:
            rows = (await db.execute(
                text("SELECT state, COUNT(*) AS n FROM pod_sessions GROUP BY state")
            )).all()
            pods_by_state = {r.state: int(r.n) for r in rows}

            recent_failures = int((await db.execute(text(
                "SELECT COUNT(*) FROM pod_sessions "
                "WHERE state = 'failed' AND started_at > NOW() - INTERVAL '1 hour'"
            ))).scalar_one() or 0)

            total_recent = int((await db.execute(text(
                "SELECT COUNT(*) FROM pod_sessions "
                "WHERE started_at > NOW() - INTERVAL '1 hour'"
            ))).scalar_one() or 0)
            if total_recent:
                error_rate = round(recent_failures / total_recent, 3)
    except Exception as exc:  # noqa: BLE001 - DB down is itself worth reporting
        errors.append(f"db telemetry unavailable: {exc}")
    return pods_by_state, recent_failures, error_rate, errors


async def collect_telemetry() -> TelemetrySnapshot:
    cpu, mem, disk = await asyncio.to_thread(_host_metrics)
    pods_by_state, recent_failures, error_rate, errors = await _app_metrics()
    return TelemetrySnapshot(
        ts=datetime.now(timezone.utc).isoformat(),
        cpu_percent=cpu, mem_percent=mem, disk_percent=disk,
        pods_by_state=pods_by_state, recent_failures=recent_failures,
        error_rate=error_rate, collection_errors=errors,
    )


# --------------------------------------------------------------------------- #
# 2. ANALYSE
# --------------------------------------------------------------------------- #
def evaluate(snap: TelemetrySnapshot) -> tuple[str, list[str]]:
    """Return (severity, findings). Pure/rule-based so it's deterministic."""
    findings: list[str] = []
    severity = "info"

    def bump(level: str) -> None:
        nonlocal severity
        if _SEVERITY_ORDER[level] > _SEVERITY_ORDER[severity]:
            severity = level

    if snap.disk_percent >= settings.telemetry_disk_warn_percent:
        findings.append(f"Disk at {snap.disk_percent:.0f}% (≥ {settings.telemetry_disk_warn_percent:.0f}%) "
                        f"— risks kubelet DiskPressure, which blocks new VMs from scheduling.")
        bump("critical" if snap.disk_percent >= 95 else "warning")
    if snap.cpu_percent >= settings.telemetry_cpu_warn_percent:
        findings.append(f"CPU at {snap.cpu_percent:.0f}% (≥ {settings.telemetry_cpu_warn_percent:.0f}%).")
        bump("warning")
    if snap.mem_percent >= settings.telemetry_mem_warn_percent:
        findings.append(f"Memory at {snap.mem_percent:.0f}% (≥ {settings.telemetry_mem_warn_percent:.0f}%).")
        bump("warning")
    if snap.error_rate >= settings.telemetry_error_rate_warn:
        findings.append(f"VM failure rate {snap.error_rate:.0%} in the last hour "
                        f"({snap.recent_failures} failed).")
        bump("warning" if snap.error_rate < 0.25 else "critical")
    if snap.collection_errors:
        findings.extend(snap.collection_errors)
        bump("warning")

    if not findings:
        findings.append("All monitored signals within thresholds.")
    return severity, findings


async def summarize(snap: TelemetrySnapshot, severity: str, findings: list[str]) -> str:
    """A short report. Uses a free LLM to phrase it when enabled + reachable,
    else a deterministic template."""
    header = (
        f"Hopper telemetry — {severity.upper()} @ {snap.ts}\n"
        f"CPU {snap.cpu_percent:.0f}% · MEM {snap.mem_percent:.0f}% · DISK {snap.disk_percent:.0f}%\n"
        f"Pods: {snap.pods_by_state or '{}'} · failures/1h: {snap.recent_failures} "
        f"· error-rate: {snap.error_rate:.0%}\n"
        "Findings:\n" + "\n".join(f"  • {f}" for f in findings)
    )
    if not settings.telemetry_use_llm_summary:
        return header
    try:
        from app.agents.free_agents import HermesAgent

        agent = HermesAgent()
        prompt = (
            "You are an SRE assistant. Given this monitoring snapshot, write a 2-3 sentence "
            "status summary for an on-call engineer. Be specific and calm; if severity is "
            "warning/critical, lead with the most urgent action.\n\n" + header
        )
        note = await agent.arun(prompt, temperature=0.2)
        if note and not note.startswith("["):  # skip stub/error markers
            return f"{header}\n\nSummary: {note}"
    except Exception as exc:  # noqa: BLE001 - summary is best-effort
        logger.debug("telemetry summary LLM failed: %s", exc)
    return header


# --------------------------------------------------------------------------- #
# 3. ALERT + orchestration
# --------------------------------------------------------------------------- #
async def _resolve_recipients(severity: str) -> tuple[list[str], list[str]]:
    """Union of global config recipients and every subscribed user whose chosen
    minimum severity is met by this alert. Returns (emails, telegram_numbers)."""
    sev = _SEVERITY_ORDER[severity]
    emails: set[str] = {e.strip() for e in settings.alert_email_to.split(",") if e.strip()}
    numbers: set[str] = {n.strip() for n in settings.telegram_to.split(",") if n.strip()}

    try:
        from sqlalchemy import select

        from app.core.database import async_session
        from app.models.alert_subscription import AlertSubscription

        async with async_session() as db:
            subs = (await db.execute(select(AlertSubscription))).scalars().all()
        for s in subs:
            if sev < _SEVERITY_ORDER.get(s.min_severity, 1):
                continue  # this user only wants higher-severity alerts
            if s.email_enabled and s.email_address:
                emails.add(s.email_address.strip())
            if s.telegram_enabled and s.telegram_number:
                numbers.add(s.telegram_number.strip())
    except Exception as exc:  # noqa: BLE001 - subscription lookup must not block alerting
        logger.warning("telemetry: subscriber lookup failed (%s); using global config only", exc)

    return list(emails), list(numbers)


async def _alert_if_needed(severity: str, subject: str, report: str) -> dict[str, bool] | None:
    threshold = _SEVERITY_ORDER.get(settings.telemetry_alert_min_severity, 1)
    if _SEVERITY_ORDER[severity] < threshold:
        logger.debug("telemetry: %s below alert threshold; not dispatching", severity)
        return None
    from app.agents.alerting import dispatch_alert

    emails, numbers = await _resolve_recipients(severity)
    return await dispatch_alert(subject, report, emails=emails, telegram_numbers=numbers)


async def _run_sequential() -> dict:
    snap = await collect_telemetry()
    severity, findings = evaluate(snap)
    report = await summarize(snap, severity, findings)
    subject = f"[Hopper {severity.upper()}] telemetry report"
    delivered = await _alert_if_needed(severity, subject, report)
    return {
        "ts": snap.ts, "severity": severity, "findings": findings,
        "snapshot": asdict(snap), "report": report, "alerted": delivered,
    }


def _try_langgraph():
    """Build a LangGraph StateGraph(collect→analyse→alert) if langgraph is
    installed. Returns a compiled graph or None."""
    try:
        from typing import TypedDict

        from langgraph.graph import END, START, StateGraph  # type: ignore
    except Exception:  # noqa: BLE001 - not installed / import error
        return None

    class S(TypedDict, total=False):
        snapshot: TelemetrySnapshot
        severity: str
        findings: list
        report: str
        result: dict

    async def n_collect(state: S) -> S:
        state["snapshot"] = await collect_telemetry()
        return state

    async def n_analyse(state: S) -> S:
        sev, findings = evaluate(state["snapshot"])
        state["severity"], state["findings"] = sev, findings
        state["report"] = await summarize(state["snapshot"], sev, findings)
        return state

    async def n_alert(state: S) -> S:
        subject = f"[Hopper {state['severity'].upper()}] telemetry report"
        delivered = await _alert_if_needed(state["severity"], subject, state["report"])
        state["result"] = {
            "ts": state["snapshot"].ts, "severity": state["severity"],
            "findings": state["findings"], "snapshot": asdict(state["snapshot"]),
            "report": state["report"], "alerted": delivered,
        }
        return state

    g = StateGraph(S)
    g.add_node("collect", n_collect)
    g.add_node("analyse", n_analyse)
    g.add_node("alert", n_alert)
    g.add_edge(START, "collect")
    g.add_edge("collect", "analyse")
    g.add_edge("analyse", "alert")
    g.add_edge("alert", END)
    return g.compile()


_graph = None
_graph_built = False


async def run_once() -> dict:
    """One collect→analyse→alert cycle. Never raises. Stores the latest result."""
    global _latest, _graph, _graph_built
    try:
        if not _graph_built:
            _graph = _try_langgraph()
            _graph_built = True
            logger.info("telemetry orchestration: %s", "langgraph" if _graph else "sequential")
        if _graph is not None:
            out = await _graph.ainvoke({})
            result = out["result"]
        else:
            result = await _run_sequential()
        _latest = result
        logger.info("telemetry: %s — %d finding(s)", result["severity"], len(result["findings"]))
        return result
    except Exception as exc:  # noqa: BLE001 - the monitor must never crash the app
        logger.exception("telemetry run failed: %s", exc)
        _latest = {"ts": datetime.now(timezone.utc).isoformat(), "severity": "info",
                   "error": str(exc)}
        return _latest


def latest() -> dict | None:
    return _latest


# --------------------------------------------------------------------------- #
# Continuous execution
# --------------------------------------------------------------------------- #
_scheduler = None
_task: asyncio.Task | None = None


async def start_telemetry_agent() -> None:
    """Start the recurring monitor. APScheduler if available, else an asyncio loop.
    Safe to call once from the FastAPI lifespan; a no-op when disabled."""
    global _scheduler, _task
    if not settings.telemetry_agent_enabled:
        logger.info("telemetry agent disabled (HOPPER_TELEMETRY_AGENT_ENABLED=false)")
        return
    interval = max(30, settings.telemetry_interval_seconds)

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore

        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(run_once, "interval", seconds=interval,
                           next_run_time=datetime.now(timezone.utc), id="telemetry", max_instances=1)
        _scheduler.start()
        logger.info("telemetry agent started (apscheduler, every %ss)", interval)
        return
    except ModuleNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("apscheduler unavailable (%s); using asyncio loop", exc)

    async def _loop() -> None:
        while True:
            await run_once()
            await asyncio.sleep(interval)

    _task = asyncio.create_task(_loop())
    logger.info("telemetry agent started (asyncio loop, every %ss)", interval)


async def stop_telemetry_agent() -> None:
    global _scheduler, _task
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
        _scheduler = None
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        _task = None


async def _main() -> None:
    """Standalone runner for a worker/cron deployment (no FastAPI)."""
    logging.basicConfig(level=logging.INFO)
    interval = max(30, settings.telemetry_interval_seconds)
    logger.info("telemetry agent (standalone) every %ss — Ctrl+C to stop", interval)
    while True:
        result = await run_once()
        print(result.get("report", result))
        await asyncio.sleep(interval)


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
