"""/auth/signup + /auth/reset-password — password errors over real HTTP.

Drives the routers through ASGI (no network, no DB, no Keycloak) to pin the
contract the browser actually sees: a weak password is a 400 naming the unmet
rules, NOT the blanket 502 "Could not create the account. Try again later."

These are the regression guard for the schema no longer carrying
`min_length=12` (see tests/unit/schemas/test_validation_boundaries.py) — they
fail if anything stops calling password_policy before Keycloak.

The full app's lifespan dials NATS and the orchestrator, so these mount just
the auth router with the DB dependency stubbed out.
"""
import httpx
import pytest
from fastapi import FastAPI

from app.core.limiter import limiter
from app.dependencies import get_db
from app.routers import auth
from app.services.keycloak_admin import KeycloakAdminError, KeycloakPasswordPolicyError

WEAK = "111111111111111"  # the password from the bug report
STRONG = "CorrectHorse9Battery"
EMAIL = "jane@cs.du.ac.bd"


class StubDb:
    """Enough AsyncSession surface for the paths under test."""

    def add(self, _obj):
        pass

    async def commit(self):
        pass

    async def execute(self, *_a, **_kw):
        raise AssertionError("no query should run on a rejected password")


@pytest.fixture(autouse=True)
def fresh_rate_limit_bucket():
    """Signup is capped at 5/minute per IP and slowapi's buckets are in-memory
    process-wide — without this, later tests in the module 429 instead of
    exercising the path under test."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def app():
    application = FastAPI()
    application.state.limiter = limiter  # slowapi reads the limiter off app.state
    application.include_router(auth.router, prefix="/auth")
    application.dependency_overrides[get_db] = lambda: StubDb()
    return application


@pytest.fixture
def client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def signup_body(password: str = WEAK, **over):
    return {"name": "Jane Doe", "email": EMAIL, "password": password, "role": "student", **over}


class TestSignupWeakPassword:
    async def test_all_digit_password_is_400_not_502(self, client):
        async with client as c:
            r = await c.post("/auth/signup", json=signup_body())
        assert r.status_code == 400
        assert "Try again later" not in r.json()["detail"]

    async def test_error_names_the_unmet_rules(self, client):
        async with client as c:
            r = await c.post("/auth/signup", json=signup_body())
        detail = r.json()["detail"]
        assert "lowercase letter" in detail
        assert "uppercase letter" in detail

    async def test_detail_is_a_plain_string_the_client_can_render(self, client):
        # The client does `json.detail || json.message` — a pydantic 422 hands
        # back a list here and renders as "[object Object]".
        async with client as c:
            r = await c.post("/auth/signup", json=signup_body(password="short"))
        assert r.status_code == 400
        assert isinstance(r.json()["detail"], str)
        assert "at least 12 characters" in r.json()["detail"]

    async def test_rejection_happens_before_keycloak_is_called(self, client, monkeypatch):
        async def boom(**_kw):
            raise AssertionError("create_user must not be called for a weak password")

        monkeypatch.setattr(auth.keycloak_admin, "create_user", boom)
        async with client as c:
            r = await c.post("/auth/signup", json=signup_body())
        assert r.status_code == 400

    async def test_password_equal_to_email_is_rejected(self, client):
        async with client as c:
            r = await c.post("/auth/signup", json=signup_body(password=EMAIL))
        assert r.status_code == 400
        assert "not be the same as your email" in r.json()["detail"]


class TestSignupKeycloakFallbacks:
    async def test_realm_rejection_of_an_allowed_password_surfaces_the_reason(
        self, client, monkeypatch
    ):
        # Mirror and realm drifted: we allowed it, Keycloak did not.
        async def rejects(**_kw):
            raise KeycloakPasswordPolicyError(
                "Invalid password: must contain at least 1 special characters."
            )

        monkeypatch.setattr(auth.keycloak_admin, "create_user", rejects)
        async with client as c:
            r = await c.post("/auth/signup", json=signup_body(password=STRONG))
        assert r.status_code == 400
        assert "special characters" in r.json()["detail"]

    async def test_keycloak_being_down_is_still_a_502(self, client, monkeypatch):
        # The generic message is correct HERE — this one really is our problem.
        async def down(**_kw):
            raise KeycloakAdminError("create user failed: connection refused")

        monkeypatch.setattr(auth.keycloak_admin, "create_user", down)
        async with client as c:
            r = await c.post("/auth/signup", json=signup_body(password=STRONG))
        assert r.status_code == 502
        assert "Try again later" in r.json()["detail"]


class TestResetPasswordWeakPassword:
    async def test_weak_password_is_400_naming_rules(self, client):
        async with client as c:
            r = await c.post(
                "/auth/reset-password",
                json={"email": EMAIL, "code": "123456", "password": WEAK},
            )
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "lowercase letter" in detail
        assert "Try again later" not in detail

    async def test_weak_password_does_not_burn_the_code(self, client):
        # StubDb.execute raises if reached — verify_code must not run, so the
        # emailed code survives for the user's next attempt.
        async with client as c:
            r = await c.post(
                "/auth/reset-password",
                json={"email": EMAIL, "code": "123456", "password": WEAK},
            )
        assert r.status_code == 400
