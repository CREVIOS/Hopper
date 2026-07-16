import asyncio
import json
import logging
import uuid

import httpx
import websockets
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
import asyncssh

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import get_current_user, get_db
from app.models.session import PodSession
from app.models.vm_queue_entry import VmQueueEntry
from app.schemas.pod import CreatePodRequest, PodResponse, VM_PLAN_RESOURCES
from app.schemas.user import TokenPayload
from app.middleware.auth import verify_token
from app.services.credit_service import get_balance
from app.services.notification_service import notify
from app.services.orchestrator_client import orchestrator_client
from app.services import port_forward, vm_queue, vm_scheduler

logger = logging.getLogger(__name__)
router = APIRouter()

# Live PodSession states that occupy real cluster capacity (mirrors the
# per-user concurrency check below and vm_scheduler._LIVE_VM_STATES).
_LIVE_VM_STATES = ("pending", "creating", "running")
# Queue entry states that still hold a slot (mirrors vm_queue._LIVE_QUEUE_STATES).
_LIVE_QUEUE_STATES = ("queued", "admitting")
_BYTES_PER_GIB = 1024**3


def _session_to_response(s: PodSession) -> PodResponse:
    # Only surface live connection details for running pods. Once a pod is
    # stopped or terminated, its NodePort is released and may be reassigned,
    # so leaking the stale port leads users to dial a black hole (or worse,
    # someone else's pod).
    is_live = s.state == "running"
    return PodResponse(
        id=s.id,
        user_id=s.user_id,
        state=s.state,
        plan=s.plan,
        image=s.image,
        cpu=s.cpu,
        memory=s.memory,
        namespace=s.namespace,
        ssh_port=s.ssh_port if is_live else None,
        vscode_port=s.vscode_port if is_live else None,
        ssh_password=s.ssh_password if is_live else None,
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
@limiter.limit("10/minute")
async def create_pod(
    request: Request,
    response: Response,
    body: CreatePodRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new VM instance.

    This allocates a slice of the host machine's CPU/RAM to the user as an
    isolated container with SSH access. Resources are capped by the chosen plan.
    """
    # Check credit balance — need at least 1 hour's worth
    resources = VM_PLAN_RESOURCES[body.plan]
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

    # Cluster admission fork. The reservation is serialized under a DB advisory
    # lock (reserve_sync_slot), so two concurrent creates can never both take the
    # last slot. If the cluster has room AND nobody is already waiting, reserve a
    # slot and create synchronously as before. Otherwise enqueue and return 202.
    # If capacity cannot be computed (orchestrator unreachable) we fail OPEN and
    # create synchronously so the queue never makes us worse than today.
    image = body.resolved_image()
    nodes = await vm_scheduler.fetch_nodes(orchestrator_client)

    pod_id: str | None = None
    if nodes is not None:
        pod_id = await vm_scheduler.reserve_sync_slot(
            db, nodes, current_user.sub, body.plan.value, image,
            resources["cpu"], resources["memory"],
        )
        if pod_id is None:
            # Cluster full, or someone is already waiting -> join the queue.
            try:
                entry = await vm_queue.enqueue_vm_request(
                    db, current_user, body.plan.value, body.template
                )
            except vm_queue.EnqueueError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
            position = await vm_queue.queue_position(db, entry)
            vm_scheduler.nudge()
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "id": entry.id,
                    "state": entry.state,
                    "plan": entry.plan,
                    "position": position,
                    "queued": True,
                },
            )

    # Synchronous create: either a reserved fast-path slot (pod_id set under the
    # lock) or fail-open (orchestrator unreachable -> no capacity gate, as today).
    if pod_id is None:
        pod_id = str(uuid.uuid4())
        session = PodSession(
            id=pod_id,
            user_id=current_user.sub,
            plan=body.plan.value,
            image=image,
            cpu=resources["cpu"],
            memory=resources["memory"],
            namespace="hopper",
            pod_name=f"vm-{pod_id[:8]}",
            state="pending",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
    else:
        session = await db.get(PodSession, pod_id)  # the reserved pending row

    # Call orchestrator to create the actual K8s pod
    try:
        resp = await orchestrator_client.create_pod(
            user_id=current_user.sub,
            plan=body.plan.value,
            image=image,
            cpu=resources["cpu"],
            memory=resources["memory"],
            pod_id=pod_id,
        )
        session.state = resp.state
        session.pod_name = resp.id  # use the actual K8s pod name from orchestrator
        session.ssh_port = resp.ssh_port if resp.ssh_port else None
        session.vscode_port = resp.vscode_port if resp.vscode_port else None
        session.ssh_password = resp.ssh_password or None
        await db.commit()
        await db.refresh(session)
    except Exception as e:
        logger.error("Orchestrator CreatePod failed: %s", e)
        session.state = "failed"
        await db.commit()
        await db.refresh(session)
        # This path owns the failure notification — the pod.failed NATS
        # consumer deliberately only repairs state (see notification_service).
        try:
            await notify(
                db,
                current_user.sub,
                type_="error",
                title="VM failed to create",
                body="Something went wrong while provisioning your VM. "
                     "Try again, or contact an admin if it keeps failing.",
                data={"pod_id": session.id},
            )
        except Exception:
            logger.exception("failed to record VM-creation-failure notification")

    return _session_to_response(session)


# NOTE: these static routes MUST be declared before "/{pod_id}" so that
# "/availability" and "/queue" are not captured by the pod_id path parameter.
@router.get("/availability")
async def get_availability(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Best-effort cluster capacity readout for the VM create UI.

    Never 500s: if the orchestrator is unreachable the capacity fields come
    back null while the queue length (read straight from the DB) stays real.
    """
    queue_length = await vm_queue.live_queue_count(db)

    try:
        nodes = await orchestrator_client.list_nodes()
        nodes_ready = sum(1 for n in nodes if n.ready)
    except Exception as exc:
        logger.warning("Availability: ListNodes failed: %s", exc)
        nodes_ready = None

    cap = await vm_scheduler.current_capacity(db, orchestrator_client)
    if cap is None:
        return {
            "cpu": {"total_cores": None, "used_cores": None, "free_cores": None},
            "memory": {"total_gib": None, "used_gib": None, "free_gib": None},
            "storage": {"total_gib": None, "used_gib": None, "free_gib": None},
            "nodes_ready": nodes_ready,
            "queue_length": queue_length,
        }

    # "used" is derived as total - free so the three values always reconcile
    # (it folds in both live-VM requests and the system reserve).
    free_cpu_m = cap.free_cpu_m()
    free_mem_b = cap.free_mem_b()
    free_storage_b = cap.free_storage_b()
    return {
        "cpu": {
            "total_cores": round(cap.total_cpu_m / 1000, 2),
            "used_cores": round((cap.total_cpu_m - free_cpu_m) / 1000, 2),
            "free_cores": round(free_cpu_m / 1000, 2),
        },
        "memory": {
            "total_gib": round(cap.total_mem_b / _BYTES_PER_GIB, 2),
            "used_gib": round((cap.total_mem_b - free_mem_b) / _BYTES_PER_GIB, 2),
            "free_gib": round(free_mem_b / _BYTES_PER_GIB, 2),
        },
        # Workspace-disk pool (configured total; used = sum of live VMs' plan disk).
        "storage": {
            "total_gib": round(cap.total_storage_b / _BYTES_PER_GIB, 2),
            "used_gib": round((cap.total_storage_b - free_storage_b) / _BYTES_PER_GIB, 2),
            "free_gib": round(free_storage_b / _BYTES_PER_GIB, 2),
        },
        "nodes_ready": nodes_ready,
        "queue_length": queue_length,
    }


@router.get("/queue")
async def list_queue(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's own pending queue entries (queued/admitting)."""
    result = await db.execute(
        select(VmQueueEntry)
        .where(
            VmQueueEntry.user_id == current_user.sub,
            VmQueueEntry.state.in_(_LIVE_QUEUE_STATES),
        )
        .order_by(VmQueueEntry.seq.asc())
    )
    entries = result.scalars().all()
    return [
        {
            "id": entry.id,
            "plan": entry.plan,
            "template": entry.template,
            "state": entry.state,
            "position": await vm_queue.queue_position(db, entry),
            "created_at": entry.created_at,
        }
        for entry in entries
    ]


@router.delete("/queue/{entry_id}")
async def cancel_queue_entry(
    entry_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a still-queued VM request owned by the caller.

    Only a 'queued' entry can be cancelled: once it is 'admitting' the
    orchestrator create is already in flight, so we refuse with 409.
    """
    result = await db.execute(
        select(VmQueueEntry).where(VmQueueEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    if entry.user_id != current_user.sub:
        raise HTTPException(status_code=403, detail="Not your queue entry")
    if entry.state != "queued":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel a queue entry in state '{entry.state}'",
        )

    entry.state = "cancelled"
    await db.commit()
    # Freeing a queue slot may let a smaller entry behind it fit (once the
    # head clears); nudge the loop to re-evaluate.
    vm_scheduler.nudge()
    return {"message": "cancelled", "id": entry_id}


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

    # Commit the terminal state BEFORE calling the orchestrator: its
    # pod.stopped event races this handler, and the notification consumer
    # uses "row already terminated" to tell a user-initiated delete (no
    # notification — the user is watching the response) from an unexpected
    # one. The orchestrator call failing doesn't change the outcome — this
    # endpoint has always marked the row terminated regardless.
    session.state = "terminated"
    await db.commit()

    # Call orchestrator to delete the K8s pod
    try:
        await orchestrator_client.terminate_pod(session.pod_name)
    except Exception as e:
        logger.error("Orchestrator TerminatePod failed: %s", e)

    # Stop the port-forward if running
    await port_forward.stop(session.pod_name)

    # Freed capacity may now admit the next queued VM. Nudge the local loop;
    # the orchestrator's pod.stopped NATS event covers the cross-worker case.
    # (The terminated state itself was committed above, BEFORE the
    # orchestrator call, so the notification consumer can tell user-initiated
    # deletes from unexpected ones.)
    vm_scheduler.nudge()
    return {"message": "terminated", "pod_id": pod_id}


@router.get("/{pod_id}/metrics")
async def stream_metrics(
    pod_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream CPU/RAM metrics via SSE.

    The orchestrator publishes metrics on subject ``metrics.<pod_name>`` where
    pod_name is the orchestrator-side identifier (``vm-<unix_nano>``), not the
    API UUID we use in URLs. We resolve session.pod_name here so the
    subscription actually matches what's being published.
    """
    import asyncio
    import json
    from app.core import nats as nats_client

    result = await db.execute(select(PodSession).where(PodSession.id == pod_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != current_user.sub:
        raise HTTPException(status_code=404, detail="VM not found")
    subject_id = session.pod_name or pod_id

    async def event_generator():
        nc = nats_client.get_nc()
        queue: asyncio.Queue = asyncio.Queue()

        async def _on_msg(msg):
            await queue.put(msg.data)

        sub = await nc.subscribe(f"metrics.{subject_id}", cb=_on_msg)

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
    db: AsyncSession = Depends(get_db),
):
    # Auth is inlined (instead of Depends(get_current_user)) so that a
    # top-level navigation with a missing/expired session cookie redirects
    # to /login instead of returning a JSON 401. Without that, the browser
    # opens VS Code in a new tab and shows a blank "loading" screen until
    # the user gives up and closes it.
    token = request.cookies.get("session_token")
    current_user = await verify_token(token) if token else None
    if current_user is None:
        accept = request.headers.get("accept", "")
        if "text/html" in accept and request.method == "GET":
            from urllib.parse import quote
            return_to = request.url.path
            if request.url.query:
                return_to += f"?{request.url.query}"
            return RedirectResponse(
                url=f"{settings.frontend_url}/login?return_to={quote(return_to, safe='')}",
                status_code=302,
            )
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(select(PodSession).where(PodSession.id == pod_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="VM not found")
    if session.user_id != current_user.sub:
        raise HTTPException(status_code=403, detail="Not your VM")

    if session.state != "running":
        # Pod still starting / stopped — the user-facing 503 was confusing
        # because the gateway didn't disambiguate "no pod" from "pod still
        # warming up". Tell the browser to retry shortly.
        raise HTTPException(
            status_code=503,
            detail=f"VM is {session.state} — VS Code will be available once running.",
            headers={"Retry-After": "5"},
        )

    if session.state != "running":
        # Pod still starting / stopped — the user-facing 503 was confusing
        # because the gateway didn't disambiguate "no pod" from "pod still
        # warming up". Tell the browser to retry shortly.
        raise HTTPException(
            status_code=503,
            detail=f"VM is {session.state} — VS Code will be available once running.",
            headers={"Retry-After": "5"},
        )

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
    else:
        raise HTTPException(
            status_code=503,
            detail="VS Code not available yet — port-forward failed and no NodePort configured.",
            headers={"Retry-After": "5"},
        )

    target_url = f"{target_base}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    logger.debug("vscode proxy %s -> %s", pod_id[:8], target_url)

    # code-server may take a few seconds to bind to :8080 even after the pod
    # is "running". Retry a connect-failed request once after a short pause so
    # the browser doesn't show a 503 on the very first navigation.
    body = await request.body()
    forwarded_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "connection", "accept-encoding")
    }
    last_err: Exception | None = None
    resp = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Redirects must pass through to the browser, not be resolved
                # here: code-server's login success is a 302 whose Set-Cookie
                # carries the session. Following it server-side swallows the
                # cookie, so the browser never authenticates and every request
                # after login 401s. code-server's Locations are relative, so
                # they resolve correctly against the browser's
                # /{userId}/code/{podId}/ URL.
                resp = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=forwarded_headers,
                    content=body,
                    follow_redirects=False,
                )
            break
        except httpx.ConnectError as e:
            last_err = e
            if attempt == 0:
                await asyncio.sleep(1.0)
                continue
    if resp is None:
        logger.warning("vscode proxy connect failed for pod %s: %s", pod_id[:8], last_err)
        raise HTTPException(
            status_code=503,
            detail="code-server is not ready yet — please retry in a moment.",
            headers={"Retry-After": "3"},
        )

    # Strip headers that would break the browser when served from a different origin.
    # content-encoding must be removed because httpx decompresses the body transparently —
    # forwarding the original gzip header with a decoded body causes ERR_CONTENT_DECODING_FAILED.
    excluded_resp_headers = {"transfer-encoding", "connection", "keep-alive", "content-encoding", "set-cookie"}
    headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_resp_headers}

    out = Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=headers,
    )
    # Set-Cookie needs raw multi-header passthrough: a dict collapses repeats,
    # and httpx's items() joins them with ", " — which corrupts cookie values.
    for cookie_header in resp.headers.get_list("set-cookie"):
        out.headers.append("set-cookie", cookie_header)
    return out


@router.websocket("/{pod_id}/vscode/{path:path}")
async def vscode_ws_proxy(
    pod_id: str,
    path: str,
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    """Proxy WebSocket connections from code-server to the pod.

    code-server uses WebSockets for its main RPC channel. We verify the user's
    JWT cookie and pod ownership here too — the connectionToken in the query
    string is code-server's own session value and not a substitute for auth.
    Origin is checked against the configured allowlist.
    """
    token = websocket.cookies.get("session_token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    payload = await verify_token(token)
    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    origin = websocket.headers.get("origin", "")
    if origin and origin not in settings.cors_origins:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    result = await db.execute(select(PodSession).where(PodSession.id == pod_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != payload.sub or session.state != "running":
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
        # Forward the browser's cookies: code-server authenticates its
        # WebSocket with the same code-server-session cookie as HTTP requests,
        # so without this the editor 401s right after login.
        upstream_headers = {"Host": f"127.0.0.1:{local_port}"}
        browser_cookies = websocket.headers.get("cookie")
        if browser_cookies:
            upstream_headers["Cookie"] = browser_cookies
        async with websockets.connect(
            target_url,
            additional_headers=upstream_headers,
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
    allowed = settings.cors_origins
    if "*" not in allowed and origin not in allowed:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    result = await db.execute(select(PodSession).where(PodSession.id == pod_id))
    session = result.scalar_one_or_none()

    if not session or session.user_id != payload.sub or not session.ssh_port or session.state != "running":
        await _safe_send(websocket, "\r\nError: VM is not running, SSH is not available, or forbidden.\r\n")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # SSH NodePort isn't reachable from the api-gateway under the minikube
    # docker driver (or most kind setups), so prefer a kubectl port-forward
    # into the pod's sshd on port 22 — matching the path VS Code already takes.
    # Fall back to the NodePort on bare-metal clusters where it does work.
    host: str | None = None
    port: int | None = None
    if session.pod_name:
        host = "127.0.0.1"
        port = port_forward.get_local_port(session.pod_name, 22)
        if not port:
            try:
                port = await port_forward.start(session.pod_name, session.namespace, 22)
            except Exception as pf_err:
                logger.warning(
                    "ssh port-forward unavailable for %s: %s — falling back to NodePort",
                    session.pod_name, pf_err,
                )
                host = port = None
    if port is None:
        if not session.ssh_port:
            await _safe_send(websocket, "\r\nVM has no SSH endpoint yet — please retry.\r\n")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return
        host = settings.node_ip
        port = session.ssh_port
    username = "root"
    # Per-pod password generated by the orchestrator at create time. Refuse
    # to connect if the pod predates the 009 migration (no per-pod password)
    # — the previous global "hopper" fallback let any caller into any pod.
    if not session.ssh_password:
        await _safe_send(
            websocket,
            "\r\nThis VM was created with an older orchestrator and has no SSH credential. "
            "Recreate the VM to enable the in-browser terminal.\r\n",
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    password = session.ssh_password

    # Limits — protect the gateway from DoS via giant frames or stalled PTYs.
    MAX_INPUT_BYTES = 64 * 1024  # one keystroke or paste, capped
    IDLE_TIMEOUT_S = 600         # close after 10 min of no output activity

    conn = process = None
    last_output_at = asyncio.get_event_loop().time()

    try:
        # NOTE: known_hosts=None is acceptable only because the SSH endpoint is
        # reached via the K8s node IP from inside the cluster. If the gateway
        # ever runs off-cluster, switch to verifying a per-pod host key
        # captured at VM boot and stored alongside the SSH password.
        conn = await asyncssh.connect(
            host, port=port, username=username, password=password, known_hosts=None
        )

        process = await conn.create_process(
            term_type="xterm-256color",
            term_size=(80, 24),
        )

        # Bounded queue between the SSH PTY and the WebSocket. If the browser
        # is slow, the queue fills and `put` blocks the SSH-reader, providing
        # natural backpressure rather than memory growth.
        out_queue: asyncio.Queue[bytes | str] = asyncio.Queue(maxsize=64)

        async def ws_to_ssh():
            while True:
                msg_text = await websocket.receive_text()
                if len(msg_text) > MAX_INPUT_BYTES:
                    logger.warning(
                        "Oversized terminal input from pod %s (%d bytes) — closing",
                        pod_id, len(msg_text),
                    )
                    await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                    return
                if msg_text.startswith('{"type":"resize"'):
                    try:
                        msg = json.loads(msg_text)
                        cols = max(1, min(1000, int(msg["cols"])))
                        rows = max(1, min(1000, int(msg["rows"])))
                        process.change_terminal_size(cols, rows)
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning("Invalid resize from pod %s: %s", pod_id, e)
                    except OSError:
                        logger.error("PTY resize failed pod=%s", pod_id, exc_info=True)
                        raise
                elif msg_text.startswith('{"type":"ping"'):
                    # Browser heartbeat. Discard.
                    pass
                else:
                    process.stdin.write(msg_text)

        async def ssh_reader():
            while True:
                data = await process.stdout.read(8192)
                if not data:
                    break
                await out_queue.put(data)

        async def ws_writer():
            nonlocal last_output_at
            while True:
                try:
                    data = await asyncio.wait_for(out_queue.get(), timeout=IDLE_TIMEOUT_S)
                except asyncio.TimeoutError:
                    logger.info("Terminal idle timeout pod=%s", pod_id)
                    await _safe_send(
                        websocket,
                        "\r\nSession closed after 10 minutes of inactivity.\r\n",
                    )
                    return
                last_output_at = asyncio.get_event_loop().time()
                if isinstance(data, bytes):
                    await websocket.send_bytes(data)
                else:
                    await websocket.send_text(data)

        tasks = [
            asyncio.create_task(ws_to_ssh()),
            asyncio.create_task(ssh_reader()),
            asyncio.create_task(ws_writer()),
        ]
        # Audit-log session open with timing — never the actual data stream.
        logger.info("terminal_open pod=%s user=%s", pod_id, payload.sub)
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("terminal_close pod=%s user=%s", pod_id, payload.sub)

    except asyncssh.PermissionDenied:
        logger.error("SSH auth failed pod=%s", pod_id, exc_info=True)
        await _safe_send(websocket, "\r\nVM authentication failed. Please retry.\r\n")
    except (asyncssh.ConnectionLost, OSError) as e:
        logger.error("SSH connect failed pod=%s: %s", pod_id, e, exc_info=True)
        await _safe_send(websocket, "\r\nVM is unreachable — please retry shortly.\r\n")
    except Exception:
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
