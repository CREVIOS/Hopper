from types import SimpleNamespace

from app.routers import settings as settings_router
from app.schemas.user import TokenPayload


def _payload():
    return TokenPayload(
        sub="user-1", email="user@example.com", name="Test User", role="student", exp=1234567890
    )


async def test_save_vscode_settings_persists_and_returns_blob(monkeypatch):
    captured = {}

    async def fake_set(db, user_id, vscode):
        captured.update(user_id=user_id, vscode=vscode)
        return SimpleNamespace(vscode=vscode)

    monkeypatch.setattr(settings_router, "set_vscode_settings", fake_set)

    result = await settings_router.save_vscode_settings(
        {"editor.fontSize": 16}, current_user=_payload(), db=None
    )

    assert result == {"status": "saved", "vscode": {"editor.fontSize": 16}}
    assert captured == {"user_id": "user-1", "vscode": {"editor.fontSize": 16}}


async def test_read_vscode_settings_returns_empty_when_unset(monkeypatch):
    async def fake_get(db, user_id):
        return None

    monkeypatch.setattr(settings_router, "get_user_settings", fake_get)

    result = await settings_router.read_vscode_settings(current_user=_payload(), db=None)

    assert result == {"vscode": {}}


async def test_read_vscode_settings_returns_saved_blob(monkeypatch):
    async def fake_get(db, user_id):
        return SimpleNamespace(vscode={"editor.tabSize": 2})

    monkeypatch.setattr(settings_router, "get_user_settings", fake_get)

    result = await settings_router.read_vscode_settings(current_user=_payload(), db=None)

    assert result == {"vscode": {"editor.tabSize": 2}}
