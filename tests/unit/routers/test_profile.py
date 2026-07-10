import pytest
from fastapi import HTTPException

from app.models.audit import AuditLog
from app.models.user import User
from app.routers import auth as auth_router
from app.schemas.user import AccountDeleteRequest, ProfileUpdateRequest, TokenPayload


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


# --- account deletion ---------------------------------------------------------


class _RecordingDB:
    """Records executed statements + added rows; execute() returns an empty result."""

    def __init__(self):
        self.executed = []
        self.added = []
        self.commits = 0

    async def execute(self, stmt):
        self.executed.append(stmt)

        class _R:
            def scalars(self_inner):
                class _S:
                    def all(self_s):
                        return []

                return _S()

        return _R()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


async def test_delete_account_rejects_email_mismatch(monkeypatch):
    called = {"kc": False}

    async def fake_delete_user(uid):
        called["kc"] = True

    monkeypatch.setattr(auth_router.keycloak_admin, "delete_user", fake_delete_user)

    with pytest.raises(HTTPException) as exc:
        await auth_router.delete_account(
            AccountDeleteRequest(confirm_email="WRONG@e.com"),
            current_user=_payload(),
            db=_RecordingDB(),
        )

    assert exc.value.status_code == 400
    assert called["kc"] is False  # no side effects on a mismatch


async def test_delete_account_happy_path(monkeypatch):
    deleted = {}

    async def fake_terminate_user_pods(db, user_id):
        deleted["terminated_for"] = user_id

    async def fake_delete_user(uid):
        deleted["kc_uid"] = uid

    monkeypatch.setattr(auth_router, "_terminate_user_pods", fake_terminate_user_pods)
    monkeypatch.setattr(auth_router.keycloak_admin, "delete_user", fake_delete_user)

    db = _RecordingDB()
    resp = await auth_router.delete_account(
        AccountDeleteRequest(confirm_email="u@e.com"), current_user=_payload(), db=db
    )

    assert resp.status_code == 200
    assert deleted["terminated_for"] == "user-1"
    assert deleted["kc_uid"] == "user-1"
    assert db.commits == 1
    audit = [a for a in db.added if isinstance(a, AuditLog)]
    assert len(audit) == 1 and audit[0].action == "account.delete"
    # session cookie is cleared on the response
    set_cookie = resp.headers.get("set-cookie", "")
    assert "session_token=" in set_cookie


async def test_delete_account_email_match_is_case_insensitive(monkeypatch):
    async def noop(*a, **k):
        pass

    monkeypatch.setattr(auth_router, "_terminate_user_pods", noop)
    monkeypatch.setattr(auth_router.keycloak_admin, "delete_user", noop)

    resp = await auth_router.delete_account(
        AccountDeleteRequest(confirm_email="  U@E.COM "), current_user=_payload(), db=_RecordingDB()
    )
    assert resp.status_code == 200


async def test_delete_account_502_when_keycloak_fails(monkeypatch):
    async def noop(*a, **k):
        pass

    async def boom(uid):
        raise RuntimeError("keycloak down")

    monkeypatch.setattr(auth_router, "_terminate_user_pods", noop)
    monkeypatch.setattr(auth_router.keycloak_admin, "delete_user", boom)

    with pytest.raises(HTTPException) as exc:
        await auth_router.delete_account(
            AccountDeleteRequest(confirm_email="u@e.com"), current_user=_payload(), db=_RecordingDB()
        )
    assert exc.value.status_code == 502
