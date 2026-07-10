import pytest
from fastapi import HTTPException

from app.models.user import User
from app.routers import auth as auth_router
from app.schemas.user import ProfileUpdateRequest, TokenPayload


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDB:
    def __init__(self, user):
        self._user = user
        self.commits = 0

    async def execute(self, stmt):
        return _FakeResult(self._user)

    async def commit(self):
        self.commits += 1


def _payload():
    return TokenPayload(sub="user-1", email="u@e.com", name="U", role="student", exp=123)


async def test_me_returns_university_id_from_db():
    user = User(id="user-1", email="u@e.com", name="U", role="student", university_id="STU-42")

    result = await auth_router.me(current_user=_payload(), db=_FakeDB(user))

    assert result.university_id == "STU-42"


async def test_update_profile_sets_university_id():
    user = User(id="user-1", email="u@e.com", name="U", role="student", university_id=None)
    db = _FakeDB(user)

    result = await auth_router.update_profile(
        ProfileUpdateRequest(university_id="NEW-7"), current_user=_payload(), db=db
    )

    assert user.university_id == "NEW-7"
    assert result.university_id == "NEW-7"
    assert db.commits == 1


async def test_update_profile_404_when_user_missing():
    db = _FakeDB(None)

    with pytest.raises(HTTPException) as exc:
        await auth_router.update_profile(
            ProfileUpdateRequest(university_id="x"), current_user=_payload(), db=db
        )

    assert exc.value.status_code == 404
