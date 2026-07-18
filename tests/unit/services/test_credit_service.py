from sqlalchemy.orm import DeclarativeBase

from app.models.credit_ledger import Account, Transfer
from app.services import credit_service as credit_service_module


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])
        self.added = []
        self.flushed = False
        self.committed = False
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        value = self.execute_results.pop(0)
        return FakeResult(value)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True


async def test_get_or_create_account_returns_existing_account():
    account = Account(
        id="acct-1",
        name="user:user-1",
        type="asset",
        owner_id="user-1",
        owner_type="user",
    )
    db = FakeDB(execute_results=[account])

    result = await credit_service_module.get_or_create_account(db, "user-1")

    assert result is account
    assert db.added == []
    assert db.flushed is False


async def test_get_or_create_account_creates_new_account():
    db = FakeDB(execute_results=[None])

    account = await credit_service_module.get_or_create_account(db, "user-1")

    assert account.owner_id == "user-1"
    assert account.owner_type == "user"
    assert account.type == "asset"
    assert account.name == "user:user-1"
    assert db.added == [account]
    assert db.flushed is True


async def test_ensure_system_account_creates_default_account():
    db = FakeDB(execute_results=[None])

    account = await credit_service_module.ensure_system_account(db)

    assert account.id == credit_service_module.SYSTEM_ACCOUNT_ID
    assert account.type == "liability"
    assert account.owner_type == "system"
    assert db.added == [account]
    assert db.flushed is True


async def test_get_balance_returns_zero_when_no_ledger_entry(monkeypatch):
    async def fake_get_or_create_account(db, user_id, **kwargs):
        return Account(
            id="acct-1",
            name="user:user-1",
            type="asset",
            owner_id=user_id,
            owner_type="user",
        )

    monkeypatch.setattr("app.services.credit_service.get_or_create_account", fake_get_or_create_account)
    db = FakeDB(execute_results=[None])

    balance = await credit_service_module.get_balance(db, "user-1")

    assert balance == 0.0


async def test_add_credits_creates_transfer_and_balanced_entries(monkeypatch):
    user_account = Account(
        id="acct-user",
        name="user:user-1",
        type="asset",
        owner_id="user-1",
        owner_type="user",
    )
    system_account = Account(
        id=credit_service_module.SYSTEM_ACCOUNT_ID,
        name="system",
        type="liability",
        owner_id=None,
        owner_type="system",
    )

    async def fake_get_or_create_account(db, user_id):
        return user_account

    async def fake_ensure_system_account(db):
        return system_account

    balances = iter([25.0])

    async def fake_get_balance(db, user_id):
        return next(balances)

    monkeypatch.setattr("app.services.credit_service.get_or_create_account", fake_get_or_create_account)
    monkeypatch.setattr("app.services.credit_service.ensure_system_account", fake_ensure_system_account)
    monkeypatch.setattr("app.services.credit_service.get_balance", fake_get_balance)

    db = FakeDB(execute_results=[50.0])

    transfer = await credit_service_module.add_credits(db, "user-1", 10.0, "grant")

    assert transfer.type == "grant"
    assert db.committed is True
    assert len(db.added) == 3
    debit_entry = db.added[1]
    credit_entry = db.added[2]
    assert debit_entry.account_id == system_account.id
    assert debit_entry.current_balance == 40.0
    assert credit_entry.account_id == user_account.id
    assert credit_entry.current_balance == 35.0


async def test_allocate_between_users_rejects_same_user():
    db = FakeDB()

    try:
        await credit_service_module.allocate_between_users(db, "user-1", "user-1", 10.0)
    except ValueError as exc:
        assert str(exc) == "cannot allocate to yourself"
    else:
        raise AssertionError("expected ValueError")


async def test_allocate_between_users_creates_transfer_and_entries(monkeypatch):
    source = Account(
        id="acct-source",
        name="user:teacher",
        type="asset",
        owner_id="teacher",
        owner_type="user",
    )
    dest = Account(
        id="acct-dest",
        name="user:student",
        type="asset",
        owner_id="student",
        owner_type="user",
    )

    async def fake_get_or_create_account(db, user_id):
        return source if user_id == "teacher" else dest

    balances = {"teacher": 50.0, "student": 5.0}

    async def fake_get_balance(db, user_id):
        return balances[user_id]

    monkeypatch.setattr("app.services.credit_service.get_or_create_account", fake_get_or_create_account)
    monkeypatch.setattr("app.services.credit_service.get_balance", fake_get_balance)

    db = FakeDB(execute_results=[None])

    transfer = await credit_service_module.allocate_between_users(
        db, "teacher", "student", 10.0, "teacher_allocation"
    )

    assert transfer.type == "teacher_allocation"
    assert db.committed is True
    assert len(db.added) == 3
    debit_entry = db.added[1]
    credit_entry = db.added[2]
    assert debit_entry.current_balance == 40.0
    assert credit_entry.current_balance == 15.0


async def test_deduct_credits_returns_existing_transfer_when_tx_id_exists(monkeypatch):
    user_account = Account(
        id="acct-user",
        name="user:user-1",
        type="asset",
        owner_id="user-1",
        owner_type="user",
    )
    existing_transfer = Transfer(id="tx-1", type="pod_usage", metadata_={}, event_at=None)

    async def fake_get_or_create_account(db, user_id):
        return user_account

    monkeypatch.setattr("app.services.credit_service.get_or_create_account", fake_get_or_create_account)

    db = FakeDB(execute_results=[None, existing_transfer])

    result = await credit_service_module.deduct_credits(db, "user-1", 2.5, tx_id="tx-1")

    assert result is existing_transfer
    assert db.committed is False


async def test_deduct_credits_raises_on_insufficient_balance(monkeypatch):
    user_account = Account(
        id="acct-user",
        name="user:user-1",
        type="asset",
        owner_id="user-1",
        owner_type="user",
    )

    async def fake_get_or_create_account(db, user_id):
        return user_account

    async def fake_get_balance(db, user_id):
        return 1.0

    monkeypatch.setattr("app.services.credit_service.get_or_create_account", fake_get_or_create_account)
    monkeypatch.setattr("app.services.credit_service.get_balance", fake_get_balance)

    db = FakeDB(execute_results=[None, None])

    try:
        await credit_service_module.deduct_credits(db, "user-1", 2.5, tx_id="tx-2")
    except ValueError as exc:
        assert "Insufficient credits" in str(exc)
    else:
        raise AssertionError("expected ValueError")


async def test_deduct_credits_creates_transfer_and_balanced_entries(monkeypatch):
    user_account = Account(
        id="acct-user",
        name="user:user-1",
        type="asset",
        owner_id="user-1",
        owner_type="user",
    )
    system_account = Account(
        id=credit_service_module.SYSTEM_ACCOUNT_ID,
        name="system",
        type="liability",
        owner_id=None,
        owner_type="system",
    )

    async def fake_get_or_create_account(db, user_id):
        return user_account

    async def fake_get_balance(db, user_id):
        return 25.0

    async def fake_ensure_system_account(db):
        return system_account

    monkeypatch.setattr("app.services.credit_service.get_or_create_account", fake_get_or_create_account)
    monkeypatch.setattr("app.services.credit_service.get_balance", fake_get_balance)
    monkeypatch.setattr("app.services.credit_service.ensure_system_account", fake_ensure_system_account)

    db = FakeDB(execute_results=[None, None, 50.0])

    transfer = await credit_service_module.deduct_credits(
        db, "user-1", 10.0, description="pod_usage", tx_id="tx-3"
    )

    assert transfer.id == "tx-3"
    assert db.committed is True
    assert len(db.added) == 3
    debit_entry = db.added[1]
    credit_entry = db.added[2]
    assert debit_entry.current_balance == 15.0
    assert credit_entry.current_balance == 60.0


async def test_grant_signup_bonus_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(credit_service_module.settings, "signup_grant_credits", 0.0)
    called = {}

    async def fake_add_credits(*args, **kwargs):
        called["yes"] = True

    monkeypatch.setattr(credit_service_module, "add_credits", fake_add_credits)

    result = await credit_service_module.grant_signup_bonus(object(), "user-1")

    assert result is None
    assert "yes" not in called


async def test_grant_signup_bonus_grants_configured_amount(monkeypatch):
    monkeypatch.setattr(credit_service_module.settings, "signup_grant_credits", 15.0)
    captured = {}

    async def fake_add_credits(db, user_id, amount, description):
        captured.update(user_id=user_id, amount=amount, description=description)
        return "transfer-sentinel"

    monkeypatch.setattr(credit_service_module, "add_credits", fake_add_credits)

    result = await credit_service_module.grant_signup_bonus(object(), "user-42")

    assert result == "transfer-sentinel"
    assert captured == {
        "user_id": "user-42",
        "amount": 15.0,
        "description": "signup_welcome_grant",
    }
