from pydantic import BaseModel


class TokenPayload(BaseModel):
    sub: str
    email: str
    name: str
    role: str
    exp: int


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
