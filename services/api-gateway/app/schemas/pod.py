from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.config import settings


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
# container image tag. The reference is "{prefix}vm-<template>:22.04" — prefix
# defaults to "hopper/" (locally imported images) and is set to a GHCR path in
# the deployed cluster so every node pulls from the registry. Keep the template
# keys in sync with the images/hopper-vm-* Dockerfiles.
_VM_TEMPLATES = ("ubuntu", "python-ml", "cpp", "java")
VM_TEMPLATE_IMAGES: dict[str, str] = {
    t: f"{settings.vm_image_prefix}vm-{t}:22.04" for t in _VM_TEMPLATES
}
DEFAULT_TEMPLATE = "ubuntu"


class CreatePodRequest(BaseModel):
    # Plan key, validated at request time against the DB-backed vm_plans
    # catalogue (was the VmPlan enum; kept as a plain string so admins can add
    # plans beyond small/medium/large without a code change). VM_PLAN_RESOURCES
    # remains as a built-in fallback for the scheduler's disk math.
    plan: str
    template: str = DEFAULT_TEMPLATE
    # `image` is kept for backward-compat / direct image overrides (admin/CLI).
    # When unset, it's resolved from `template` via VM_TEMPLATE_IMAGES.
    image: str | None = None
    # Network isolation group (HOP-19 18.3). VMs sharing a group can reach
    # each other over the pod network (team projects); unset = fully isolated
    # (the default). Teacher/admin only — the router enforces the role, since
    # without course membership a student could otherwise join any group and
    # defeat tenant isolation. Must be a DNS-label-safe slug (it becomes a
    # K8s label value and part of a NetworkPolicy name).
    network_group: str | None = Field(
        default=None, min_length=1, max_length=32,
        pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
    )

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
    network_group: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
