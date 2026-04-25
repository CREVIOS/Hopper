import logging
import uuid
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
import asyncssh

from app.dependencies import get_current_user, get_db
from app.models.session import PodSession
from app.schemas.pod import CreatePodRequest, PodResponse, VM_PLAN_RESOURCES
from app.schemas.user import TokenPayload
from app.services.credit_service import get_balance
from app.services.orchestrator_client import orchestrator_client

logger = logging.getLogger(__name__)
router = APIRouter()


def _session_to_response(s: PodSession) -> PodResponse:
    return PodResponse(
        id=s.id,
        user_id=s.user_id,
        state=s.state,
        plan=s.plan,
        image=s.image,
        cpu=s.cpu,
        memory=s.memory,
        namespace=s.namespace,
        ssh_port=s.ssh_port,
        created_at=s.started_at,
        updated_at=s.updated_at,
    )


@router.get("/plans")
async def list_plans():
    """List available VM plans with their resource allocations and pricing."""
    return {
        plan.value: {
            "cpu": res["cpu"],
            "memory": res["memory"],
            "disk": res["disk"],
            "credits_per_hour": res["credits_per_hour"],
        }
        for plan, res in VM_PLAN_RESOURCES.items()
    }


@router.get("/", response_model=list[PodResponse])
async def list_pods(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List VMs for the current user."""
    result = await db.execute(
        select(PodSession)
        .where(PodSession.user_id == current_user.sub)
        .order_by(PodSession.started_at.desc())
    )
    sessions = result.scalars().all()
    return [_session_to_response(s) for s in sessions]


@router.post("/", response_model=PodResponse, status_code=status.HTTP_201_CREATED)
async def create_pod(
    request: CreatePodRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new VM instance.

    This allocates a slice of the host machine's CPU/RAM to the user as an
    isolated container with SSH access. Resources are capped by the chosen plan.
    """
    # Check credit balance — need at least 1 hour's worth
    resources = VM_PLAN_RESOURCES[request.plan]
    balance = await get_balance(db, current_user.sub)
    if balance < resources["credits_per_hour"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Need {resources['credits_per_hour']}, have {balance:.2f}",
        )

    # Check max concurrent pods per user (limit to 3)
    active_result = await db.execute(
        select(PodSession).where(
            PodSession.user_id == current_user.sub,
            PodSession.state.in_(["pending", "creating", "running"]),
        )
    )
    active_pods = active_result.scalars().all()
    if len(active_pods) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum 3 concurrent VMs allowed",
        )

    pod_id = str(uuid.uuid4())
    namespace = "hopper"

    session = PodSession(
        id=pod_id,
        user_id=current_user.sub,
        plan=request.plan.value,
        image=request.image,
        cpu=resources["cpu"],
        memory=resources["memory"],
        namespace=namespace,
        pod_name=f"vm-{pod_id[:8]}",
        state="pending",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # Call orchestrator to create the actual K8s pod
    try:
        resp = await orchestrator_client.create_pod(
            user_id=current_user.sub,
            plan=request.plan.value,
            image=request.image,
            cpu=resources["cpu"],
            memory=resources["memory"],
        )
        session.state = resp.state
        session.ssh_port = resp.ssh_port if resp.ssh_port else None
        await db.commit()
        await db.refresh(session)
    except Exception as e:
        logger.error("Orchestrator CreatePod failed: %s", e)
        session.state = "failed"
        await db.commit()
        await db.refresh(session)

    return _session_to_response(session)


@router.get("/{pod_id}", response_model=PodResponse)
async def get_pod(
    pod_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get VM details."""
    result = await db.execute(
        select(PodSession).where(PodSession.id == pod_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="VM not found")
    if session.user_id != current_user.sub:
        raise HTTPException(status_code=403, detail="Not your VM")

    return _session_to_response(session)


@router.delete("/{pod_id}")
async def terminate_pod(
    pod_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Terminate a VM."""
    result = await db.execute(
        select(PodSession).where(PodSession.id == pod_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="VM not found")
    if session.user_id != current_user.sub:
        raise HTTPException(status_code=403, detail="Not your VM")

    # Call orchestrator to delete the K8s pod
    try:
        await orchestrator_client.terminate_pod(session.pod_name)
    except Exception as e:
        logger.error("Orchestrator TerminatePod failed: %s", e)

    session.state = "terminated"
    await db.commit()
    return {"message": "terminated", "pod_id": pod_id}


@router.get("/{pod_id}/metrics")
async def stream_metrics(
    pod_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Stream CPU/RAM metrics via SSE.

    Subscribes to NATS subject `metrics.<pod_id>` and forwards each message
    as a Server-Sent Event. The orchestrator publishes metrics every 5 seconds.
    """
    import asyncio
    import json
    from app.core import nats as nats_client

    async def event_generator():
        nc = nats_client.get_nc()
        queue: asyncio.Queue = asyncio.Queue()

        sub = await nc.subscribe(
            f"metrics.{pod_id}",
            cb=lambda msg: queue.put_nowait(msg.data),
        )

        try:
            yield {"event": "connected", "data": json.dumps({"pod_id": pod_id})}
            while True:
                try:
                    raw = await asyncio.wait_for(queue.get(), timeout=30)
                    data = json.loads(raw)
                    yield {"event": "metrics", "data": json.dumps(data)}
                except asyncio.TimeoutError:
                    # Send keepalive to prevent client disconnect
                    yield {"event": "ping", "data": ""}
        finally:
            await sub.unsubscribe()

    return EventSourceResponse(event_generator())


@router.websocket("/{pod_id}/terminal")
async def websocket_terminal(
    websocket: WebSocket,
    pod_id: str,
    db: AsyncSession = Depends(get_db),
    session_token: str | None = Query(None),
):
    """Bridge a WebSocket connection from the browser to an SSH session in the VM."""
    # The browser WS API doesn't send custom headers, but we can read cookies or query parameters.
    token = session_token or websocket.cookies.get("session_token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    from app.middleware.auth import verify_token
    payload = await verify_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    await websocket.accept()

    result = await db.execute(select(PodSession).where(PodSession.id == pod_id))
    session = result.scalar_one_or_none()

    if not session or session.user_id != payload.sub or not session.ssh_port or session.state != "running":
        await websocket.send_text("\\r\\nError: VM is not running, SSH is not available, or forbidden.\\r\\n")
        await websocket.close(code=1008)
        return

    # Connect to the pod via SSH
    host = "localhost"  # Or the actual K8s node IP if running remotely
    port = session.ssh_port
    username = "root"
    password = "hopper"  # Default POC password

    try:
        # Establish SSH connection
        conn = await asyncssh.connect(
            host, port=port, username=username, password=password, known_hosts=None
        )
        
        # Open an interactive SSH session (PTY)
        chan, _ = await conn.create_session(
            asyncssh.SSHClientSession,
            term_type="xterm-256color",
            term_size=(80, 24),
        )

        async def ws_to_ssh():
            try:
                while True:
                    data = await websocket.receive_text()
                    # Handle resize events from xterm fit addon
                    if data.startswith('{"type":"resize"'):
                        try:
                            msg = json.loads(data)
                            chan.change_terminal_size(msg["cols"], msg["rows"])
                        except Exception:
                            pass
                    else:
                        chan.write(data)
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.error(f"WS to SSH error: {e}")

        async def ssh_to_ws():
            try:
                while True:
                    data = await chan.read(8192)
                    if not data:
                        break
                    await websocket.send_text(data)
            except Exception as e:
                logger.error(f"SSH to WS error: {e}")

        # Run bridging tasks concurrently
        await asyncio.gather(
            ws_to_ssh(),
            ssh_to_ws(),
        )

    except Exception as e:
        logger.error(f"SSH bridge failed: {e}")
        await websocket.send_text(f"\\r\\nConnection failed: {e}\\r\\n")
    finally:
        if 'chan' in locals():
            chan.close()
        if 'conn' in locals():
            conn.close()
        try:
            await websocket.close()
        except:
            pass
