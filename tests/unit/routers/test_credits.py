import pytest
from fastapi import HTTPException

from app.models.user import User
from app.routers.credits import (
    AllocateRequest,
    _users_with_balance,
    allocate_credits,
    get_credit_balance,
    get_history,
    list_students,
    list_teachers,
)
from app.schemas.user import TokenPayload


def _payload(role: str, sub: str = "user-1") -> TokenPayload:
    return TokenPayload(
        sub=sub,
        email="user@example.com",
        name="Test User",
        role=role,
        exp=1234567890,
    )


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, target=None, users=None):
        self.target = target
        self.users = users or []

    async def get(self, model, user_id):
        return self.target

    async def execute(self, stmt):
        return FakeExecuteResult(self.users)


async def test_get_credit_balance_returns_account_id_and_balance(monkeypatch):
    account = type("Account", (), {"id": "acct-1"})()

    async def fake_get_balance(db, user_id):
        return 42.5

    async def fake_get_or_create_account(db, user_id, **kwargs):
        return account

    monkeypatch.setattr("app.routers.credits.get_balance", fake_get_balance)
    monkeypatch.setattr("app.routers.credits.get_or_create_account", fake_get_or_create_account)

    result = await get_credit_balance(current_user=_payload("student"), db=FakeDB())

    assert result.account_id == "acct-1"
    assert result.balance == 42.5


async def test_get_history_formats_credit_and_debit_entries(monkeypatch):
    account = type("Account", (), {"id": "acct-1"})()
    entry_debit = type(
        "Entry",
        (),
        {
            "id": "e1",
            "account_id": "acct-1",
            "amount": 5,
            "direction": 1,
            "created_at": "2026-01-01T12:00:00",
        },
    )()
    entry_credit = type(
        "Entry",
        (),
        {
            "id": "e2",
            "account_id": "acct-1",
            "amount": 3,
            "direction": -1,
            "created_at": "2026-01-01T13:00:00",
        },
    )()

    async def fake_get_or_create_account(db, user_id):
        return account

    monkeypatch.setattr("app.routers.credits.get_or_create_account", fake_get_or_create_account)

    db = FakeDB(users=[(entry_debit, "pod_usage"), (entry_credit, "allocation")])

    result = await get_history(current_user=_payload("student"), db=db)

    assert result[0].direction == "debit"
    assert result[0].amount == 5.0
    assert result[1].direction == "credit"
    assert result[1].type == "allocation"


async def test_users_with_balance_returns_serialized_users(monkeypatch):
    users = [
        User(id="u1", email="teacher@example.com", name="Teacher", role="professor"),
        User(id="u2", email="teacher2@example.com", name="Teacher 2", role="professor"),
    ]
    db = FakeDB(users=users)

    async def fake_get_balance(db_obj, user_id):
        return {"u1": 10.0, "u2": 20.0}[user_id]

    monkeypatch.setattr("app.routers.credits.get_balance", fake_get_balance)

    result = await _users_with_balance(db, "professor")

    assert result == [
        {"id": "u1", "email": "teacher@example.com", "name": "Teacher", "balance": 10.0},
        {"id": "u2", "email": "teacher2@example.com", "name": "Teacher 2", "balance": 20.0},
    ]


async def test_list_teachers_requires_admin():
    with pytest.raises(HTTPException) as exc_info:
        await list_teachers(current_user=_payload("professor"), db=FakeDB())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admins only"


async def test_list_teachers_returns_teacher_balances(monkeypatch):
    expected = [{"id": "u1", "email": "teacher@example.com", "name": "Teacher", "balance": 10.0}]

    async def fake_users_with_balance(db, role):
        assert role == "professor"
        return expected

    monkeypatch.setattr("app.routers.credits._users_with_balance", fake_users_with_balance)

    result = await list_teachers(current_user=_payload("admin"), db=FakeDB())

    assert result == expected


async def test_list_students_requires_admin_or_professor():
    with pytest.raises(HTTPException) as exc_info:
        await list_students(current_user=_payload("student"), db=FakeDB())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Teachers only"


async def test_list_students_returns_student_balances(monkeypatch):
    expected = [{"id": "u2", "email": "student@example.com", "name": "Student", "balance": 5.0}]

    async def fake_users_with_balance(db, role):
        assert role == "student"
        return expected

    monkeypatch.setattr("app.routers.credits._users_with_balance", fake_users_with_balance)

    result = await list_students(current_user=_payload("professor"), db=FakeDB())

    assert result == expected


async def test_allocate_credits_rejects_self_allocation():
    with pytest.raises(HTTPException) as exc_info:
        await allocate_credits(
            AllocateRequest(user_id="user-1", amount=10),
            current_user=_payload("admin", sub="user-1"),
            db=FakeDB(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Cannot allocate credits to yourself"


async def test_allocate_credits_admin_grants_to_target(monkeypatch):
    db = FakeDB(target=User(id="user-2", email="student@example.com", name="Student", role="student"))
    notified = {}

    async def fake_add_credits(db_obj, user_id, amount, description):
        return type("Transfer", (), {"id": "tx-1"})()

    async def fake_notify(db_obj, user_id, **kwargs):
        notified["user_id"] = user_id
        notified.update(kwargs)

    monkeypatch.setattr("app.routers.credits.add_credits", fake_add_credits)
    monkeypatch.setattr("app.routers.credits.notify", fake_notify)

    result = await allocate_credits(
        AllocateRequest(user_id="user-2", amount=10, description="grant"),
        current_user=_payload("admin"),
        db=db,
    )

    assert result == {"message": "granted", "transfer_id": "tx-1"}
    # The recipient gets a "credits received" notification.
    assert notified["user_id"] == "user-2"
    assert notified["title"] == "Credits received"


async def test_allocate_credits_rejects_missing_recipient():
    with pytest.raises(HTTPException) as exc_info:
        await allocate_credits(
            AllocateRequest(user_id="missing", amount=10),
            current_user=_payload("admin"),
            db=FakeDB(target=None),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Recipient not found"


async def test_allocate_credits_professor_rejects_non_student_target():
    db = FakeDB(target=User(id="user-2", email="teacher@example.com", name="Teacher", role="professor"))

    with pytest.raises(HTTPException) as exc_info:
        await allocate_credits(
            AllocateRequest(user_id="user-2", amount=10),
            current_user=_payload("professor"),
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Teachers can only allocate to students"


async def test_allocate_credits_professor_maps_insufficient_credit_error(monkeypatch):
    db = FakeDB(target=User(id="user-2", email="student@example.com", name="Student", role="student"))

    async def fake_allocate_between_users(db_obj, from_user_id, to_user_id, amount, description):
        raise ValueError("Insufficient credits: have 0, need 10")

    monkeypatch.setattr("app.routers.credits.allocate_between_users", fake_allocate_between_users)

    with pytest.raises(HTTPException) as exc_info:
        await allocate_credits(
            AllocateRequest(user_id="user-2", amount=10),
            current_user=_payload("professor"),
            db=db,
        )

    assert exc_info.value.status_code == 402
    assert "Insufficient credits" in exc_info.value.detail


async def test_allocate_credits_professor_allocates_to_student(monkeypatch):
    db = FakeDB(target=User(id="user-2", email="student@example.com", name="Student", role="student"))

    async def fake_allocate_between_users(db_obj, from_user_id, to_user_id, amount, description):
        assert from_user_id == "user-1"
        assert to_user_id == "user-2"
        assert amount == 10
        return type("Transfer", (), {"id": "tx-2"})()

    async def fake_notify(db_obj, user_id, **kwargs):
        notified["user_id"] = user_id
        notified.update(kwargs)

    notified = {}
    monkeypatch.setattr("app.routers.credits.allocate_between_users", fake_allocate_between_users)
    monkeypatch.setattr("app.routers.credits.notify", fake_notify)

    result = await allocate_credits(
        AllocateRequest(user_id="user-2", amount=10, description="teacher_allocation"),
        current_user=_payload("professor"),
        db=db,
    )

    assert result == {"message": "allocated", "transfer_id": "tx-2"}
    assert notified["user_id"] == "user-2"
    assert notified["title"] == "Credits received"


async def test_allocate_credits_rejects_non_admin_non_professor():
    db = FakeDB(target=User(id="user-2", email="student@example.com", name="Student", role="student"))

    with pytest.raises(HTTPException) as exc_info:
        await allocate_credits(
            AllocateRequest(user_id="user-2", amount=10),
            current_user=_payload("student"),
            db=db,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Only admins and teachers can allocate credits"
