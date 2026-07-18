from datetime import datetime

from sqlalchemy import String, DateTime, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PodProvisioning(Base):
    """The approved sandbox spec + generated bootstrap for one provisioned VM.

    Written by ``POST /sandbox/provision`` and read by the in-VM provisioner via
    ``GET /sandbox/pods/{pod_id}/provision-script``. One row per pod; ``status``
    tracks the in-VM run (``pending`` -> ``running`` -> ``done`` / ``failed``)
    once the provisioner starts reporting.
    """

    __tablename__ = "pod_provisioning"

    # Matches pod_sessions.id (the UUID used in /pods/{id} URLs).
    pod_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The validated WorkspaceSpec (as emitted by WorkspaceSpec.model_dump()).
    spec: Mapped[dict] = mapped_column(JSON, nullable=False)
    # The rendered provision.sh the in-VM agent fetches and runs.
    provision_script: Mapped[str] = mapped_column(Text, nullable=False)
    llm_used: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
