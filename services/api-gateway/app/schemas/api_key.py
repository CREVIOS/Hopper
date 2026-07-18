from datetime import datetime

from pydantic import BaseModel, Field


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # "read_only" (GET/HEAD only) or "full_access".
    scope: str = Field(default="read_only", pattern="^(read_only|full_access)$")


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    prefix: str
    scope: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    # The full plaintext token — returned exactly once, at creation. Only its
    # SHA-256 hash is stored server-side.
    key: str
