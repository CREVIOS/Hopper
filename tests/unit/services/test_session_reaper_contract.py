"""Contract marker for the planned expired-session reaper.

The production service does not exist yet. Keeping this as a strict XPASS
guard makes the missing release requirement visible without making every test
run fail before implementation work is authorized outside ``tests/``.
"""

import importlib

import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "session reaper is not implemented; expected app.services.session_reaper "
        "with an async reap_expired_sessions entry point"
    ),
)
def test_session_reaper_service_contract_exists():
    module = importlib.import_module("app.services.session_reaper")
    reap = getattr(module, "reap_expired_sessions")
    assert callable(reap)

