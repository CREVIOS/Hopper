import asyncio
import logging
import uuid
import json

import httpx
import websockets
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
import asyncssh

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.session import PodSession
from app.schemas.pod import CreatePodRequest, PodResponse, VM_PLAN_RESOURCES
from app.schemas.user import TokenPayload
from app.middleware.auth import verify_token
from app.services.credit_service import get_balance
from app.services.orchestrator_client import orchestrator_client
from app.services import port_forward

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
        vscode_port=s.vscode_port,
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
        session.pod_name = resp.id  # use the actual K8s pod name from orchestrator
        session.ssh_port = resp.ssh_port if resp.ssh_port else None
        session.vscode_port = resp.vscode_port if resp.vscode_port else None
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

    # Stop the port-forward if running
    await port_forward.stop(session.pod_name)

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

        async def _on_msg(msg):
            await queue.put(msg.data)

        sub = await nc.subscribe(f"metrics.{pod_id}", cb=_on_msg)

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


async def _safe_send(websocket: WebSocket, text: str):
    """Send text over a websocket that may already be closed."""
    try:
        await websocket.send_text(text)
    except (WebSocketDisconnect, RuntimeError):
        pass


@router.api_route("/{pod_id}/vscode/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def vscode_proxy(
    pod_id: str,
    path: str,
    request: Request,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PodSession).where(PodSession.id == pod_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != current_user.sub:
        raise HTTPException(status_code=403)

    # Get or (re)start the kubectl port-forward — needed for minikube Docker driver
    # where NodePorts are not reachable from the host directly.
    local_port = port_forward.get_local_port(session.pod_name)
    if not local_port:
        try:
            local_port = await port_forward.start(session.pod_name, session.namespace)
        except Exception as pf_err:
            logger.warning("port-forward unavailable for %s: %s", session.pod_name, pf_err)

    if local_port:
        target_base = f"http://127.0.0.1:{local_port}"
    elif session.vscode_port:
        # Fallback: direct NodePort (works in bare-metal K8s, not minikube Docker driver)
        target_base = f"http://{settings.node_ip}:{session.vscode_port}"
    else:
        raise HTTPException(status_code=503, detail="VS Code not available yet — pod may still be starting")

    target_url = f"{target_base}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    logger.debug("vscode proxy %s -> %s", pod_id[:8], target_url)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers={k: v for k, v in request.headers.items() if k.lower() not in ("host", "connection", "accept-encoding")},
                content=await request.body(),
                follow_redirects=True,
            )
    except httpx.ConnectError as e:
        logger.warning("vscode proxy connect failed for pod %s: %s", pod_id[:8], e)
        raise HTTPException(status_code=502, detail="Cannot reach VS Code — is code-server running inside the pod?")

    # Strip headers that would break the browser when served from a different origin.
    # content-encoding must be removed because httpx decompresses the body transparently —
    # forwarding the original gzip header with a decoded body causes ERR_CONTENT_DECODING_FAILED.
    excluded_resp_headers = {"transfer-encoding", "connection", "keep-alive", "content-encoding"}
    headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_resp_headers}

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=headers,
    )


@router.websocket("/{pod_id}/vscode/{path:path}")
async def vscode_ws_proxy(
    pod_id: str,
    path: str,
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    """Proxy WebSocket connections from code-server to the pod.

    code-server uses WebSockets for its main RPC channel. Auth is intentionally
    skipped here — the HTTP page load already verified ownership, and the
    connectionToken in the query string is code-server's own session token.
    """
    result = await db.execute(select(PodSession).where(PodSession.id == pod_id))
    session = result.scalar_one_or_none()
    if not session or session.state != "running":
        await websocket.close(code=1008)
        return

    local_port = port_forward.get_local_port(session.pod_name)
    if not local_port:
        try:
            local_port = await port_forward.start(session.pod_name, session.namespace)
        except Exception:
            await websocket.close(code=1011)
            return

    qs = websocket.url.query
    target_url = f"ws://127.0.0.1:{local_port}/{path}"
    if qs:
        target_url += f"?{qs}"

    await websocket.accept()

    try:
        async with websockets.connect(
            target_url,
            additional_headers={"Host": f"127.0.0.1:{local_port}"},
            ping_interval=20,
            ping_timeout=20,
        ) as ws_upstream:
            async def client_to_upstream():
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if "bytes" in msg and msg["bytes"]:
                            await ws_upstream.send(msg["bytes"])
                        elif "text" in msg and msg["text"]:
                            await ws_upstream.send(msg["text"])
                except Exception:
                    pass

            async def upstream_to_client():
                try:
                    async for msg in ws_upstream:
                        if isinstance(msg, bytes):
                            await websocket.send_bytes(msg)
                        else:
                            await websocket.send_text(msg)
                except Exception:
                    pass

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except Exception as e:
        logger.debug("vscode ws proxy closed for %s: %s", pod_id[:8], e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
@router.websocket("/{pod_id}/terminal")
async def websocket_terminal(
    websocket: WebSocket,
    pod_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Bridge a WebSocket connection from the browser to an SSH session in the VM.
    Enforces ownership, state (running), authentication (cookie), and origin controls.
    """
    token = websocket.cookies.get("session_token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    payload = await verify_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    origin = websocket.headers.get("origin", "")
    if origin not in settings.cors_origins:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    result = await db.execute(select(PodSession).where(PodSession.id == pod_id))
    session = result.scalar_one_or_none()

    if not session or session.user_id != payload.sub or not session.ssh_port or session.state != "running":
        await _safe_send(websocket, "\r\nError: VM is not running, SSH is not available, or forbidden.\r\n")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    host = "localhost"  # Or the actual K8s node IP if running remotely
    port = session.ssh_port
    username = "root"
    # TODO(HOP-XX): replace with per-pod ephemeral key/cert injected at provisioning.
    password = "hopper"

    conn = process = None
    try:
        # known_hosts=None disables host-key verification — safe only because the SSH endpoint
        # is reached via in-cluster localhost forwarding which is not externally reachable.
        # MUST be replaced before exposing the gateway off-host.
        conn = await asyncssh.connect(
            host, port=port, username=username, password=password, known_hosts=None
        )
        
        process = await conn.create_process(
            term_type="xterm-256color",
            term_size=(80, 24),
        )

        async def ws_to_ssh():
            try:
                while True:
                    msg_text = await websocket.receive_text()
                    if msg_text.startswith('{"type":"resize"'):
                        try:
                            msg = json.loads(msg_text)
                            cols = max(1, min(1000, int(msg["cols"])))
                            rows = max(1, min(1000, int(msg["rows"])))
                            process.change_terminal_size(cols, rows)
                        except (json.JSONDecodeError, KeyError, ValueError) as e:
                            logger.warning("Invalid resize control frame from pod %s: %s", pod_id, e)
                        except OSError as e:
                            logger.error("Failed to resize SSH PTY for pod %s: %s", pod_id, e)
                            raise
                    else:
                        process.stdin.write(msg_text)
            except WebSocketDisconnect:
                logger.info("Client disconnected from terminal pod=%s", pod_id)
                raise
            except asyncssh.ChannelOpenError:
                logger.error("SSH channel closed mid-stream pod=%s", pod_id, exc_info=True)
                raise
            except Exception as e:
                logger.error("WS to SSH error pod=%s: %s", pod_id, e, exc_info=True)
                raise

        async def ssh_to_ws():
            try:
                while True:
                    data = await process.stdout.read(8192)
                    if not data:
                        break
                    if isinstance(data, bytes):
                        await websocket.send_bytes(data)
                    else:
                        await websocket.send_text(data)
            except (asyncssh.ConnectionLost, asyncssh.DisconnectError):
                logger.info("SSH connection lost or closed pod=%s", pod_id)
                raise
            except Exception as e:
                logger.error("SSH to WS error pod=%s: %s", pod_id, e, exc_info=True)
                raise

        t1 = asyncio.create_task(ws_to_ssh())
        t2 = asyncio.create_task(ssh_to_ws())
        done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    except asyncssh.PermissionDenied:
        logger.error("SSH auth failed pod=%s", pod_id, exc_info=True)
        await _safe_send(websocket, "\r\nVM authentication failed. Please retry.\r\n")
    except (asyncssh.ConnectionLost, OSError) as e:
        logger.error("SSH connect failed pod=%s: %s", pod_id, e, exc_info=True)
        await _safe_send(websocket, "\r\nVM is unreachable — please retry shortly.\r\n")
    except Exception as e:
        logger.exception("Unhandled SSH bridge failure pod=%s", pod_id)
        await _safe_send(websocket, "\r\nUnexpected error occurred while connecting.\r\n")
    finally:
        if process is not None:
            process.close()
        if conn is not None:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:
                logger.exception("conn.wait_closed failed pod=%s", pod_id)
        try:
            await websocket.close()
        except RuntimeError:
            pass
        except Exception:
            logger.exception("Failed closing terminal websocket pod=%s", pod_id)
