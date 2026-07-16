"""Database-level credit ledger invariants.

These tests intentionally use separate PostgreSQL sessions for concurrent
operations. Unit tests with a fake session cannot prove advisory-lock or
append-only ledger behavior.
"""

import asyncio
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.models.credit_ledger import Account, LedgerEntry, Transfer
from app.services.credit_service import add_credits, deduct_credits, get_balance


def _docker_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker is required for PostgreSQL ledger invariant tests",
)


async def _account_for(session, user_id: str) -> Account:
    result = await session.execute(
        select(Account).where(
            Account.owner_id == user_id,
            Account.owner_type == "user",
        )
    )
    return result.scalar_one()


async def _entries_for(session, account_id: str) -> list[LedgerEntry]:
    result = await session.execute(
        select(LedgerEntry)
        .where(LedgerEntry.account_id == account_id)
        .order_by(LedgerEntry.created_at, LedgerEntry.id)
    )
    return list(result.scalars())


@pytest.mark.asyncio
async def test_each_transfer_has_two_balanced_entries(db_session):
    grant = await add_credits(db_session, "student-ledger", 100, "initial_grant")
    charge = await deduct_credits(
        db_session,
        "student-ledger",
        15,
        description="pod_usage:pod-1",
        tx_id="charge-pod-1-minute-1",
    )

    for transfer in (grant, charge):
        result = await db_session.execute(
            select(LedgerEntry).where(LedgerEntry.transfer_id == transfer.id)
        )
        entries = list(result.scalars())

        assert len(entries) == 2
        assert {entry.direction for entry in entries} == {-1, 1}
        signed_total = sum(
            Decimal(entry.direction) * entry.amount for entry in entries
        )
        assert signed_total == Decimal("0")


@pytest.mark.asyncio
async def test_concurrent_deductions_are_serialized_and_cannot_overdraw(db_session):
    """Ten simultaneous 50-credit charges against 100 credits yield 2 wins."""
    user_id = "student-concurrent"
    await add_credits(db_session, user_id, 100, "initial_grant")
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def deduct(index: int) -> bool:
        async with session_factory() as session:
            try:
                await deduct_credits(
                    session,
                    user_id,
                    50,
                    description="concurrency_test",
                    tx_id=f"concurrent-charge-{index}",
                )
            except ValueError as exc:
                assert "Insufficient credits" in str(exc)
                await session.rollback()
                return False
            return True

    results = await asyncio.gather(*(deduct(index) for index in range(10)))

    assert results.count(True) == 2
    assert results.count(False) == 8
    assert await get_balance(db_session, user_id) == 0

    account = await _account_for(db_session, user_id)
    entries = await _entries_for(db_session, account.id)
    assert len(entries) == 3  # one grant plus two successful deductions
    assert all(entry.current_balance >= 0 for entry in entries)


@pytest.mark.asyncio
async def test_ledger_entry_balance_chain_is_contiguous(db_session):
    user_id = "student-chain"
    await add_credits(db_session, user_id, 100, "initial_grant")
    await deduct_credits(db_session, user_id, 10, tx_id="chain-charge-1")
    await deduct_credits(db_session, user_id, 25, tx_id="chain-charge-2")

    account = await _account_for(db_session, user_id)
    entries = await _entries_for(db_session, account.id)

    assert len(entries) == 3
    assert entries[0].previous_balance == Decimal("0")
    for previous, current in zip(entries, entries[1:]):
        assert current.previous_balance == previous.current_balance
    assert entries[-1].current_balance == Decimal("65")


@pytest.mark.asyncio
async def test_ledger_entries_cannot_be_updated_or_deleted(db_session):
    user_id = "student-immutable"
    transfer = await add_credits(db_session, user_id, 20, "initial_grant")
    result = await db_session.execute(
        select(LedgerEntry).where(LedgerEntry.transfer_id == transfer.id)
    )
    original = {
        entry.id: (entry.amount, entry.previous_balance, entry.current_balance)
        for entry in result.scalars()
    }

    await db_session.execute(
        update(LedgerEntry)
        .where(LedgerEntry.transfer_id == transfer.id)
        .values(amount=999, current_balance=999)
    )
    await db_session.commit()
    await db_session.execute(
        delete(LedgerEntry).where(LedgerEntry.transfer_id == transfer.id)
    )
    await db_session.commit()

    result = await db_session.execute(
        select(LedgerEntry).where(LedgerEntry.transfer_id == transfer.id)
    )
    persisted = {
        entry.id: (entry.amount, entry.previous_balance, entry.current_balance)
        for entry in result.scalars()
    }
    assert persisted == original


@pytest.mark.asyncio
async def test_compensating_credit_appends_entries_without_rewriting_history(db_session):
    user_id = "student-refund"
    await add_credits(db_session, user_id, 50, "initial_grant")
    charge = await deduct_credits(
        db_session, user_id, 20, description="pod_usage", tx_id="refundable-charge"
    )
    account = await _account_for(db_session, user_id)
    before = await _entries_for(db_session, account.id)
    before_snapshot = [
        (entry.id, entry.transfer_id, entry.previous_balance, entry.current_balance)
        for entry in before
    ]

    refund = await add_credits(db_session, user_id, 20, "refund:refundable-charge")

    after = await _entries_for(db_session, account.id)
    after_snapshot = [
        (entry.id, entry.transfer_id, entry.previous_balance, entry.current_balance)
        for entry in after[: len(before_snapshot)]
    ]
    assert refund.id != charge.id
    assert after_snapshot == before_snapshot
    assert len(after) == len(before) + 1
    assert after[-1].previous_balance == Decimal("30")
    assert after[-1].current_balance == Decimal("50")


@pytest.mark.asyncio
async def test_transfer_metadata_and_idempotency_key_are_preserved(db_session):
    transfer = await deduct_credits_after_grant(
        db_session,
        user_id="student-metadata",
        tx_id="pod-42-sequence-7",
        description="pod_usage:pod-42:rtx4090",
    )

    await db_session.refresh(transfer)
    assert transfer.id == "pod-42-sequence-7"
    assert transfer.type == "pod_usage:pod-42:rtx4090"
    assert transfer.metadata_ == {"description": "pod_usage:pod-42:rtx4090"}


async def deduct_credits_after_grant(
    db_session, *, user_id: str, tx_id: str, description: str
) -> Transfer:
    await add_credits(db_session, user_id, 10, "initial_grant")
    return await deduct_credits(
        db_session,
        user_id,
        1,
        description=description,
        tx_id=tx_id,
    )
