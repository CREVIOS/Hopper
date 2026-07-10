from pathlib import Path
import sys

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api-gateway"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.dependencies import get_current_user, get_db
from app.main import create_app
from app.middleware import audit as audit_middleware
from app.schemas.user import TokenPayload


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


@pytest_asyncio.fixture
async def current_user_payload() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        email="student@cs.du.ac.bd",
        name="Student One",
        role="student",
        exp=4_102_444_800,
        email_verified=True,
    )


@pytest_asyncio.fixture
async def client(db_session, current_user_payload):
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    app = create_app()
    original_async_session = audit_middleware.async_session

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def override_get_current_user():
        return current_user_payload

    audit_middleware.async_session = session_factory
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    audit_middleware.async_session = original_async_session


@pytest.mark.asyncio
async def test_save_vscode_settings_returns_saved_status(client):
    response = await client.put(
        "/settings/vscode",
        json={"editor.fontSize": 16, "files.autoSave": "afterDelay"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "saved"}
