import pytest
from fastapi import HTTPException

from app.models.user import User
from app.routers.credits import AllocateRequest, _users_with_balance, allocate_credits
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


class FakeDB:
    def __init__(self, target=None, users=None):
        self.target = target
        self.users = users or []

    async def get(self, model, user_id):
        return self.target

    async def execute(self, stmt):
        return FakeExecuteResult(self.users)


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

    async def fake_add_credits(db_obj, user_id, amount, description):
        return type("Transfer", (), {"id": "tx-1"})()

    monkeypatch.setattr("app.routers.credits.add_credits", fake_add_credits)

    result = await allocate_credits(
        AllocateRequest(user_id="user-2", amount=10, description="grant"),
        current_user=_payload("admin"),
        db=db,
    )

    assert result == {"message": "granted", "transfer_id": "tx-1"}


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
