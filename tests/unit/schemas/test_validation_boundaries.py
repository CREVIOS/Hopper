import pytest
from pydantic import ValidationError

from app.schemas.user import (
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    VerifyEmailRequest,
)


@pytest.mark.parametrize(
    ("model", "payload", "valid"),
    [
        (SignupRequest, {"email": "a@b.co", "password": "x" * 12, "name": "A"}, True),
        (SignupRequest, {"email": "a@b.co", "password": "x" * 11, "name": "A"}, False),
        (SignupRequest, {"email": "a@b.co", "password": "x" * 129, "name": "A"}, False),
        (SignupRequest, {"email": "a@b.co", "password": "x" * 12, "name": ""}, False),
        (SignupRequest, {"email": "a@b.co", "password": "x" * 12, "name": "A" * 120}, True),
        (SignupRequest, {"email": "a@b.co", "password": "x" * 12, "name": "A" * 121}, False),
        (LoginRequest, {"email": "a@b.co", "password": "x" * 128}, True),
        (LoginRequest, {"email": "a@b.co", "password": "x" * 129}, False),
        (VerifyEmailRequest, {"email": "a@b.co", "code": "1234"}, True),
        (VerifyEmailRequest, {"email": "a@b.co", "code": "123"}, False),
        (VerifyEmailRequest, {"email": "a@b.co", "code": "1" * 13}, False),
        (ResetPasswordRequest, {"email": "a@b.co", "code": "1234", "password": "x" * 12}, True),
        (ResetPasswordRequest, {"email": "a@b.co", "code": "1234", "password": "x" * 11}, False),
    ],
)
def test_request_validation_boundaries(model, payload, valid):
    if valid:
        assert model(**payload)
    else:
        with pytest.raises(ValidationError):
            model(**payload)

