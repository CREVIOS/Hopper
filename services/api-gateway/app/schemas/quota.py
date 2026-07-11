from pydantic import BaseModel, Field


class QuotaResponse(BaseModel):
    max_concurrent_vms: int
    max_workspace_gb: int
    # True if this is a per-user override, False if it's the global default.
    is_custom: bool


class QuotaSetRequest(BaseModel):
    max_concurrent_vms: int = Field(ge=0, le=1000)
    max_workspace_gb: int = Field(ge=0, le=100000)
