from datetime import datetime

import pytest
from fastapi import HTTPException

from app.routers.issues import IssueCreate, create_issue, list_all_issues, resolve_issue
from app.schemas.user import TokenPayload


def _payload(role: str = "student") -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="user@example.com",
        name="Test User",
        role=role,
        exp=1234567890,
    )


class FakeDB:
    def __init__(self, issue=None):
        self.issue = issue
        self.added = None
        self.committed = False
        self.refreshed = False
        self.executed = None

    def add(self, obj):
        self.added = obj

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        self.refreshed = True
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(2026, 1, 1, 12, 0, 0)

    async def execute(self, stmt):
        self.executed = stmt

        class Result:
            def scalars(self_inner):
                return [self.issue] if self.issue else []

        return Result()

    async def get(self, model, issue_id):
        return self.issue


async def test_create_issue_trims_description_and_defaults_status():
    db = FakeDB()

    issue = await create_issue(
        IssueCreate(description="  GPU is unavailable  "),
        current_user=_payload(),
        db=db,
    )

    assert db.committed is True
    assert db.refreshed is True
    assert db.added.description == "GPU is unavailable"
    assert db.added.status == "open"
    assert issue.user_id == "user-1"


async def test_list_all_issues_requires_admin():
    with pytest.raises(HTTPException) as exc_info:
        await list_all_issues(current_user=_payload("student"), db=FakeDB())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin only"


async def test_resolve_issue_marks_issue_resolved():
    issue = type("Issue", (), {"status": "open", "resolved_at": None})()
    db = FakeDB(issue=issue)

    result = await resolve_issue("issue-1", current_user=_payload("admin"), db=db)

    assert db.committed is True
    assert db.refreshed is True
    assert result.status == "resolved"
    assert result.resolved_at is not None
