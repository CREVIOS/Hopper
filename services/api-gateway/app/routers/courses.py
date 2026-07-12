"""Course roster + course-scoped credit allocation.

Admins create courses and assign the owning professor (see routers/admin.py).
This router is what that professor uses day to day: view their courses, manage
the roster, and fund the whole class in one go.

Authorization rule throughout: **admin, or the professor who owns the course.**
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.course import Course
from app.models.user import User
from app.schemas.course import (
    BulkAllocateRequest,
    CourseMemberResponse,
    CourseResponse,
    EnrollRequest,
)
from app.schemas.user import TokenPayload
from app.services import course_service
from app.services.credit_service import allocate_to_many, get_balance
from app.services.notification_service import create_notification_safely

logger = logging.getLogger(__name__)

router = APIRouter()


async def _course_for_manager(
    db: AsyncSession, course_id: str, current_user: TokenPayload
) -> Course:
    """Fetch a course the caller is allowed to manage, else 403/404.

    404 is only for a course that genuinely doesn't exist; a professor poking at
    someone else's course gets a 403 (the id is not a secret — it's exposed in
    the admin console — so there's nothing to hide by pretending it's missing).
    """
    course = await course_service.get_course(db, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    if current_user.role == "admin":
        return course
    if current_user.role == "professor" and course.professor_id == current_user.sub:
        return course

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the owning professor or an admin can manage this course",
    )


@router.get("/mine", response_model=list[CourseResponse])
async def list_my_courses(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The active courses owned by the calling professor."""
    if current_user.role != "professor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Teachers only"
        )

    courses = await course_service.list_courses(db, professor_id=current_user.sub)
    counts = await course_service.enrolled_counts(db, [c.id for c in courses])
    return [
        CourseResponse(
            id=c.id,
            code=c.code,
            name=c.name,
            description=c.description,
            professor_id=c.professor_id,
            is_active=c.is_active,
            professor_name=current_user.name,
            enrolled_count=counts.get(c.id, 0),
        )
        for c in courses
    ]


@router.get("/{course_id}/roster", response_model=list[CourseMemberResponse])
async def get_roster(
    course_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The students enrolled in a course, with their credit balances."""
    await _course_for_manager(db, course_id, current_user)

    students = await course_service.list_roster(db, course_id)
    return [
        CourseMemberResponse(
            id=s.id, email=s.email, name=s.name, balance=await get_balance(db, s.id)
        )
        for s in students
    ]


@router.post("/{course_id}/enrollments", status_code=201)
async def enroll_student(
    course_id: str,
    body: EnrollRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a student to the roster. Idempotent — re-enrolling is a no-op."""
    await _course_for_manager(db, course_id, current_user)

    student = await db.get(User, body.user_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if student.role != "student":
        raise HTTPException(status_code=400, detail="Only students can be enrolled")

    created = await course_service.enroll(db, course_id, body.user_id)
    if created is None:
        return {"message": "already_enrolled", "user_id": body.user_id}
    return {"message": "enrolled", "user_id": body.user_id}


@router.delete("/{course_id}/enrollments/{user_id}")
async def unenroll_student(
    course_id: str,
    user_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a student from the roster. Credits already allocated are not clawed back."""
    await _course_for_manager(db, course_id, current_user)

    if not await course_service.unenroll(db, course_id, user_id):
        raise HTTPException(status_code=404, detail="Student is not enrolled in this course")
    return {"message": "unenrolled", "user_id": user_id}


@router.post("/{course_id}/allocate")
async def allocate_to_course(
    course_id: str,
    body: BulkAllocateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Allocate ``amount`` credits to **every student on the roster**, from the
    calling professor's own balance.

    All-or-nothing: if the professor can't cover ``amount × roster size`` the
    whole allocation is rejected with 402 and nobody is funded.
    """
    course = await _course_for_manager(db, course_id, current_user)

    # An admin has no personal balance to spend from — the source must be the
    # course's professor, and only they can authorise spending their credits.
    if current_user.role != "professor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owning professor can allocate from their balance",
        )

    students = await course_service.list_roster(db, course_id)
    if not students:
        raise HTTPException(status_code=400, detail="Course has no enrolled students")

    try:
        transfer = await allocate_to_many(
            db,
            current_user.sub,
            [s.id for s in students],
            body.amount,
            body.description or "course_allocation",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e))

    logger.info(
        "course_allocation course=%s professor=%s students=%d per_student=%s",
        course.code, current_user.sub, len(students), body.amount,
    )

    # Tell each student they've been funded. Best-effort — the ledger transfer
    # has already committed and must not be rolled back by a notification error.
    for student in students:
        await create_notification_safely(
            db,
            user_id=student.id,
            type="credits_received",
            severity="success",
            title="Credits received",
            body=f"{body.amount:g} credits for {course.code}.",
            action_url="/credits",
            dedupe_key=f"credits-received:{transfer.id}:{student.id}",
            metadata={
                "transfer_id": transfer.id,
                "amount": body.amount,
                "course_id": course.id,
                "course_code": course.code,
            },
        )
    return {
        "message": "allocated",
        "transfer_id": transfer.id,
        "students": len(students),
        "per_student": body.amount,
        "total": body.amount * len(students),
    }
