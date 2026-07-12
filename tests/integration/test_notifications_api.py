"""Notifications API + the credit-exhaustion grace lifecycle (FR-HC-18).

Run against real Postgres so the dedupe constraint, the pruning query, and the
grace state machine are exercised for real rather than against fakes.
"""

from datetime import datetime, timedelta
from pathlib import Path
import sys

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.dependencies import get_current_user, get_db
from app.main import create_app
from app.middleware import audit as audit_middleware
from app.models import Notification, PodSession, User
from app.schemas.user import TokenPayload
from app.services import credit_alerts
from app.services.credit_service import add_credits
from app.services.notification_service import create_notification


def _docker_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker is required for integration tests",
)


def _payload(sub: str, role: str = "student") -> TokenPayload:
    return TokenPayload(
        sub=sub,
        email=f"{sub}@cs.du.ac.bd",
        name="Test User",
        role=role,
        exp=4_102_444_800,
        email_verified=True,
    )


@pytest.fixture
def auth() -> dict:
    return {"user": _payload("stu-1")}


@pytest_asyncio.fixture
async def client(db_session, auth):
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    app = create_app()
    original_async_session = audit_middleware.async_session

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def override_get_current_user():
        return auth["user"]

    audit_middleware.async_session = session_factory
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    audit_middleware.async_session = original_async_session


@pytest_asyncio.fixture
async def people(db_session):
    db_session.add_all([
        User(id="admin-1", email="admin@cs.du.ac.bd", name="Admin", role="admin"),
        User(id="stu-1", email="stu1@cs.du.ac.bd", name="Student One", role="student"),
        User(id="stu-2", email="stu2@cs.du.ac.bd", name="Student Two", role="student"),
    ])
    await db_session.commit()


async def _notify(db, user_id="stu-1", **overrides):
    kwargs = dict(
        user_id=user_id,
        type="credit_warning",
        severity="warning",
        title="Low credits",
        body="About 10 minutes left.",
        publish=False,  # no NATS in the test harness
    )
    kwargs.update(overrides)
    return await create_notification(db, **kwargs)


# --- API ---------------------------------------------------------------------


async def test_listing_returns_only_your_own_notifications(client, people, db_session, auth):
    await _notify(db_session, user_id="stu-1", dedupe_key="a")
    await _notify(db_session, user_id="stu-2", dedupe_key="b")

    response = await client.get("/notifications")

    assert response.status_code == 200
    body = response.json()
    assert len(body["notifications"]) == 1  # stu-2's is not visible
    assert body["unread_count"] == 1


async def test_marking_read_clears_the_unread_count(client, people, db_session):
    notification = await _notify(db_session, dedupe_key="a")

    read = await client.post(f"/notifications/{notification.id}/read")
    assert read.status_code == 200
    assert read.json()["read_at"] is not None

    body = (await client.get("/notifications")).json()
    assert body["unread_count"] == 0


async def test_cannot_mark_someone_elses_notification_read(client, people, db_session, auth):
    notification = await _notify(db_session, user_id="stu-2", dedupe_key="b")

    auth["user"] = _payload("stu-1")  # a different student
    response = await client.post(f"/notifications/{notification.id}/read")

    assert response.status_code == 404  # not even acknowledged as existing


async def test_dedupe_key_prevents_a_duplicate_row(client, people, db_session):
    """The billing tick fires every minute; the same warning band must not repeat."""
    await _notify(db_session, dedupe_key="credit-warning:pod-1:10")
    await _notify(db_session, dedupe_key="credit-warning:pod-1:10")

    body = (await client.get("/notifications")).json()

    assert len(body["notifications"]) == 1


# --- grace lifecycle ---------------------------------------------------------


@pytest_asyncio.fixture
async def running_pod(db_session, people):
    session = PodSession(
        id="pod-1",
        user_id="stu-1",
        plan="small",
        image="hopper/vm-ubuntu:22.04",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-123",
        state="running",
        expires_at=datetime.utcnow() + timedelta(hours=8),  # the real TTL
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


async def test_starting_grace_does_not_disturb_the_session_ttl(db_session, running_pod):
    original_ttl = running_pod.expires_at

    await credit_alerts.start_credit_grace(db_session, session=running_pod)

    assert running_pod.credit_grace_until is not None
    assert running_pod.expires_at == original_ttl  # the reaper's field is untouched


async def test_topping_up_before_the_deadline_saves_the_vm(
    db_session, running_pod, monkeypatch
):
    published = []

    async def fake_publish(pod_id, user_id):
        published.append(pod_id)

    monkeypatch.setattr(credit_alerts, "publish_billing_exhausted", fake_publish)

    # Grace expired a minute ago, but the student has since been funded.
    running_pod.credit_grace_until = datetime.utcnow() - timedelta(minutes=1)
    await db_session.commit()
    await add_credits(db_session, "stu-1", 50.0, "admin_grant")

    resolved = await credit_alerts.process_expired_graces(db_session)

    assert resolved == 1
    assert published == []  # VM spared
    await db_session.refresh(running_pod)
    assert running_pod.credit_grace_until is None


async def test_still_broke_at_the_deadline_terminates_the_vm(
    db_session, running_pod, monkeypatch
):
    published = []

    async def fake_publish(pod_id, user_id):
        published.append(pod_id)

    monkeypatch.setattr(credit_alerts, "publish_billing_exhausted", fake_publish)

    running_pod.credit_grace_until = datetime.utcnow() - timedelta(minutes=1)
    await db_session.commit()
    # No credits added.

    resolved = await credit_alerts.process_expired_graces(db_session)

    assert resolved == 1
    assert published == ["vm-123"]  # orchestrator told to kill it

    notifications = (
        await db_session.scalars(
            select(Notification).where(Notification.user_id == "stu-1")
        )
    ).all()
    assert any(n.type == "vm_terminated" for n in notifications)


async def test_a_grace_that_has_not_expired_yet_is_left_alone(
    db_session, running_pod, monkeypatch
):
    published = []

    async def fake_publish(pod_id, user_id):
        published.append(pod_id)

    monkeypatch.setattr(credit_alerts, "publish_billing_exhausted", fake_publish)

    running_pod.credit_grace_until = datetime.utcnow() + timedelta(minutes=4)
    await db_session.commit()

    resolved = await credit_alerts.process_expired_graces(db_session)

    assert resolved == 0
    assert published == []
    await db_session.refresh(running_pod)
    assert running_pod.credit_grace_until is not None  # still counting down
