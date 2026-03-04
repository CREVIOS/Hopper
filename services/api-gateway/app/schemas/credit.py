from datetime import datetime

from pydantic import BaseModel


class CreditBalanceResponse(BaseModel):
    account_id: str
    balance: float


class CreditHistoryResponse(BaseModel):
    id: str
    account_id: str
    amount: float
    direction: str
    type: str
    pod_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
