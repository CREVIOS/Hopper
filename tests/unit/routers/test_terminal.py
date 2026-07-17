from app.routers.terminal import _set_winsize
from app.routers import terminal as terminal_router


def test_set_winsize_calls_ioctl_with_terminal_size(monkeypatch):
    captured = {}

    def fake_ioctl(fd, op, winsize):
        captured["fd"] = fd
        captured["op"] = op
        captured["winsize"] = winsize

    monkeypatch.setattr("app.routers.terminal.fcntl.ioctl", fake_ioctl)

    _set_winsize(10, 24, 80)

    assert captured["fd"] == 10
    assert len(captured["winsize"]) == 8


class FakeWebSocket:
    def __init__(self, *, cookies=None):
        self.cookies = cookies or {}
        self.closed = []
        self.accepted = False
        self.sent_text = []

    async def close(self, code=None, reason=None):
        self.closed.append((code, reason))

    async def accept(self):
        self.accepted = True

    async def send_text(self, text):
        self.sent_text.append(text)

    async def receive(self):
        return {"type": "websocket.disconnect"}


class FakeExecuteResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class FakeDB:
    def __init__(self, row):
        self.row = row

    async def execute(self, stmt):
        return FakeExecuteResult(self.row)


class FakeDBContext:
    def __init__(self, row):
        self.row = row

    async def __aenter__(self):
        return FakeDB(self.row)

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def test_terminal_ws_rejects_missing_and_invalid_token(monkeypatch):
    ws = FakeWebSocket()
    await terminal_router.terminal_ws(ws, "pod-1")
    assert ws.closed == [(1008, "Not authenticated")]

    async def fake_verify_none(token):
        return None

    monkeypatch.setattr("app.routers.terminal.verify_token", fake_verify_none)
    ws = FakeWebSocket(cookies={"session_token": "tok"})
    await terminal_router.terminal_ws(ws, "pod-1")
    assert ws.closed == [(1008, "Invalid token")]


async def test_terminal_ws_rejects_unavailable_pod(monkeypatch):
    payload = type("Payload", (), {"sub": "user-1"})()
    async def fake_verify_token(token):
        return payload

    monkeypatch.setattr("app.routers.terminal.verify_token", fake_verify_token)
    monkeypatch.setattr("app.routers.terminal.async_session", lambda: FakeDBContext(None))

    ws = FakeWebSocket(cookies={"session_token": "tok"})
    await terminal_router.terminal_ws(ws, "pod-1")

    assert ws.closed == [(1008, "Pod not available")]


async def test_terminal_ws_reports_when_no_running_k8s_pod_found(monkeypatch):
    payload = type("Payload", (), {"sub": "user-1"})()
    session = type("Session", (), {"id": "pod-1", "user_id": "user-1", "state": "running", "namespace": "hopper"})()
    async def fake_verify_token(token):
        return payload

    monkeypatch.setattr("app.routers.terminal.verify_token", fake_verify_token)
    monkeypatch.setattr("app.routers.terminal.async_session", lambda: FakeDBContext(session))

    class FakeProc:
        async def communicate(self):
            return (b"", b"")

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr("app.routers.terminal.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    ws = FakeWebSocket(cookies={"session_token": "tok"})
    await terminal_router.terminal_ws(ws, "pod-1")

    assert ws.accepted is True
    assert ws.sent_text == ["\r\nNo running pod found\r\n"]
