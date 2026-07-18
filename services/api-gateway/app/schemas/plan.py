from pydantic import BaseModel, Field


class PlanResponse(BaseModel):
    name: str
    display_name: str
    cpu: str
    memory: str
    disk: str
    credits_per_hour: float
    workspace_gb: int
    is_active: bool

    model_config = {"from_attributes": True}


class PlanCreateRequest(BaseModel):
    # DNS-label-ish key; kept short and lowercase since it becomes a k8s label
    # value and the pod_sessions.plan string.
    name: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(min_length=1, max_length=64)
    cpu: str = Field(min_length=1, max_length=16)
    memory: str = Field(min_length=1, max_length=16)
    disk: str = Field(min_length=1, max_length=16)
    credits_per_hour: float = Field(gt=0)
    workspace_gb: int = Field(gt=0, le=10000)


class PlanUpdateRequest(BaseModel):
    # All optional — only the provided fields are changed. name is immutable.
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    cpu: str | None = Field(default=None, min_length=1, max_length=16)
    memory: str | None = Field(default=None, min_length=1, max_length=16)
    disk: str | None = Field(default=None, min_length=1, max_length=16)
    credits_per_hour: float | None = Field(default=None, gt=0)
    workspace_gb: int | None = Field(default=None, gt=0, le=10000)
    is_active: bool | None = None
