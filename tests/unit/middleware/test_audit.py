from starlette.requests import Request
from starlette.responses import Response

from app.middleware.audit import AuditMiddleware, _extract_user_id, _resolve_action
from app.schemas.user import TokenPayload


def test_resolve_action_matches_known_pattern_with_resource_id():
    action, resource_type, resource_id = _resolve_action("/admin/users/user-1/role", "PATCH")

    assert action == "change_user_role"
    assert resource_type == "user"
    assert resource_id == "user-1"


def test_resolve_action_falls_back_for_unknown_path():
    action, resource_type, resource_id = _resolve_action("/custom/path", "POST")

    assert action == "post:/custom/path"
    assert resource_type == "unknown"
    assert resource_id is None


async def test_extract_user_id_returns_none_without_cookie():
    request = Request({"type": "http", "headers": []})

    assert await _extract_user_id(request) is None


async def test_extract_user_id_returns_verified_subject(monkeypatch):
    payload = TokenPayload(
        sub="user-1",
        email="student@example.com",
        name="Test Student",
        role="student",
        exp=1234567890,
    )

    async def fake_verify_token(token):
        assert token == "good-token"
        return payload

    monkeypatch.setattr("app.middleware.audit.verify_token", fake_verify_token)

    request = Request(
        {"type": "http", "headers": [(b"cookie", b"session_token=good-token")]}
    )

    assert await _extract_user_id(request) == "user-1"


async def test_dispatch_skips_non_mutating_requests():
    middleware = AuditMiddleware(app=lambda scope, receive, send: None)
    request = Request({"type": "http", "method": "GET", "path": "/pods", "headers": []})

    async def call_next(req):
        return Response("ok", status_code=200)

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200


async def test_dispatch_skips_health_checks():
    middleware = AuditMiddleware(app=lambda scope, receive, send: None)
    request = Request({"type": "http", "method": "POST", "path": "/healthz", "headers": []})

    async def call_next(req):
        return Response("ok", status_code=200)

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200


async def test_dispatch_schedules_log_task_for_mutating_request(monkeypatch):
    middleware = AuditMiddleware(app=lambda scope, receive, send: None)
    request = Request({"type": "http", "method": "POST", "path": "/issues", "headers": []})
    scheduled = {}

    async def call_next(req):
        return Response("created", status_code=201)

    async def fake_log(req, status_code):
        scheduled["path"] = req.url.path
        scheduled["status_code"] = status_code

    def fake_create_task(coro):
        scheduled["scheduled"] = True
        coro.close()
        return object()

    monkeypatch.setattr(middleware, "_log", fake_log)
    monkeypatch.setattr("app.middleware.audit.asyncio.create_task", fake_create_task)

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 201
    assert scheduled["scheduled"] is True


async def test_log_writes_audit_entry(monkeypatch):
    middleware = AuditMiddleware(app=lambda scope, receive, send: None)
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/admin/users/user-1/role",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )

    async def fake_extract_user_id(req):
        return "admin-1"

    captured = {}

    class FakeDB:
        def add(self, entry):
            captured["entry"] = entry

        async def commit(self):
            captured["committed"] = True

    class FakeSessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.middleware.audit._extract_user_id", fake_extract_user_id)
    monkeypatch.setattr("app.middleware.audit.async_session", lambda: FakeSessionContext())

    await middleware._log(request, 200)

    assert captured["committed"] is True
    assert captured["entry"].user_id == "admin-1"
    assert captured["entry"].action == "change_user_role"
    assert captured["entry"].resource_id == "user-1"
    assert captured["entry"].ip_address == "127.0.0.1"
    assert captured["entry"].status_code == 200
