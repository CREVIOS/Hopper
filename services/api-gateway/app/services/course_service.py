"""Data access for courses and their student rosters.

Courses are owned by a professor (``professor_id``). Admins create and assign
them; the owning professor manages the roster. Deletion is a soft-delete
(``is_active = False``) so historical allocations still reference a real course.
"""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.course_enrollment import CourseEnrollment
from app.models.user import User


async def list_courses(
    db: AsyncSession,
    *,
    professor_id: str | None = None,
    include_inactive: bool = False,
) -> list[Course]:
    stmt = select(Course)
    if professor_id is not None:
        stmt = stmt.where(Course.professor_id == professor_id)
    if not include_inactive:
        stmt = stmt.where(Course.is_active.is_(True))
    return list((await db.execute(stmt.order_by(Course.code))).scalars().all())


async def get_course(db: AsyncSession, course_id: str) -> Course | None:
    return (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()


async def get_course_by_code(db: AsyncSession, code: str) -> Course | None:
    return (await db.execute(select(Course).where(Course.code == code))).scalar_one_or_none()


async def create_course(
    db: AsyncSession, *, code: str, name: str, description: str, professor_id: str
) -> Course:
    course = Course(
        id=str(uuid.uuid4()),
        code=code,
        name=name,
        description=description,
        professor_id=professor_id,
        is_active=True,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


async def update_course(db: AsyncSession, course: Course, fields: dict) -> Course:
    """Apply only the provided non-None fields. ``id`` and ``code`` are immutable."""
    for key, value in fields.items():
        if key in ("id", "code") or value is None:
            continue
        setattr(course, key, value)
    await db.commit()
    await db.refresh(course)
    return course


async def deactivate_course(db: AsyncSession, course: Course) -> Course:
    """Soft-delete. The roster is preserved so past allocations stay explicable."""
    course.is_active = False
    await db.commit()
    await db.refresh(course)
    return course


async def enrolled_counts(db: AsyncSession, course_ids: list[str]) -> dict[str, int]:
    """Roster sizes for many courses in one query (avoids an N+1 in list views)."""
    if not course_ids:
        return {}
    rows = await db.execute(
        select(CourseEnrollment.course_id, func.count())
        .where(CourseEnrollment.course_id.in_(course_ids))
        .group_by(CourseEnrollment.course_id)
    )
    return {course_id: count for course_id, count in rows.all()}


async def professor_names(db: AsyncSession, professor_ids: list[str]) -> dict[str, str]:
    if not professor_ids:
        return {}
    rows = await db.execute(
        select(User.id, User.name).where(User.id.in_(professor_ids))
    )
    return {user_id: name for user_id, name in rows.all()}


async def list_roster(db: AsyncSession, course_id: str) -> list[User]:
    """The students enrolled in a course, ordered by name."""
    stmt = (
        select(User)
        .join(CourseEnrollment, CourseEnrollment.user_id == User.id)
        .where(CourseEnrollment.course_id == course_id)
        .order_by(User.name)
    )
    return list((await db.execute(stmt)).scalars().all())


async def is_enrolled(db: AsyncSession, course_id: str, user_id: str) -> bool:
    row = await db.execute(
        select(CourseEnrollment.id).where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.user_id == user_id,
        )
    )
    return row.scalar_one_or_none() is not None


async def enroll(db: AsyncSession, course_id: str, user_id: str) -> CourseEnrollment | None:
    """Enroll a student. Returns None if they were already on the roster —
    the (course_id, user_id) unique constraint makes this idempotent."""
    if await is_enrolled(db, course_id, user_id):
        return None
    row = CourseEnrollment(id=str(uuid.uuid4()), course_id=course_id, user_id=user_id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def unenroll(db: AsyncSession, course_id: str, user_id: str) -> bool:
    """Remove a student from the roster. Returns False if they weren't on it."""
    result = await db.execute(
        delete(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.user_id == user_id,
        )
    )
    await db.commit()
    return result.rowcount > 0
