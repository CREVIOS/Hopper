from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.credit_ledger import LedgerEntry, Transfer
from app.schemas.credit import CreditBalanceResponse, CreditHistoryResponse
from app.schemas.user import TokenPayload
from app.services.credit_service import get_balance, get_or_create_account, add_credits

router = APIRouter()


@router.get("/balance", response_model=CreditBalanceResponse)
async def get_credit_balance(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current credit balance."""
    balance = await get_balance(db, current_user.sub)
    account = await get_or_create_account(db, current_user.sub)
    return CreditBalanceResponse(account_id=account.id, balance=balance)


@router.get("/history", response_model=list[CreditHistoryResponse])
async def get_history(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """Get credit transaction history."""
    account = await get_or_create_account(db, current_user.sub)

    result = await db.execute(
        select(LedgerEntry, Transfer.type)
        .join(Transfer, LedgerEntry.transfer_id == Transfer.id)
        .where(LedgerEntry.account_id == account.id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.all()

    return [
        CreditHistoryResponse(
            id=entry.id,
            account_id=entry.account_id,
            amount=float(entry.amount),
            direction="debit" if entry.direction == 1 else "credit",
            type=transfer_type,
            created_at=entry.created_at,
        )
        for entry, transfer_type in rows
    ]


class AllocateRequest(BaseModel):
    account_id: str
    amount: float
    description: str = "allocation"


@router.post("/allocate")
async def allocate_credits(
    request: AllocateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Allocate credits to a student account (professor/admin only)."""
    allowed_roles = {"platform_admin", "university_admin", "department_admin", "professor"}
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only professors and admins can allocate credits",
        )

    transfer = await add_credits(db, request.account_id, request.amount, request.description)
    return {"message": "allocated", "transfer_id": transfer.id}
