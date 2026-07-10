import pytest

from app.services import port_forward as port_forward_module


class FakeProcess:
    def __init__(self, returncode=None, stderr=b""):
        self.returncode = returncode
        self.stderr = stderr
        self.terminated = False
        self.waited = False

    async def communicate(self):
        return (b"", self.stderr)

    def terminate(self):
        self.terminated = True

    async def wait(self):
        self.waited = True


async def test_start_returns_existing_active_forward():
    proc = FakeProcess(returncode=None)
    port_forward_module._forwards = {("vm-1", 8080): (51000, proc)}

    assert await port_forward_module.start("vm-1", "hopper") == 51000


async def test_start_creates_new_forward_when_ready(monkeypatch):
    fake_proc = FakeProcess(returncode=None)
    port_forward_module._forwards = {}

    monkeypatch.setattr("app.services.port_forward._free_port", lambda: 51000)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return fake_proc

    monkeypatch.setattr("app.services.port_forward.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr("app.services.port_forward.asyncio.sleep", fake_sleep)

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def settimeout(self, timeout):
            self.timeout = timeout

        def connect_ex(self, addr):
            return 0

    monkeypatch.setattr("app.services.port_forward.socket.socket", lambda: FakeSocket())

    result = await port_forward_module.start("vm-1", "hopper", 8080)

    assert result == 51000
    assert port_forward_module._forwards[("vm-1", 8080)][0] == 51000


async def test_start_raises_when_process_exits_early(monkeypatch):
    fake_proc = FakeProcess(returncode=1, stderr=b"bind failed")
    port_forward_module._forwards = {}

    monkeypatch.setattr("app.services.port_forward._free_port", lambda: 51000)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return fake_proc

    monkeypatch.setattr("app.services.port_forward.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    async def fake_sleep(seconds):
        return None

    async def fake_wait_for(coro, timeout):
        return await coro

    monkeypatch.setattr("app.services.port_forward.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.services.port_forward.asyncio.wait_for", fake_wait_for)

    with pytest.raises(RuntimeError) as exc_info:
        await port_forward_module.start("vm-1", "hopper", 8080)

    assert "bind failed" in str(exc_info.value)


async def test_stop_terminates_matching_forward():
    proc = FakeProcess(returncode=None)
    port_forward_module._forwards = {("vm-1", 8080): (51000, proc)}

    await port_forward_module.stop("vm-1", 8080)

    assert proc.terminated is True
    assert proc.waited is True
    assert ("vm-1", 8080) not in port_forward_module._forwards


def test_get_local_port_returns_none_for_stopped_process():
    port_forward_module._forwards = {("vm-1", 8080): (51000, FakeProcess(returncode=1))}

    assert port_forward_module.get_local_port("vm-1", 8080) is None
