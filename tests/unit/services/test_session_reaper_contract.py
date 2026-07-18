"""Contract test for the expired-session reaper service."""

import importlib

def test_session_reaper_service_contract_exists():
    module = importlib.import_module("app.services.session_reaper")
    reap = getattr(module, "reap_expired_sessions")
    assert callable(reap)
