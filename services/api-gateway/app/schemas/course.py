from pydantic import BaseModel, Field


class CourseResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str
    professor_id: str
    is_active: bool
    # Denormalised for list views so the UI doesn't need an N+1 roster fetch.
    professor_name: str | None = None
    enrolled_count: int = 0

    model_config = {"from_attributes": True}


class CourseCreateRequest(BaseModel):
    # Course codes are human-facing identifiers (e.g. "CSE-4108"); kept uppercase
    # alphanumeric + dash so they read consistently across the roster views.
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=500)
    professor_id: str = Field(min_length=1)


class CourseUpdateRequest(BaseModel):
    # All optional — only provided fields change. ``code`` is immutable once
    # issued so historical roster references stay meaningful.
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    professor_id: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class CourseMemberResponse(BaseModel):
    """A student on a course roster, with their current credit balance."""

    id: str
    email: str
    name: str
    balance: float


class EnrollRequest(BaseModel):
    user_id: str = Field(min_length=1)


class BulkAllocateRequest(BaseModel):
    """Allocate ``amount`` credits to every enrolled student on the course.

    Bounded exactly like the single-student AllocateRequest so a fat-finger
    value can't overflow the NUMERIC(12,4) ledger columns.
    """

    amount: float = Field(gt=0, le=1_000_000_000)
    description: str = Field(default="course_allocation", max_length=500)
