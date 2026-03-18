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


class VmPlan(str, Enum):
    """VM plans that slice the host machine's resources."""
    SMALL = "small"      # 1 CPU, 2GB RAM, 5GB disk  — 1 credit/hour
    MEDIUM = "medium"    # 2 CPU, 4GB RAM, 10GB disk — 2 credits/hour
    LARGE = "large"      # 4 CPU, 8GB RAM, 20GB disk — 4 credits/hour


# Resource limits per plan (used by orchestrator to set cgroup limits)
VM_PLAN_RESOURCES = {
    VmPlan.SMALL:  {"cpu": "1",    "memory": "2Gi",  "disk": "5Gi",  "credits_per_hour": 1.0},
    VmPlan.MEDIUM: {"cpu": "2",    "memory": "4Gi",  "disk": "10Gi", "credits_per_hour": 2.0},
    VmPlan.LARGE:  {"cpu": "4",    "memory": "8Gi",  "disk": "20Gi", "credits_per_hour": 4.0},
}


class CreatePodRequest(BaseModel):
    plan: VmPlan
    image: str = "hopper/vm-ubuntu:22.04"


class PodResponse(BaseModel):
    id: str
    user_id: str
    state: PodState
    plan: str
    image: str
    cpu: str | None = None
    memory: str | None = None
    node_name: str | None = None
    namespace: str
    ssh_port: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
