"""Grant credits to any user from the system account (dev/testing helper).

Why this exists: POST /credits/allocate deliberately refuses self-allocation, so
an admin cannot fund their own account through the UI. That's correct for the
product, but it leaves a lone admin on a fresh DB with 0 credits and no way to
launch a VM to test with.

Goes through credit_service.add_credits, so it writes a proper balanced
double-entry transfer (system -> user). Do NOT hand-write INSERTs into
ledger_entries instead: each row carries a running previous_balance /
current_balance, and a manual insert corrupts that chain.

Usage:
    cd services/api-gateway
    PYTHONPATH=. poetry run python ../../scripts/grant_credits.py admin@du.ac.bd 500
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.database import async_session
from app.models.user import User
from app.services.credit_service import add_credits, get_balance


async def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    email, raw_amount = sys.argv[1], sys.argv[2]
    try:
        amount = float(raw_amount)
    except ValueError:
        print(f"error: '{raw_amount}' is not a number")
        return 2
    if amount <= 0:
        print("error: amount must be positive")
        return 2

    async with async_session() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"error: no user with email {email!r}")
            return 1

        before = await get_balance(db, user.id)
        transfer = await add_credits(db, user.id, amount, "dev_grant")
        after = await get_balance(db, user.id)

        print(f"granted {amount:g} credits to {email} ({user.role})")
        print(f"  balance: {before:g} -> {after:g}")
        print(f"  transfer: {transfer.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
