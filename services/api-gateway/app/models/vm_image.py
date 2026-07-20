from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, false, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VmImageRow(Base):
    """Admin-configurable VM base-image / template catalogue (``vm_images``).

    Runtime source of truth for the container image each template maps to,
    replacing the hardcoded VM_TEMPLATE_IMAGES dict. ``template`` is the stable
    key the frontend sends and create_pod resolves to ``image``.
    """

    __tablename__ = "vm_images"

    template: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    image: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    # Exactly one image should be the default (used when a launch omits template);
    # the service keeps this single-valued.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
