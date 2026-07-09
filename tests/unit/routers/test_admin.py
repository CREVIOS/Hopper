import pytest
from fastapi import HTTPException

from app.routers.admin import _require_admin, _require_admin_only
from app.schemas.user import TokenPayload


def _payload(role: str) -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="Test User",
        role=role,
        exp=1234567890,
    )


def test_require_admin_allows_admin_and_professor():
    assert _require_admin(_payload("admin")) is None
    assert _require_admin(_payload("professor")) is None


def test_require_admin_rejects_other_roles():
    with pytest.raises(HTTPException) as exc_info:
        _require_admin(_payload("student"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin access required"


def test_require_admin_only_accepts_admin():
    assert _require_admin_only(_payload("admin")) is None


def test_require_admin_only_rejects_non_admin():
    with pytest.raises(HTTPException) as exc_info:
        _require_admin_only(_payload("professor"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin role required"
