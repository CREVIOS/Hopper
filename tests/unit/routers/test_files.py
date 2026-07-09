import pytest
from fastapi import HTTPException

from app.routers.files import _safe_path


def test_safe_path_accepts_normal_path():
    assert _safe_path("/home/student") == "/home/student"


@pytest.mark.parametrize("path", ["", "bad\x00path", "bad\npath"])
def test_safe_path_rejects_invalid_path(path):
    with pytest.raises(HTTPException) as exc_info:
        _safe_path(path)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "invalid path"
