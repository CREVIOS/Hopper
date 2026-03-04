from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class PodState(str, Enum):
    PENDING = "pending"
    CREATING = "creating"
    RUNNING = "running"
    STOPPING = "stopping"
    TERMINATED = "terminated"
    FAILED = "failed"


class GpuTier(str, Enum):
    PREMIUM = "premium"
    STANDARD = "standard"
    BUDGET = "budget"
    SCAVENGER = "scavenger"


class CreatePodRequest(BaseModel):
    gpu_tier: GpuTier
    image: str = "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime"


class PodResponse(BaseModel):
    id: str
    user_id: str
    state: PodState
    gpu_tier: GpuTier
    image: str
    node_name: str | None = None
    namespace: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
