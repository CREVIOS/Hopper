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


# Resource limits per plan (used by orchestrator to set cgroup limits).
# These match the labels shown in the frontend (VM_PLAN_INFO).
VM_PLAN_RESOURCES = {
    VmPlan.SMALL:  {"cpu": "1",  "memory": "2Gi", "disk": "5Gi",  "credits_per_hour": 1.0},
    VmPlan.MEDIUM: {"cpu": "2",  "memory": "4Gi", "disk": "10Gi", "credits_per_hour": 2.0},
    VmPlan.LARGE:  {"cpu": "4",  "memory": "8Gi", "disk": "20Gi", "credits_per_hour": 4.0},
}


# Frontend sends `template` (a friendly key); backend resolves to the actual
# container image tag. Keep these in sync with images/hopper-vm-* Dockerfiles
# and the build target in Makefile (`make vm-images`).
VM_TEMPLATE_IMAGES: dict[str, str] = {
    "ubuntu":    "hopper/vm-ubuntu:22.04",
    "python-ml": "hopper/vm-python-ml:22.04",
    "cpp":       "hopper/vm-cpp:22.04",
    "java":      "hopper/vm-java:22.04",
}
DEFAULT_TEMPLATE = "ubuntu"


class CreatePodRequest(BaseModel):
    plan: VmPlan
    template: str = DEFAULT_TEMPLATE
    # `image` is kept for backward-compat / direct image overrides (admin/CLI).
    # When unset, it's resolved from `template` via VM_TEMPLATE_IMAGES.
    image: str | None = None

    def resolved_image(self) -> str:
        if self.image:
            return self.image
        return VM_TEMPLATE_IMAGES.get(self.template, VM_TEMPLATE_IMAGES[DEFAULT_TEMPLATE])


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
    vscode_port: int | None = None
    ssh_password: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    extension_count: int = 0

    model_config = {"from_attributes": True}
