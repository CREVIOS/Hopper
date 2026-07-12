import pytest
from fastapi import HTTPException

from app.models.course import Course
from app.routers.courses import (
    _course_for_manager,
    allocate_to_course,
    list_my_courses,
)
from app.schemas.course import BulkAllocateRequest
from app.schemas.user import TokenPayload


def _payload(role: str, sub: str = "prof-1") -> TokenPayload:
    return TokenPayload(
        sub=sub,
        email="user@example.com",
        name="Test User",
        role=role,
        exp=4_102_444_800,
    )


def _course(professor_id: str = "prof-1") -> Course:
    return Course(
        id="c-1",
        code="CSE-4108",
        name="Operating Systems",
        description="",
        professor_id=professor_id,
        is_active=True,
    )


class FakeDB:
    """Stands in for AsyncSession; course lookup is monkeypatched per test."""


@pytest.fixture
def owned_course(monkeypatch):
    course = _course(professor_id="prof-1")

    async def fake_get_course(db, course_id):
        return course if course_id == "c-1" else None

    monkeypatch.setattr("app.services.course_service.get_course", fake_get_course)
    return course


# --- _course_for_manager: the authorization gate every route depends on -------


async def test_owning_professor_can_manage_their_course(owned_course):
    result = await _course_for_manager(FakeDB(), "c-1", _payload("professor", "prof-1"))

    assert result is owned_course


async def test_admin_can_manage_any_course(owned_course):
    result = await _course_for_manager(FakeDB(), "c-1", _payload("admin", "admin-1"))

    assert result is owned_course


async def test_other_professor_cannot_manage_someone_elses_course(owned_course):
    with pytest.raises(HTTPException) as exc:
        await _course_for_manager(FakeDB(), "c-1", _payload("professor", "prof-2"))

    assert exc.value.status_code == 403


async def test_student_cannot_manage_a_course(owned_course):
    with pytest.raises(HTTPException) as exc:
        await _course_for_manager(FakeDB(), "c-1", _payload("student", "stu-1"))

    assert exc.value.status_code == 403


async def test_missing_course_is_404(owned_course):
    with pytest.raises(HTTPException) as exc:
        await _course_for_manager(FakeDB(), "nope", _payload("admin", "admin-1"))

    assert exc.value.status_code == 404


# --- role gates --------------------------------------------------------------


async def test_list_my_courses_rejects_non_professor():
    with pytest.raises(HTTPException) as exc:
        await list_my_courses(current_user=_payload("student", "stu-1"), db=FakeDB())

    assert exc.value.status_code == 403


async def test_admin_cannot_bulk_allocate_from_a_professors_balance(owned_course):
    """An admin manages the course but has no personal balance to spend — bulk
    allocation must come from the owning professor, so this is a 403."""
    with pytest.raises(HTTPException) as exc:
        await allocate_to_course(
            "c-1",
            BulkAllocateRequest(amount=5),
            current_user=_payload("admin", "admin-1"),
            db=FakeDB(),
        )

    assert exc.value.status_code == 403


async def test_bulk_allocate_rejects_empty_roster(owned_course, monkeypatch):
    async def fake_roster(db, course_id):
        return []

    monkeypatch.setattr("app.services.course_service.list_roster", fake_roster)

    with pytest.raises(HTTPException) as exc:
        await allocate_to_course(
            "c-1",
            BulkAllocateRequest(amount=5),
            current_user=_payload("professor", "prof-1"),
            db=FakeDB(),
        )

    assert exc.value.status_code == 400


async def test_bulk_allocate_returns_402_when_professor_cannot_cover_total(
    owned_course, monkeypatch
):
    """All-or-nothing: an underfunded professor funds nobody."""
    students = [type("U", (), {"id": f"stu-{i}"})() for i in range(3)]

    async def fake_roster(db, course_id):
        return students

    async def fake_allocate(db, from_user_id, to_user_ids, amount, description):
        raise ValueError("Insufficient credits: have 10.0, need 30.0")

    monkeypatch.setattr("app.services.course_service.list_roster", fake_roster)
    monkeypatch.setattr("app.routers.courses.allocate_to_many", fake_allocate)

    with pytest.raises(HTTPException) as exc:
        await allocate_to_course(
            "c-1",
            BulkAllocateRequest(amount=10),
            current_user=_payload("professor", "prof-1"),
            db=FakeDB(),
        )

    assert exc.value.status_code == 402
    assert "Insufficient credits" in exc.value.detail


async def test_bulk_allocate_funds_every_student_on_the_roster(owned_course, monkeypatch):
    students = [type("U", (), {"id": f"stu-{i}"})() for i in range(3)]
    captured = {}

    async def fake_roster(db, course_id):
        return students

    async def fake_allocate(db, from_user_id, to_user_ids, amount, description):
        captured["from"] = from_user_id
        captured["to"] = to_user_ids
        captured["amount"] = amount
        return type("T", (), {"id": "transfer-1"})()

    monkeypatch.setattr("app.services.course_service.list_roster", fake_roster)
    monkeypatch.setattr("app.routers.courses.allocate_to_many", fake_allocate)

    result = await allocate_to_course(
        "c-1",
        BulkAllocateRequest(amount=10),
        current_user=_payload("professor", "prof-1"),
        db=FakeDB(),
    )

    assert captured["from"] == "prof-1"  # spent from the professor's own balance
    assert captured["to"] == ["stu-0", "stu-1", "stu-2"]
    assert result["students"] == 3
    assert result["total"] == 30
    assert result["transfer_id"] == "transfer-1"
