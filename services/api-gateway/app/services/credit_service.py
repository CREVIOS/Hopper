import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_ledger import Account, Transfer, LedgerEntry

SYSTEM_ACCOUNT_ID = "00000000-0000-0000-0000-000000000000"


async def get_or_create_account(
    db: AsyncSession,
    user_id: str,
    *,
    persist: bool = False,
) -> Account:
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
    if persist:
        await db.commit()
        await db.refresh(account)
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
    now = datetime.utcnow()
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


async def allocate_between_users(
    db: AsyncSession,
    from_user_id: str,
    to_user_id: str,
    amount: float,
    description: str = "teacher_allocation",
) -> Transfer:
    """Move credits from one user's account to another (teacher → student).

    Balanced double-entry: source debited, destination credited. An advisory
    xact lock on the SOURCE account serialises concurrent allocations from the
    same teacher so two requests can't both pass the balance check and overdraw.
    Raises ValueError if the source has insufficient balance.
    """
    if from_user_id == to_user_id:
        raise ValueError("cannot allocate to yourself")

    source = await get_or_create_account(db, from_user_id)
    dest = await get_or_create_account(db, to_user_id)

    # Lock the source account for the duration of the transaction (matches the
    # deduct_credits pattern). id is a server-generated UUID, so interpolating
    # it into hashtext() is safe from injection.
    await db.execute(text(f"SELECT pg_advisory_xact_lock(hashtext('{source.id}'))"))

    source_balance = await get_balance(db, from_user_id)
    if source_balance < amount:
        raise ValueError(f"Insufficient credits: have {source_balance}, need {amount}")
    dest_balance = await get_balance(db, to_user_id)

    now = datetime.utcnow()
    transfer_id = str(uuid.uuid4())
    transfer = Transfer(
        id=transfer_id,
        type=description,
        metadata_={"from": from_user_id, "to": to_user_id, "description": description},
        event_at=now,
    )
    db.add(transfer)
    # Debit source
    db.add(LedgerEntry(
        id=str(uuid.uuid4()),
        transfer_id=transfer_id,
        account_id=source.id,
        direction=1,
        amount=amount,
        previous_balance=source_balance,
        current_balance=source_balance - amount,
        event_at=now,
    ))
    # Credit destination
    db.add(LedgerEntry(
        id=str(uuid.uuid4()),
        transfer_id=transfer_id,
        account_id=dest.id,
        direction=-1,
        amount=amount,
        previous_balance=dest_balance,
        current_balance=dest_balance + amount,
        event_at=now,
    ))
    await db.commit()
    return transfer


async def deduct_credits(
    db: AsyncSession, user_id: str, amount: float,
    description: str = "pod_usage",
    tx_id: str | None = None,
) -> Transfer:
    """Deduct credits from a user account (user -> system transfer).

    Idempotency: if `tx_id` is provided we use it as the Transfer primary
    key. A redelivery of the same NATS message (same pod_id+seq) attempts
    to insert a duplicate Transfer.id and raises IntegrityError, which the
    caller catches as the no-op signal. Without `tx_id` we fall back to a
    fresh UUID — only safe for callers (e.g. manual admin allocations) that
    don't replay.

    Uses advisory lock to prevent concurrent deductions racing the balance
    read. Raises ValueError if insufficient balance.
    """
    user_account = await get_or_create_account(db, user_id)

    await db.execute(text(f"SELECT pg_advisory_xact_lock(hashtext('{user_account.id}'))"))

    # Idempotency: bail out early if this tx already exists. Read the row once —
    # scalar_one_or_none() consumes the Result, so re-reading it with
    # scalar_one() would raise ResourceClosedError ("result object is closed").
    if tx_id:
        existing = await db.execute(select(Transfer).where(Transfer.id == tx_id))
        existing_transfer = existing.scalar_one_or_none()
        if existing_transfer is not None:
            return existing_transfer

    balance = await get_balance(db, user_id)
    if balance < amount:
        raise ValueError(f"Insufficient credits: have {balance}, need {amount}")

    now = datetime.utcnow()
    system_account = await ensure_system_account(db)

    sys_result = await db.execute(
        select(LedgerEntry.current_balance)
        .where(LedgerEntry.account_id == system_account.id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(1)
    )
    sys_balance = float(sys_result.scalar_one_or_none() or 0)

    transfer_id = tx_id or str(uuid.uuid4())
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
