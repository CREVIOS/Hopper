from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    # "student" (active immediately) or "teacher" (created as student, pending
    # admin approval). Anything else is rejected by the router.
    role: str = Field(default="student")


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
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


class ChangeRoleRequest(BaseModel):
    role: str  # one of: admin, professor, student
