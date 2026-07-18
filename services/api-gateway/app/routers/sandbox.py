"""Smart Project Sandbox Template Generator.

Endpoints:
  POST /sandbox/plan     — NL description -> proposed WorkspaceSpec (no side effects)
  POST /sandbox/provision — approved spec -> create VM + store provision.sh
  GET  /sandbox/pods/{id}/provision-script — in-VM provisioner fetches its script

The plan/provision split is the human-in-the-loop guardrail: nothing is built or
billed until the user approves a concrete spec, and everything installed has
passed the allowlist (see app/services/sandbox_agent + sandbox_allowlist).
"""
import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import get_current_user, get_db
from app.models.sandbox_spec import PodProvisioning
from app.models.session import PodSession
from app.schemas.pod import VM_PLAN_RESOURCES, VM_TEMPLATE_IMAGES, DEFAULT_TEMPLATE
from app.schemas.sandbox import (
    PlanRequest,
    PlanResponse,
    ProvisionRequest,
    RejectedItemOut,
)
from app.schemas.user import TokenPayload
from app.services import sandbox_agent
from app.services.credit_service import get_balance
from app.services.orchestrator_client import orchestrator_client

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_CONCURRENT_PODS = 3


def _require_enabled() -> None:
    if not settings.sandbox_agent_enabled:
        raise HTTPException(status_code=503, detail="Sandbox agent is disabled")


@router.post("/plan", response_model=PlanResponse)
@limiter.limit("20/minute")
async def plan_sandbox(
    request: Request,
    response: Response,
    body: PlanRequest,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Propose a workspace for a natural-language description. No side effects.

    Runs the (possibly LLM-backed) planner off the event loop, validates the
    result against the allowlist, and returns the spec, the exact provision.sh
    that would run, and any items the allowlist dropped.
    """
    _require_enabled()

    raw, llm_used, notes = await run_in_threadpool(sandbox_agent.plan_workspace, body.description)
    spec, rejected = sandbox_agent.validate_spec(raw)
    script = sandbox_agent.render_provision_script(spec)

    return PlanResponse(
        spec=spec,
        plan=body.plan,
        credits_per_hour=sandbox_agent.credits_per_hour(body.plan),
        provision_script=script,
        rejected=[RejectedItemOut(**r.as_dict()) for r in rejected],
        llm_used=llm_used,
        notes=notes,
    )


@router.post("/provision", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def provision_sandbox(
    request: Request,
    response: Response,
    body: ProvisionRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a spec and create a VM whose in-VM provisioner will run it.

    Re-validates the spec server-side (the client may have edited it), then
    follows the same create path as POST /pods: credit check, concurrency cap,
    orchestrator CreatePod — additionally passing the HOPPER_* env the in-VM
    provisioner needs, and storing the generated script for it to fetch.
    """
    _require_enabled()

    # Never trust the spec the client sends back — re-run the allowlist.
    spec, _rejected = sandbox_agent.validate_spec(body.spec)
    script = sandbox_agent.render_provision_script(spec)

    resources = VM_PLAN_RESOURCES[body.plan]
    balance = await get_balance(db, current_user.sub)
    if balance < resources["credits_per_hour"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Need {resources['credits_per_hour']}, have {balance:.2f}",
        )

    active_result = await db.execute(
        select(PodSession).where(
            PodSession.user_id == current_user.sub,
            PodSession.state.in_(["pending", "creating", "running"]),
        )
    )
    if len(active_result.scalars().all()) >= MAX_CONCURRENT_PODS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum {MAX_CONCURRENT_PODS} concurrent VMs allowed",
        )

    pod_id = str(uuid.uuid4())
    namespace = "hopper"
    image = VM_TEMPLATE_IMAGES.get(spec.base_template, VM_TEMPLATE_IMAGES[DEFAULT_TEMPLATE])

    session = PodSession(
        id=pod_id,
        user_id=current_user.sub,
        plan=body.plan.value,
        image=image,
        cpu=resources["cpu"],
        memory=resources["memory"],
        namespace=namespace,
        pod_name=f"vm-{pod_id[:8]}",
        state="pending",
    )
    db.add(session)

    # Persist the provisioning record BEFORE the pod boots, so the in-VM
    # provisioner's fetch can never race ahead of the row existing.
    db.add(
        PodProvisioning(
            pod_id=pod_id,
            user_id=current_user.sub,
            description=body.description,
            spec=spec.model_dump(),
            provision_script=script,
            status="pending",
        )
    )
    await db.commit()
    await db.refresh(session)

    try:
        resp = await orchestrator_client.create_pod(
            user_id=current_user.sub,
            plan=body.plan.value,
            image=image,
            cpu=resources["cpu"],
            memory=resources["memory"],
            pod_id=pod_id,
            labels=sandbox_agent.build_pod_env(pod_id),
        )
        session.state = resp.state
        session.pod_name = resp.id
        session.ssh_port = resp.ssh_port or None
        session.vscode_port = resp.vscode_port or None
        session.ssh_password = resp.ssh_password or None
        await db.commit()
        await db.refresh(session)
    except Exception as e:  # noqa: BLE001 - mirror POST /pods failure handling
        logger.error("Orchestrator CreatePod failed for sandbox %s: %s", pod_id, e)
        session.state = "failed"
        await db.commit()
        await db.refresh(session)

    return {
        "pod_id": pod_id,
        "state": session.state,
        "image": image,
        "vscode_port": session.vscode_port,
        "ssh_port": session.ssh_port,
        "spec": spec.model_dump(),
    }


@router.get("/pods/{pod_id}/provision-script", response_class=PlainTextResponse)
async def get_provision_script(
    pod_id: str,
    x_pod_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return the raw provision.sh for the in-VM provisioner.

    Authenticated by the per-pod HMAC token (same token the idle agent uses),
    so a VM can only fetch its own script and no user session is required.
    """
    if not sandbox_agent.verify_provision_token(pod_id, x_pod_token):
        raise HTTPException(status_code=401, detail="unauthorized")

    row = await db.get(PodProvisioning, pod_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no provisioning script for this VM")
    return PlainTextResponse(row.provision_script)


@router.post("/pods/{pod_id}/provision-status")
@limiter.limit("60/minute")
async def report_provision_status(
    pod_id: str,
    request: Request,
    response: Response,
    x_pod_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """The in-VM provisioner reports its run outcome (running/done/failed)."""
    if not sandbox_agent.verify_provision_token(pod_id, x_pod_token):
        raise HTTPException(status_code=401, detail="unauthorized")

    body = await request.json()
    new_status = str(body.get("status", "")).strip()
    if new_status not in {"running", "done", "failed"}:
        raise HTTPException(status_code=400, detail="invalid status")

    row = await db.get(PodProvisioning, pod_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown VM")
    row.status = new_status
    await db.commit()
    return {"ok": True, "status": new_status}
