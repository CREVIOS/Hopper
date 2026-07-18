"""Async gRPC client for the orchestrator service.

Uses grpcio directly. In production you'd import generated stubs from
generate_proto.sh — this thin wrapper keeps the POC working without
requiring a proto compilation step during development.
"""

import asyncio
import logging
from dataclasses import dataclass

import grpc
import grpc.aio

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PodStatusResponse:
    id: str
    state: str
    ssh_port: int
    vscode_port: int
    message: str
    ssh_password: str = ""


@dataclass
class NodeInfoResponse:
    name: str
    cpu_capacity: str
    memory_capacity: str
    cpu_allocatable: str
    memory_allocatable: str
    pod_count: int
    ready: bool


# Proto state enum value → string
_STATE_MAP = {
    0: "unspecified",
    1: "pending",
    2: "creating",
    3: "running",
    4: "stopping",
    5: "terminated",
    6: "failed",
}


class OrchestratorClient:
    """Async gRPC client wrapping the PodOrchestrator service."""

    def __init__(self):
        self._channel: grpc.aio.Channel | None = None

    async def connect(self):
        self._channel = grpc.aio.insecure_channel(settings.orchestrator_url)
        # Do not block startup indefinitely: during rolling deploys the new API pod
        # can come up before orchestrator is ready; /healthz is unreachable until lifespan
        # finishes, so aggressive probes see connection refused and kill the container.
        try:
            await asyncio.wait_for(self._channel.channel_ready(), timeout=45.0)
            logger.info("Connected to orchestrator at %s", settings.orchestrator_url)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning(
                "Orchestrator not ready at %s (%s); continuing startup (retries on first call)",
                settings.orchestrator_url,
                exc,
            )

    async def close(self):
        if self._channel:
            await self._channel.close()

    async def create_pod(
        self,
        user_id: str,
        plan: str,
        image: str,
        cpu: str,
        memory: str,
        disk: str = "",
        pod_id: str = "",
        labels: dict[str, str] | None = None,
    ) -> PodStatusResponse:
        """Call orchestrator.CreatePod and return the response.

        ``labels`` carries per-pod key/value pairs to the orchestrator via the
        proto ``labels`` map. Keys prefixed ``HOPPER_`` are promoted to container
        env vars (not k8s labels) by the orchestrator — this is how the in-VM
        provisioner receives HOPPER_POD_ID / HOPPER_API_URL / HOPPER_POD_TOKEN.
        """
        # Import generated stubs (available after generate_proto.sh)
        from app.proto.hopper.pod.v1 import pod_pb2, pod_pb2_grpc

        stub = pod_pb2_grpc.PodOrchestratorStub(self._channel)
        req = pod_pb2.CreatePodRequest(
            user_id=user_id,
            plan=plan,
            image=image,
            cpu=cpu,
            memory=memory,
            disk=disk,
            pod_id=pod_id,
            labels=labels or {},
        )
        resp = await stub.CreatePod(req, timeout=30)
        return PodStatusResponse(
            id=resp.id,
            state=_STATE_MAP.get(resp.state, "unknown"),
            ssh_port=resp.ssh_port,
            vscode_port=resp.vscode_port,
            message=resp.message,
            ssh_password=resp.ssh_password,
        )

    async def terminate_pod(self, pod_id: str) -> bool:
        from app.proto.hopper.pod.v1 import pod_pb2, pod_pb2_grpc

        stub = pod_pb2_grpc.PodOrchestratorStub(self._channel)
        req = pod_pb2.PodId(id=pod_id)
        resp = await stub.TerminatePod(req, timeout=30)
        return resp.success

    async def get_pod_status(self, pod_id: str) -> PodStatusResponse:
        from app.proto.hopper.pod.v1 import pod_pb2, pod_pb2_grpc

        stub = pod_pb2_grpc.PodOrchestratorStub(self._channel)
        req = pod_pb2.PodId(id=pod_id)
        resp = await stub.GetPodStatus(req, timeout=10)
        return PodStatusResponse(
            id=resp.id,
            state=_STATE_MAP.get(resp.state, "unknown"),
            ssh_port=resp.ssh_port,
            vscode_port=resp.vscode_port,
            message=resp.message,
            ssh_password=resp.ssh_password,
        )

    async def list_nodes(self) -> list[NodeInfoResponse]:
        from app.proto.hopper.pod.v1 import pod_pb2, pod_pb2_grpc

        stub = pod_pb2_grpc.PodOrchestratorStub(self._channel)
        req = pod_pb2.ListNodesRequest()
        resp = await stub.ListNodes(req, timeout=10)
        return [
            NodeInfoResponse(
                name=n.name,
                cpu_capacity=n.cpu_capacity,
                memory_capacity=n.memory_capacity,
                cpu_allocatable=n.cpu_allocatable,
                memory_allocatable=n.memory_allocatable,
                pod_count=n.pod_count,
                ready=n.ready,
            )
            for n in resp.nodes
        ]


# Singleton — initialized in app lifespan
orchestrator_client = OrchestratorClient()
