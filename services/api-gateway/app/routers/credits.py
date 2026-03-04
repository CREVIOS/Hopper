from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_db
from app.schemas.credit import CreditBalanceResponse, CreditHistoryResponse
from app.schemas.user import TokenPayload

router = APIRouter()


@router.get("/balance", response_model=CreditBalanceResponse)
async def get_balance(
    current_user: TokenPayload = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get current credit balance."""
    # TODO: Query balance from ledger
    return CreditBalanceResponse(account_id=current_user.sub, balance=0.0)


@router.get("/history", response_model=list[CreditHistoryResponse])
async def get_history(
    current_user: TokenPayload = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get credit transaction history."""
    # TODO: Query ledger entries
    return []


@router.post("/allocate")
async def allocate_credits(
    account_id: str,
    amount: float,
    current_user: TokenPayload = Depends(get_current_user),
    db=Depends(get_db),
):
    """Allocate credits to a student account (professor/admin only)."""
    # TODO: Check role, create allocation transfer
    return {"message": "allocated"}
