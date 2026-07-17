import sys
import types

from app.services import orchestrator_client as orchestrator_module


class FakeChannel:
    def __init__(self):
        self.closed = False

    async def channel_ready(self):
        return None

    async def close(self):
        self.closed = True


async def test_connect_initializes_channel(monkeypatch):
    fake_channel = FakeChannel()

    monkeypatch.setattr("app.services.orchestrator_client.grpc.aio.insecure_channel", lambda url: fake_channel)

    async def fake_wait_for(coro, timeout):
        assert timeout == 45.0
        return await coro

    monkeypatch.setattr("app.services.orchestrator_client.asyncio.wait_for", fake_wait_for)

    client = orchestrator_module.OrchestratorClient()
    await client.connect()

    assert client._channel is fake_channel


async def test_close_closes_channel():
    client = orchestrator_module.OrchestratorClient()
    client._channel = FakeChannel()

    await client.close()

    assert client._channel.closed is True


def _install_fake_proto_modules(monkeypatch, stub_cls, create_request_cls=None, pod_id_cls=None, list_nodes_request_cls=None):
    pod_pb2 = types.SimpleNamespace(
        CreatePodRequest=create_request_cls or (lambda **kwargs: types.SimpleNamespace(**kwargs)),
        PodId=pod_id_cls or (lambda **kwargs: types.SimpleNamespace(**kwargs)),
        ListNodesRequest=list_nodes_request_cls or (lambda: types.SimpleNamespace()),
    )
    pod_pb2_grpc = types.SimpleNamespace(PodOrchestratorStub=stub_cls)

    monkeypatch.setitem(sys.modules, "app.proto.hopper.pod.v1.pod_pb2", pod_pb2)
    monkeypatch.setitem(sys.modules, "app.proto.hopper.pod.v1.pod_pb2_grpc", pod_pb2_grpc)


async def test_create_pod_maps_response(monkeypatch):
    captured = {}

    class FakeStub:
        def __init__(self, channel):
            self.channel = channel

        async def CreatePod(self, req, timeout):
            captured["request"] = req
            captured["timeout"] = timeout
            return types.SimpleNamespace(
                id="vm-1",
                state=3,
                ssh_port=30022,
                vscode_port=30080,
                message="running",
                ssh_password="secret",
            )

    _install_fake_proto_modules(monkeypatch, FakeStub)

    client = orchestrator_module.OrchestratorClient()
    client._channel = object()

    response = await client.create_pod("user-1", "small", "image", "1", "2Gi", pod_id="pod-1")

    assert captured["request"].user_id == "user-1"
    assert captured["request"].pod_id == "pod-1"
    assert captured["timeout"] == 30
    assert response.state == "running"
    assert response.ssh_password == "secret"


async def test_terminate_pod_returns_success(monkeypatch):
    class FakeStub:
        def __init__(self, channel):
            self.channel = channel

        async def TerminatePod(self, req, timeout):
            return types.SimpleNamespace(success=True)

    _install_fake_proto_modules(monkeypatch, FakeStub)

    client = orchestrator_module.OrchestratorClient()
    client._channel = object()

    assert await client.terminate_pod("vm-1") is True


async def test_get_pod_status_maps_unknown_state(monkeypatch):
    class FakeStub:
        def __init__(self, channel):
            self.channel = channel

        async def GetPodStatus(self, req, timeout):
            return types.SimpleNamespace(
                id="vm-1",
                state=99,
                ssh_port=30022,
                vscode_port=30080,
                message="unknown",
                ssh_password="secret",
            )

    _install_fake_proto_modules(monkeypatch, FakeStub)

    client = orchestrator_module.OrchestratorClient()
    client._channel = object()

    response = await client.get_pod_status("vm-1")

    assert response.state == "unknown"


async def test_list_nodes_maps_every_node(monkeypatch):
    class FakeStub:
        def __init__(self, channel):
            self.channel = channel

        async def ListNodes(self, req, timeout):
            return types.SimpleNamespace(
                nodes=[
                    types.SimpleNamespace(
                        name="node-1",
                        cpu_capacity="8",
                        memory_capacity="32Gi",
                        cpu_allocatable="6",
                        memory_allocatable="24Gi",
                        pod_count=4,
                        ready=True,
                    )
                ]
            )

    _install_fake_proto_modules(monkeypatch, FakeStub)

    client = orchestrator_module.OrchestratorClient()
    client._channel = object()

    nodes = await client.list_nodes()

    assert len(nodes) == 1
    assert nodes[0].name == "node-1"
    assert nodes[0].ready is True
