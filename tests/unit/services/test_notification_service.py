import json

from app.services import notification_service as notif_module


class FakeMessage:
    def __init__(self, data=b""):
        self.data = data


class FakePodSession:
    def __init__(self, state="running"):
        self.id = "sess-1"
        self.user_id = "user-1"
        self.plan = "small"
        self.state = state


class FakeDB:
    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


def _env(monkeypatch, session):
    """Fake db/session/notify wiring shared by the consumer tests."""
    db = FakeDB()
    notified = {}

    class FakeDBContext:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_resolve_session(_db, pod_ref):
        return session

    async def fake_notify(_db, user_id, **kwargs):
        notified["user_id"] = user_id
        notified.update(kwargs)

    monkeypatch.setattr(
        "app.services.notification_service.async_session", lambda: FakeDBContext()
    )
    monkeypatch.setattr(
        "app.services.notification_service.resolve_session", fake_resolve_session
    )
    monkeypatch.setattr("app.services.notification_service.notify", fake_notify)
    return db, notified


# --- pod.started -----------------------------------------------------------


async def test_pod_started_notifies_even_when_db_already_running(monkeypatch):
    """create_pod optimistically stores state=running before the container
    starts, so 'already running' must NOT suppress the readiness push."""
    session = FakePodSession(state="running")
    db, notified = _env(monkeypatch, session)

    msg = FakeMessage(json.dumps({"pod_id": "sess-1", "user_id": "user-1"}).encode())
    await notif_module._handle_pod_started(msg)

    assert notified["user_id"] == "user-1"
    assert notified["type_"] == "success"
    assert notified["data"]["action"] == "open_vscode"
    assert db.committed is True


async def test_pod_started_repairs_stale_creating_state(monkeypatch):
    session = FakePodSession(state="creating")
    db, notified = _env(monkeypatch, session)

    msg = FakeMessage(json.dumps({"pod_id": "sess-1"}).encode())
    await notif_module._handle_pod_started(msg)

    assert session.state == "running"
    assert notified["user_id"] == "user-1"


async def test_pod_started_skips_terminal_sessions(monkeypatch):
    session = FakePodSession(state="terminated")
    db, notified = _env(monkeypatch, session)

    msg = FakeMessage(json.dumps({"pod_id": "sess-1"}).encode())
    await notif_module._handle_pod_started(msg)

    assert session.state == "terminated"
    assert notified == {}


async def test_pod_started_ignores_malformed_payload(monkeypatch):
    db, notified = _env(monkeypatch, FakePodSession())
    await notif_module._handle_pod_started(FakeMessage(b"{nope"))
    assert notified == {}


# --- pod.stopped -----------------------------------------------------------


async def test_pod_stopped_marks_terminated_and_notifies(monkeypatch):
    session = FakePodSession(state="running")
    db, notified = _env(monkeypatch, session)

    msg = FakeMessage(
        json.dumps({"pod_id": "sess-1", "reason": "credits_exhausted"}).encode()
    )
    await notif_module._handle_pod_stopped(msg)

    assert session.state == "terminated"
    assert notified["type_"] == "warning"
    assert notified["data"]["reason"] == "credits_exhausted"
    assert db.committed is True


async def test_pod_stopped_skips_already_terminated(monkeypatch):
    """User-initiated deletes commit terminated before the event arrives —
    no notification for a termination the user is watching."""
    session = FakePodSession(state="terminated")
    db, notified = _env(monkeypatch, session)

    msg = FakeMessage(json.dumps({"pod_id": "sess-1"}).encode())
    await notif_module._handle_pod_stopped(msg)

    assert notified == {}
    assert db.committed is False


async def test_pod_stopped_unknown_session_is_noop(monkeypatch):
    db, notified = _env(monkeypatch, None)

    msg = FakeMessage(json.dumps({"pod_id": "ghost"}).encode())
    await notif_module._handle_pod_stopped(msg)

    assert notified == {}


# --- pod.failed ------------------------------------------------------------


async def test_pod_failed_repairs_state_without_notifying(monkeypatch):
    """The synchronous create_pod path owns the failure notification; the
    consumer only repairs DB state."""
    session = FakePodSession(state="running")
    db, notified = _env(monkeypatch, session)

    msg = FakeMessage(
        json.dumps({"pod_id": "vm-123", "api_pod_id": "sess-1", "user_id": "user-1"}).encode()
    )
    await notif_module._handle_pod_failed(msg)

    assert session.state == "failed"
    assert notified == {}
    assert db.committed is True


async def test_pod_failed_skips_terminal_sessions(monkeypatch):
    session = FakePodSession(state="failed")
    db, notified = _env(monkeypatch, session)

    msg = FakeMessage(json.dumps({"pod_id": "sess-1"}).encode())
    await notif_module._handle_pod_failed(msg)

    assert db.committed is False


# --- consumer registration --------------------------------------------------


async def test_start_notification_consumer_subscribes_queue_grouped(monkeypatch):
    subscriptions = []

    class FakeNC:
        async def subscribe(self, subject, queue, cb):
            subscriptions.append((subject, queue))

    monkeypatch.setattr(
        "app.services.notification_service.nats_client.get_nc", lambda: FakeNC()
    )

    await notif_module.start_notification_consumer()

    assert [s for s, _ in subscriptions] == ["pod.started", "pod.stopped", "pod.failed"]
    assert all(q == "notify-workers" for _, q in subscriptions)
