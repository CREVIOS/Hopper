import pytest
from pydantic import ValidationError

from app.schemas.user import ChangeRoleRequest, LoginRequest, SignupRequest, TokenPayload, UserResponse


def test_signup_request_accepts_valid_payload_and_default_role():
    request = SignupRequest(
        email="student@example.com",
        password="password1234",
        name="Test Student",
    )

    assert request.email == "student@example.com"
    assert request.password == "password1234"
    assert request.name == "Test Student"
    assert request.role == "student"


def test_signup_request_accepts_teacher_role():
    request = SignupRequest(
        email="teacher@example.com",
        password="password1234",
        name="Test Teacher",
        role="teacher",
    )

    assert request.role == "teacher"


def test_signup_request_leaves_password_rules_to_the_policy():
    """The schema deliberately does NOT enforce the password policy.

    A `min_length` here fails as a pydantic 422 whose `detail` is a list of
    error dicts, which the browser client renders as "[object Object]" — and it
    can only ever complain about length, never the character-class rules the
    Keycloak realm also enforces. app.services.password_policy owns all of it
    and names every unmet rule; routers/auth.py rejects with a 400 before
    Keycloak is called. See tests/unit/routers/test_auth_password.py.
    """
    request = SignupRequest(
        email="student@example.com",
        password="short",
        name="Test Student",
    )

    assert request.password == "short"


def test_signup_request_rejects_password_above_max_length():
    # max_length stays on the schema: an input-size guard, not a policy rule.
    with pytest.raises(ValidationError) as exc_info:
        SignupRequest(
            email="student@example.com",
            password="x" * 129,
            name="Test Student",
        )

    assert "at most 128 characters" in str(exc_info.value)


def test_signup_request_rejects_empty_name():
    with pytest.raises(ValidationError) as exc_info:
        SignupRequest(
            email="student@example.com",
            password="password1234",
            name="",
        )

    assert "at least 1 character" in str(exc_info.value)


def test_login_request_rejects_password_above_max_length():
    with pytest.raises(ValidationError) as exc_info:
        LoginRequest(
            email="student@example.com",
            password="x" * 129,
        )

    assert "at most 128 characters" in str(exc_info.value)


def test_token_payload_defaults_email_verified_to_false():
    payload = TokenPayload(
        sub="user-1",
        email="student@example.com",
        name="Test Student",
        role="student",
        exp=1234567890,
    )

    assert payload.email_verified is False


def test_user_response_defaults_pending_teacher_to_false_and_serializes():
    response = UserResponse(
        id="user-1",
        email="student@example.com",
        name="Test Student",
        role="student",
    )

    assert response.pending_teacher is False
    assert response.model_dump() == {
        "id": "user-1",
        "email": "student@example.com",
        "name": "Test Student",
        "role": "student",
        "pending_teacher": False,
        "university_id": None,
    }


def test_change_role_request_preserves_requested_role():
    request = ChangeRoleRequest(role="admin")

    assert request.role == "admin"
