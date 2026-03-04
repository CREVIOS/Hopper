from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.dependencies import get_current_user, get_db
from app.schemas.pod import CreatePodRequest, PodResponse
from app.schemas.user import TokenPayload

router = APIRouter()


@router.get("/", response_model=list[PodResponse])
async def list_pods(
    current_user: TokenPayload = Depends(get_current_user),
    db=Depends(get_db),
):
    """List pods for the current user."""
    # TODO: Query pods from DB / orchestrator
    return []


@router.post("/", response_model=PodResponse)
async def create_pod(
    request: CreatePodRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db=Depends(get_db),
):
    """Create a new GPU pod."""
    # TODO: Check credit balance, call orchestrator via gRPC
    pass


@router.get("/{pod_id}", response_model=PodResponse)
async def get_pod(
    pod_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Get pod details."""
    # TODO: Fetch pod status from orchestrator
    pass


@router.delete("/{pod_id}")
async def terminate_pod(
    pod_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Terminate a pod."""
    # TODO: Call orchestrator to terminate
    return {"message": "terminating"}


@router.get("/{pod_id}/metrics")
async def stream_metrics(
    pod_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Stream GPU metrics via SSE."""

    async def event_generator():
        # TODO: Subscribe to NATS metrics subject
        yield {"data": "connected"}

    return EventSourceResponse(event_generator())
