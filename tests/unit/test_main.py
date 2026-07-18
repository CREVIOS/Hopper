import pytest

from app import main as main_module


def test_create_app_rejects_wildcard_cors(monkeypatch):
    monkeypatch.setattr("app.main.settings.cors_origins", ["*"])

    with pytest.raises(RuntimeError) as exc_info:
        main_module.create_app()

    assert "HOPPER_CORS_ORIGINS must list explicit origins" in str(exc_info.value)


def test_create_app_registers_health_and_ready_routes(monkeypatch):
    monkeypatch.setattr("app.main.settings.cors_origins", ["http://localhost:5173"])

    app = main_module.create_app()
    paths = {route.path for route in app.routes}

    assert "/healthz" in paths
    assert "/readyz" in paths
    assert app.state.limiter is main_module.limiter


def _readyz_client(monkeypatch, *, db_ok=True, nats_ok=True, orch_ok=True):
    """Build a TestClient with the /readyz dependencies faked."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr("app.main.settings.cors_origins", ["http://localhost:5173"])

    class FakeConn:
        async def execute(self, stmt):
            if not db_ok:
                raise RuntimeError("db down")

    class FakeConnCtx:
        async def __aenter__(self):
            if not db_ok:
                raise RuntimeError("db down")
            return FakeConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def connect(self):
            return FakeConnCtx()

    class FakeNC:
        is_connected = nats_ok

    async def fake_healthy(timeout: float = 3.0):
        return orch_ok

    monkeypatch.setattr("app.main.engine", FakeEngine())
    monkeypatch.setattr("app.main.nats_client.nc", FakeNC() if nats_ok else None)

    from app.services.orchestrator_client import orchestrator_client

    monkeypatch.setattr(orchestrator_client, "healthy", fake_healthy)

    # No lifespan: readyz must work standalone, exactly like a K8s probe hits it.
    return TestClient(main_module.create_app())


def test_readyz_reports_ready_when_dependencies_up(monkeypatch):
    client = _readyz_client(monkeypatch)
    res = client.get("/readyz")

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": True, "nats": True, "orchestrator": True}


def test_readyz_degraded_when_database_down(monkeypatch):
    client = _readyz_client(monkeypatch, db_ok=False)
    res = client.get("/readyz")

    assert res.status_code == 503
    assert res.json()["checks"]["database"] is False


def test_readyz_degraded_when_nats_down(monkeypatch):
    client = _readyz_client(monkeypatch, nats_ok=False)
    res = client.get("/readyz")

    assert res.status_code == 503
    assert res.json()["checks"]["nats"] is False


def test_readyz_orchestrator_outage_is_reported_but_not_gating(monkeypatch):
    """The orchestrator only serves VM create/terminate; its outage must not
    pull the whole gateway (auth, credits, dashboard) out of the Service."""
    client = _readyz_client(monkeypatch, orch_ok=False)
    res = client.get("/readyz")

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["checks"]["orchestrator"] is False
