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
