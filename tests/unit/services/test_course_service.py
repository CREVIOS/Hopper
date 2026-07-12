from app.models.course import Course
from app.services import course_service


class FakeDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass


def _course() -> Course:
    return Course(
        id="c-1",
        code="CSE-4108",
        name="Operating Systems",
        description="OS lab",
        professor_id="prof-1",
        is_active=True,
    )


async def test_update_course_applies_only_provided_fields():
    course = _course()
    db = FakeDB()

    await course_service.update_course(db, course, {"name": "Advanced OS", "description": None})

    assert course.name == "Advanced OS"
    assert course.description == "OS lab"  # None is skipped, not written
    assert db.commits == 1


async def test_update_course_ignores_id_and_code_changes():
    course = _course()
    db = FakeDB()

    await course_service.update_course(
        db, course, {"id": "hacked", "code": "OTHER-1", "name": "Renamed"}
    )

    assert course.id == "c-1"      # PK is immutable
    assert course.code == "CSE-4108"  # code is immutable — roster history depends on it
    assert course.name == "Renamed"


async def test_update_course_can_reassign_professor_and_deactivate():
    course = _course()
    db = FakeDB()

    await course_service.update_course(
        db, course, {"professor_id": "prof-2", "is_active": False}
    )

    assert course.professor_id == "prof-2"
    assert course.is_active is False


async def test_deactivate_course_sets_inactive():
    course = _course()
    db = FakeDB()

    await course_service.deactivate_course(db, course)

    assert course.is_active is False
    assert db.commits == 1
