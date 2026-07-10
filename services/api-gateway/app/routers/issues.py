"""Issue reports — students flag mid-session problems for admin triage."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.issue_report import IssueReport
from app.schemas.user import TokenPayload

router = APIRouter()


class IssueCreate(BaseModel):
    pod_id: str | None = None
    description: str = Field(min_length=5, max_length=2000)


class IssueOut(BaseModel):
    id: str
    user_id: str
    pod_id: str | None
    description: str
    status: str
    response: str | None = None
    created_at: datetime
    resolved_at: datetime | None


class ResolveRequest(BaseModel):
    response: str | None = Field(default=None, max_length=2000)


@router.post("/", response_model=IssueOut, status_code=201)
async def create_issue(
    body: IssueCreate,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Report a problem with an active session."""
    issue = IssueReport(
        id=str(uuid.uuid4()),
        user_id=current_user.sub,
        pod_id=body.pod_id,
        description=body.description.strip(),
        status="open",
    )
    db.add(issue)
    await db.commit()
    await db.refresh(issue)
    return issue


@router.get("/me", response_model=list[IssueOut])
async def list_my_issues(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IssueReport)
        .where(IssueReport.user_id == current_user.sub)
        .order_by(IssueReport.created_at.desc())
        .limit(50)
    )
    return list(result.scalars())


@router.get("/admin", response_model=list[IssueOut])
async def list_all_issues(
    status: str | None = None,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    stmt = select(IssueReport).order_by(IssueReport.created_at.desc()).limit(200)
    if status:
        stmt = stmt.where(IssueReport.status == status)
    result = await db.execute(stmt)
    return list(result.scalars())


@router.post("/admin/{issue_id}/resolve", response_model=IssueOut)
async def resolve_issue(
    issue_id: str,
    body: ResolveRequest | None = None,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    issue = await db.get(IssueReport, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue.status = "resolved"
    issue.resolved_at = datetime.utcnow()
    if body and body.response:
        issue.response = body.response.strip()
    await db.commit()
    await db.refresh(issue)
    return issue
