import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_ledger import Account, Transfer, LedgerEntry

SYSTEM_ACCOUNT_ID = "00000000-0000-0000-0000-000000000000"


async def get_or_create_account(db: AsyncSession, user_id: str) -> Account:
    """Find or create a credit account for a user."""
    result = await db.execute(
        select(Account).where(Account.owner_id == user_id, Account.owner_type == "user")
    )
    account = result.scalar_one_or_none()
    if account:
        return account

    account = Account(
        id=str(uuid.uuid4()),
        name=f"user:{user_id}",
        type="asset",
        owner_id=user_id,
        owner_type="user",
    )
    db.add(account)
    await db.flush()
    return account


async def ensure_system_account(db: AsyncSession) -> Account:
    """Ensure the system account exists."""
    result = await db.execute(
        select(Account).where(Account.id == SYSTEM_ACCOUNT_ID)
    )
    account = result.scalar_one_or_none()
    if account:
        return account

    account = Account(
        id=SYSTEM_ACCOUNT_ID,
        name="system",
        type="liability",
        owner_id=None,
        owner_type="system",
    )
    db.add(account)
    await db.flush()
    return account


async def get_balance(db: AsyncSession, user_id: str) -> float:
    """Get the current credit balance for a user by reading last ledger entry."""
    account = await get_or_create_account(db, user_id)

    result = await db.execute(
        select(LedgerEntry.current_balance)
        .where(LedgerEntry.account_id == account.id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return float(row) if row is not None else 0.0


async def add_credits(
    db: AsyncSession, user_id: str, amount: float, description: str = "allocation"
) -> Transfer:
    """Add credits to a user account (system -> user transfer)."""
    now = datetime.now(timezone.utc)
    user_account = await get_or_create_account(db, user_id)
    system_account = await ensure_system_account(db)

    # Get current balances
    user_balance = await get_balance(db, user_id)
    sys_result = await db.execute(
        select(LedgerEntry.current_balance)
        .where(LedgerEntry.account_id == system_account.id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(1)
    )
    sys_balance = float(sys_result.scalar_one_or_none() or 0)

    transfer_id = str(uuid.uuid4())
    transfer = Transfer(
        id=transfer_id,
        type=description,
        metadata_={"description": description},
        event_at=now,
    )
    db.add(transfer)

    # Debit system (source), credit user (destination)
    db.add(LedgerEntry(
        id=str(uuid.uuid4()),
        transfer_id=transfer_id,
        account_id=system_account.id,
        direction=1,  # debit
        amount=amount,
        previous_balance=sys_balance,
        current_balance=sys_balance - amount,
        event_at=now,
    ))
    db.add(LedgerEntry(
        id=str(uuid.uuid4()),
        transfer_id=transfer_id,
        account_id=user_account.id,
        direction=-1,  # credit (adds to asset)
        amount=amount,
        previous_balance=user_balance,
        current_balance=user_balance + amount,
        event_at=now,
    ))

    await db.commit()
    return transfer


async def deduct_credits(
    db: AsyncSession, user_id: str, amount: float, description: str = "pod_usage"
) -> Transfer:
    """Deduct credits from a user account (user -> system transfer).

    Uses advisory lock to prevent race conditions.
    Raises ValueError if insufficient balance.
    """
    user_account = await get_or_create_account(db, user_id)

    # Advisory lock on account to prevent concurrent deductions
    await db.execute(text(f"SELECT pg_advisory_xact_lock(hashtext('{user_account.id}'))"))

    balance = await get_balance(db, user_id)
    if balance < amount:
        raise ValueError(f"Insufficient credits: have {balance}, need {amount}")

    now = datetime.now(timezone.utc)
    system_account = await ensure_system_account(db)

    sys_result = await db.execute(
        select(LedgerEntry.current_balance)
        .where(LedgerEntry.account_id == system_account.id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(1)
    )
    sys_balance = float(sys_result.scalar_one_or_none() or 0)

    transfer_id = str(uuid.uuid4())
    transfer = Transfer(
        id=transfer_id,
        type=description,
        metadata_={"description": description},
        event_at=now,
    )
    db.add(transfer)

    # Debit user (source), credit system (destination)
    db.add(LedgerEntry(
        id=str(uuid.uuid4()),
        transfer_id=transfer_id,
        account_id=user_account.id,
        direction=1,  # debit
        amount=amount,
        previous_balance=balance,
        current_balance=balance - amount,
        event_at=now,
    ))
    db.add(LedgerEntry(
        id=str(uuid.uuid4()),
        transfer_id=transfer_id,
        account_id=system_account.id,
        direction=-1,  # credit
        amount=amount,
        previous_balance=sys_balance,
        current_balance=sys_balance + amount,
        event_at=now,
    ))

    await db.commit()
    return transfer
