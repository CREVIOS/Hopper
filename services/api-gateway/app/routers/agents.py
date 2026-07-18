"""API surface for the agent layer.

* ``GET  /agents/``                 — list free agents + the resolved provider
* ``POST /agents/{name}/chat``      — one-shot chat with hermes|clawbot|opencode
* ``GET  /agents/telemetry/latest`` — most recent monitor result (admin)
* ``POST /agents/telemetry/run``    — trigger a telemetry cycle now (admin)

Agent chat is available to any authenticated user (rate-limited); telemetry
endpoints are admin/professor only.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.dependencies import get_current_user, get_db
from app.schemas.user import TokenPayload

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_CONCURRENT_PODS = 3


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    agent: str
    provider: str
    model: str
    reply: str


class LaunchRequest(BaseModel):
    plan: str = "small"          # small | medium | large
    template: str = "ubuntu"     # ubuntu | python-ml | cpp | java


class LaunchResponse(BaseModel):
    agent: str
    pod_id: str
    state: str
    image: str


@router.get("/")
async def list_agents(current_user: TokenPayload = Depends(get_current_user)):
    from app.agents import free_agents

    provider = free_agents.resolve_provider()
    return {
        "agents": free_agents.available_agents(),
        "provider": provider.name,
        "model": provider.model,
        "provider_available": provider.available(),
    }


@router.post("/{name}/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_agent(
    name: str,
    request: Request,
    response: Response,
    body: ChatRequest,
    current_user: TokenPayload = Depends(get_current_user),
):
    from app.agents import free_agents

    try:
        agent = free_agents.get_agent(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    reply = await agent.arun(body.prompt, temperature=body.temperature)
    return ChatResponse(
        agent=agent.name, provider=agent.provider.name,
        model=agent.provider.model, reply=reply,
    )


@router.post("/{name}/launch", response_model=LaunchResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("6/minute")
async def launch_agent_vm(
    name: str,
    request: Request,
    response: Response,
    body: LaunchRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch the selected agent *inside a fresh VM*.

    Reuses the Smart Sandbox provisioning path: create a pod whose first-boot
    provisioner installs the agent's in-VM CLI (``hopper-agent``) wired to a free
    LLM backend. Same credit check + concurrency cap as ``POST /pods``.
    """
    from app.agents import agent_runtime, free_agents
    from app.models.sandbox_spec import PodProvisioning
    from app.models.session import PodSession
    from app.schemas.pod import (
        DEFAULT_TEMPLATE,
        VM_PLAN_RESOURCES,
        VM_TEMPLATE_IMAGES,
        VmPlan,
    )
    from app.services.credit_service import get_balance
    from app.services.orchestrator_client import orchestrator_client

    agent_key = name.lower().strip()
    if agent_key not in free_agents.available_agents():
        raise HTTPException(status_code=404, detail=f"unknown agent '{name}'")
    try:
        plan = VmPlan(body.plan)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"unknown plan '{body.plan}'")

    resources = VM_PLAN_RESOURCES[plan]
    balance = await get_balance(db, current_user.sub)
    if balance < resources["credits_per_hour"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Need {resources['credits_per_hour']}, have {balance:.2f}",
        )

    active = await db.execute(
        select(PodSession).where(
            PodSession.user_id == current_user.sub,
            PodSession.state.in_(["pending", "creating", "running"]),
        )
    )
    if len(active.scalars().all()) >= MAX_CONCURRENT_PODS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum {MAX_CONCURRENT_PODS} concurrent VMs allowed",
        )

    pod_id = str(uuid.uuid4())
    image = VM_TEMPLATE_IMAGES.get(body.template, VM_TEMPLATE_IMAGES[DEFAULT_TEMPLATE])
    script = agent_runtime.render_agent_provision_script(agent_key)

    session = PodSession(
        id=pod_id,
        user_id=current_user.sub,
        plan=plan.value,
        image=image,
        cpu=resources["cpu"],
        memory=resources["memory"],
        namespace="hopper",
        pod_name=f"vm-{pod_id[:8]}",
        state="pending",
    )
    db.add(session)
    # Persist the provision script BEFORE boot so the in-VM provisioner's fetch
    # can't race ahead of the row existing (same guarantee as the sandbox path).
    db.add(
        PodProvisioning(
            pod_id=pod_id,
            user_id=current_user.sub,
            description=f"{agent_runtime.agent_title(agent_key)} agent VM",
            spec={"agent": agent_key},
            provision_script=script,
            status="pending",
        )
    )
    await db.commit()
    await db.refresh(session)

    try:
        resp = await orchestrator_client.create_pod(
            user_id=current_user.sub,
            plan=plan.value,
            image=image,
            cpu=resources["cpu"],
            memory=resources["memory"],
            pod_id=pod_id,
            labels=agent_runtime.build_agent_pod_env(pod_id, agent_key),
        )
        session.state = resp.state
        session.pod_name = resp.id
        session.ssh_port = resp.ssh_port or None
        session.vscode_port = resp.vscode_port or None
        session.ssh_password = resp.ssh_password or None
        await db.commit()
        await db.refresh(session)
    except Exception as e:  # noqa: BLE001 - mirror POST /pods failure handling
        logger.error("Agent VM launch failed for %s (%s): %s", pod_id, agent_key, e)
        session.state = "failed"
        await db.commit()
        await db.refresh(session)

    return LaunchResponse(agent=agent_key, pod_id=pod_id, state=session.state, image=image)


def _require_admin(current_user: TokenPayload) -> None:
    if current_user.role not in ("admin", "professor"):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/telemetry/latest")
async def telemetry_latest(current_user: TokenPayload = Depends(get_current_user)):
    _require_admin(current_user)
    from app.agents import telemetry_agent

    return telemetry_agent.latest() or {"status": "no telemetry run yet"}


@router.post("/telemetry/run")
@limiter.limit("6/minute")
async def telemetry_run(
    request: Request,
    response: Response,
    notify: bool = False,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a telemetry cycle now. With ``notify=true`` also deliver the report to
    the caller's own saved alert channels regardless of severity — so an admin
    can confirm the email/Telegram pipeline end-to-end even on a healthy system
    (the scheduled runs still only alert on threshold breaches)."""
    _require_admin(current_user)
    from app.agents import telemetry_agent

    result = await telemetry_agent.run_once()

    if notify:
        from app.agents.alerting import dispatch_alert
        from app.models.alert_subscription import AlertSubscription

        row = await db.get(AlertSubscription, current_user.sub)
        emails: list[str] = []
        numbers: list[str] = []
        if row:
            if row.email_enabled and (row.email_address or current_user.email):
                emails.append(row.email_address or current_user.email or "")
            if row.telegram_enabled and row.telegram_number:
                numbers.append(row.telegram_number)
        if emails or numbers:
            subject = f"[Hopper {str(result.get('severity', 'info')).upper()}] telemetry report"
            result["notified"] = await dispatch_alert(
                subject, result.get("report", "Telemetry report"),
                emails=emails, telegram_numbers=numbers,
            )
        else:
            result["notified"] = {"status": "no_channels"}

    return result
