from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PodIdleState(Base):
    """FSM state for the idle-detection agent, one row per tracked VM.

    Kept in Postgres (not in-memory) so the state is consistent across the
    multiple uvicorn workers and survives a worker restart. Transitions are
    driven by atomic claim UPDATEs (see app/services/idle_agent.py) so exactly
    one worker acts on a given pod even when several run the scanner.

    phase: ``active`` -> ``warned`` -> ``terminating`` (transient) -> row deleted.
    Any activity flips ``warned`` back to ``active``.
    """

    __tablename__ = "pod_idle_state"

    # Matches pod_sessions.id (the UUID used in /pods/{id} URLs).
    pod_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Orchestrator-side name (vm-<nano>) — required to call TerminatePod.
    pod_name: Mapped[str] = mapped_column(String, nullable=False)
    plan: Mapped[str] = mapped_column(String, nullable=False, default="small")
    phase: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)
    # Last CPU-active sample or activity heartbeat.
    last_active_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Last metric observed at all — freshness guard for the fail-safe.
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    warned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
