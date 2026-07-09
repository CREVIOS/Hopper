from app.routers.settings import save_vscode_settings
from app.schemas.user import TokenPayload


async def test_save_vscode_settings_returns_saved_status():
    payload = TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="Test User",
        role="student",
        exp=1234567890,
    )

    result = await save_vscode_settings(
        {"editor.fontSize": 16},
        current_user=payload,
        db=None,
    )

    assert result == {"status": "saved"}
