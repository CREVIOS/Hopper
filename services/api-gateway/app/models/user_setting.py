from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserSetting(Base):
    """Per-user application settings — currently the VS Code / code-server prefs
    blob. One row per user; `vscode` is opaque JSON echoed back to the editor.

    Previously `PUT /settings/vscode` accepted this and discarded it; it is now
    persisted here (in the DB, independent of any VM) so it survives across
    sessions and can be served without a running pod.
    """

    __tablename__ = "user_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    vscode: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
