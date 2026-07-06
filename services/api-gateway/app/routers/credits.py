from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.credit_ledger import LedgerEntry, Transfer
from app.models.user import User
from app.schemas.credit import CreditBalanceResponse, CreditHistoryResponse
from app.schemas.user import TokenPayload
from app.services.credit_service import (
    add_credits,
    allocate_between_users,
    get_balance,
    get_or_create_account,
)

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
    user_id: str
    # Bounded positive amount. The ledger column is NUMERIC(12,4), which caps
    # at 99,999,999.9999 — bound the input below that and reject ≤0 so admins
    # can't accidentally deduct via a typo (deductions have their own audited
    # path) and so a fat-finger 1e15 doesn't surface as a 500 from a numeric
    # overflow in Postgres.
    amount: float = Field(gt=0, le=1_000_000_000)
    description: str = Field(default="allocation", max_length=500)


async def _users_with_balance(db: AsyncSession, role: str) -> list[dict]:
    result = await db.execute(select(User).where(User.role == role).order_by(User.name))
    out = []
    for u in result.scalars().all():
        out.append({
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "balance": await get_balance(db, u.id),
        })
    return out


@router.get("/teachers")
async def list_teachers(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Teachers (professors) with balances — for the admin grant view."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return await _users_with_balance(db, "professor")


@router.get("/students")
async def list_students(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Students with balances — for the teacher allocation view."""
    if current_user.role not in ("admin", "professor"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teachers only")
    return await _users_with_balance(db, "student")


@router.post("/allocate")
async def allocate_credits(
    request: AllocateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Credit delegation, role-aware:

    - **admin** grants credits to a user from the system account (used to fund
      teachers). This can't overdraw — the system account is the ledger source.
    - **professor** allocates from *their own* balance to a student, and is
      rejected with 402 if they lack the credits.
    """
    if request.user_id == current_user.sub:
        raise HTTPException(status_code=400, detail="Cannot allocate credits to yourself")

    target = await db.get(User, request.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Recipient not found")

    if current_user.role == "admin":
        transfer = await add_credits(
            db, request.user_id, request.amount, request.description or "admin_grant"
        )
        return {"message": "granted", "transfer_id": transfer.id}

    if current_user.role == "professor":
        if target.role != "student":
            raise HTTPException(status_code=400, detail="Teachers can only allocate to students")
        try:
            transfer = await allocate_between_users(
                db, current_user.sub, request.user_id, request.amount,
                request.description or "teacher_allocation",
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e)
            )
        return {"message": "allocated", "transfer_id": transfer.id}

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only admins and teachers can allocate credits",
    )
