import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.dependencies import get_current_user, get_db
from app.models.session import PodSession
from app.schemas.pod import CreatePodRequest, PodResponse
from app.schemas.user import TokenPayload

router = APIRouter()


@router.get("/", response_model=list[PodResponse])
async def list_pods(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List pods for the current user."""
    result = await db.execute(
        select(PodSession)
        .where(PodSession.user_id == current_user.sub)
        .order_by(PodSession.started_at.desc())
    )
    sessions = result.scalars().all()
    return [
        PodResponse(
            id=s.id,
            user_id=s.user_id,
            state=s.state,
            gpu_tier=s.gpu_tier,
            image=s.image,
            namespace=s.namespace,
            created_at=s.started_at,
            updated_at=s.updated_at,
        )
        for s in sessions
    ]


@router.post("/", response_model=PodResponse, status_code=status.HTTP_201_CREATED)
async def create_pod(
    request: CreatePodRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new GPU pod."""
    pod_id = str(uuid.uuid4())
    namespace = f"hopper-pod-{pod_id[:8]}"

    session = PodSession(
        id=pod_id,
        user_id=current_user.sub,
        gpu_tier=request.gpu_tier.value,
        image=request.image,
        namespace=namespace,
        pod_name=f"pod-{pod_id[:8]}",
        state="pending",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return PodResponse(
        id=session.id,
        user_id=session.user_id,
        state=session.state,
        gpu_tier=session.gpu_tier,
        image=session.image,
        namespace=session.namespace,
        created_at=session.started_at,
        updated_at=session.updated_at,
    )


@router.get("/{pod_id}", response_model=PodResponse)
async def get_pod(
    pod_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get pod details."""
    result = await db.execute(
        select(PodSession).where(PodSession.id == pod_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Pod not found")
    if session.user_id != current_user.sub:
        raise HTTPException(status_code=403, detail="Not your pod")

    return PodResponse(
        id=session.id,
        user_id=session.user_id,
        state=session.state,
        gpu_tier=session.gpu_tier,
        image=session.image,
        namespace=session.namespace,
        created_at=session.started_at,
        updated_at=session.updated_at,
    )


@router.delete("/{pod_id}")
async def terminate_pod(
    pod_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Terminate a pod."""
    result = await db.execute(
        select(PodSession).where(PodSession.id == pod_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Pod not found")
    if session.user_id != current_user.sub:
        raise HTTPException(status_code=403, detail="Not your pod")

    session.state = "stopping"
    await db.commit()
    return {"message": "terminating", "pod_id": pod_id}


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
