"""Schemas for admin workspace management (FR-HC-30)."""

from pydantic import BaseModel, Field


class WorkspaceResizeRequest(BaseModel):
    # Up-only, per FR-HC-30; 4096 GiB ceiling matches the ext4 practical range
    # and guards against a fat-finger. The endpoint further clamps to the user's
    # storage quota.
    capacity_gb: int = Field(gt=0, le=4096)
