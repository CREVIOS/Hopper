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
    ],
)
def test_request_validation_boundaries(model, payload, valid):
    if valid:
        assert model(**payload)
    else:
        with pytest.raises(ValidationError):
            model(**payload)


@pytest.mark.parametrize("model", [SignupRequest, LoginRequest, ResetPasswordRequest])
def test_password_schemas_bound_input_size_but_not_policy(model):
    """Short passwords are a policy concern, not a schema one.

    The password schemas only bound input size (max_length=128). The minimum
    length and the character-class rules live in app.services.password_policy,
    which mirrors the Keycloak realm and can name every unmet rule at once;
    a pydantic min_length could only ever report length, as a 422 the browser
    client cannot render. LoginRequest never had a minimum — you must be able
    to submit an old short password and be told it's wrong.
    """
    payload = {"email": "a@b.co", "password": "short"}
    if model is ResetPasswordRequest:
        payload["code"] = "1234"
    if model is SignupRequest:
        payload["name"] = "A"

    assert model(**payload).password == "short"

