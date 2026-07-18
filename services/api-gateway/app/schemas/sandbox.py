"""Schemas for the Smart Project Sandbox Template Generator.

Flow: a user describes a project in natural language -> the agent proposes a
``WorkspaceSpec`` (``POST /sandbox/plan``) -> the user approves it ->
``POST /sandbox/provision`` creates a VM whose in-VM provisioner runs the
generated ``provision.sh``.

``WorkspaceSpec`` is the validated, allowlisted result. ``RawWorkspaceSpec`` is
the *untrusted* shape the LLM (or the deterministic fallback) emits — it is run
through ``sandbox_agent.validate_spec`` before anything is installed.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.pod import VmPlan


class RawWorkspaceSpec(BaseModel):
    """Untrusted planner output. Every list is validated before use.

    This is also the JSON shape handed to Gemini as a ``response_schema`` so the
    model returns exactly these fields. Keep it flat and string-list-only — the
    structured-output backends and the allowlist validator both rely on that.
    """

    summary: str = Field(default="", description="One-line description of the workspace.")
    base_template: str = Field(default="ubuntu", description="ubuntu | python-ml | cpp | java")
    apt_packages: list[str] = Field(default_factory=list)
    pip_packages: list[str] = Field(default_factory=list)
    npm_packages: list[str] = Field(default_factory=list)
    vscode_extensions: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list, description="postgresql | redis | mysql | mongodb")


class WorkspaceSpec(RawWorkspaceSpec):
    """A validated spec: everything here has passed the allowlist."""


class RejectedItemOut(BaseModel):
    kind: str
    value: str
    reason: str


class PlanRequest(BaseModel):
    description: str = Field(
        min_length=3,
        max_length=2000,
        description="Natural-language project description, e.g. 'React frontend "
        "with a FastAPI backend and a Postgres database'.",
    )
    plan: VmPlan = VmPlan.SMALL


class PlanResponse(BaseModel):
    """Returned by /sandbox/plan for human review before anything is built."""

    spec: WorkspaceSpec
    plan: VmPlan
    credits_per_hour: float
    provision_script: str
    # Items the planner proposed but the allowlist dropped — surfaced so the
    # user understands exactly what will and won't be installed.
    rejected: list[RejectedItemOut] = Field(default_factory=list)
    # True when a real LLM produced the spec; False when the deterministic
    # keyword fallback did (no GEMINI_API_KEY configured).
    llm_used: bool = False
    notes: list[str] = Field(default_factory=list)


class ProvisionRequest(BaseModel):
    """Approve a (possibly edited) spec and create the VM."""

    spec: WorkspaceSpec
    plan: VmPlan = VmPlan.SMALL
    description: str = ""
