from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    email: str = Field(max_length=254)
    # Policy rules (length, character classes, not-the-username) are enforced
    # by app.services.password_policy, which mirrors the Keycloak realm and can
    # name every unmet rule. A min_length here would instead fail as a pydantic
    # 422 whose `detail` is a list, which the client renders as "[object
    # Object]". max_length stays as a plain input-size guard.
    password: str = Field(max_length=128)
    name: str = Field(min_length=1, max_length=120)
    # "student" (active immediately) or "teacher" (created as student, pending
    # admin approval). Anything else is rejected by the router.
    role: str = Field(default="student")


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class VerifyEmailRequest(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(min_length=4, max_length=12)


class ResendCodeRequest(BaseModel):
    email: str = Field(max_length=254)
    # "verify_email" (default) or "password_reset".
    purpose: str = Field(default="verify_email")


class ForgotPasswordRequest(BaseModel):
    email: str = Field(max_length=254)


class ResetPasswordRequest(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(min_length=4, max_length=12)
    # Policy enforced in app.services.password_policy — see SignupRequest.
    password: str = Field(max_length=128)


class TokenPayload(BaseModel):
    sub: str
    email: str
    name: str
    role: str
    exp: int
    email_verified: bool = False


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    # True while a teacher signup is awaiting admin approval (role stays
    # "student" until then). Surfaced so the UI can show the pending state.
    pending_teacher: bool = False


class ChangeRoleRequest(BaseModel):
    role: str  # one of: admin, professor, student
