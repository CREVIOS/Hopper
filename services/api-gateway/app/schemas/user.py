from pydantic import BaseModel


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
