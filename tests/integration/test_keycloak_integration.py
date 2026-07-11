"""OIDC integration tests against an ephemeral real Keycloak server."""

import asyncio
import time

import httpx
import pytest
from jose import jwt
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs


def _docker_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="Docker is required for Keycloak integration tests"
)


@pytest.fixture(scope="module")
def keycloak_url():
    container = (
        DockerContainer("quay.io/keycloak/keycloak:25.0")
        .with_env("KEYCLOAK_ADMIN", "admin")
        .with_env("KEYCLOAK_ADMIN_PASSWORD", "admin")
        .with_command("start-dev --http-port=8080")
        .with_exposed_ports(8080)
    )
    with container:
        wait_for_logs(container, "Running the server in development mode", timeout=120)
        yield f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8080)}"


@pytest.fixture(scope="module")
def configured_keycloak(keycloak_url):
    with httpx.Client(base_url=keycloak_url, timeout=15) as client:
        token_response = client.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": "admin",
                "password": "admin",
            },
        )
        token_response.raise_for_status()
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        realm = {
            "realm": "hopper-test",
            "enabled": True,
            "roles": {"realm": [{"name": "student"}, {"name": "admin"}]},
            "clients": [
                {
                    "clientId": "hopper-api",
                    "enabled": True,
                    "publicClient": True,
                    "directAccessGrantsEnabled": True,
                    "defaultClientScopes": ["profile", "email", "roles"],
                }
            ],
            "users": [
                {
                    "username": "student",
                    "email": "student@example.edu",
                    "firstName": "Test",
                    "lastName": "Student",
                    "enabled": True,
                    "emailVerified": True,
                    "realmRoles": ["student"],
                    "credentials": [
                        {"type": "password", "value": "test-password", "temporary": False}
                    ],
                }
            ],
        }
        response = client.post("/admin/realms", headers=headers, json=realm)
        assert response.status_code in (201, 409), response.text
    return keycloak_url


async def _issue_token(base_url: str, realm: str = "hopper-test") -> dict:
    async with httpx.AsyncClient(base_url=base_url, timeout=15) as client:
        response = await client.post(
            f"/realms/{realm}/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "hopper-api",
                "username": "student",
                "password": "test-password",
                "scope": "openid profile email roles",
            },
        )
        response.raise_for_status()
        return response.json()


@pytest.mark.asyncio
async def test_oidc_token_issuance(configured_keycloak):
    tokens = await _issue_token(configured_keycloak)
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["expires_in"] > 0


@pytest.mark.asyncio
async def test_role_and_identity_claims_are_present(configured_keycloak):
    tokens = await _issue_token(configured_keycloak)
    claims = jwt.get_unverified_claims(tokens["access_token"])
    assert claims["email"] == "student@example.edu"
    assert claims["email_verified"] is True
    assert "student" in claims["realm_access"]["roles"]
    assert claims["exp"] > int(time.time())


@pytest.mark.asyncio
async def test_refresh_token_issues_new_valid_access_token(configured_keycloak):
    tokens = await _issue_token(configured_keycloak)
    await asyncio.sleep(1)
    async with httpx.AsyncClient(base_url=configured_keycloak, timeout=15) as client:
        response = await client.post(
            "/realms/hopper-test/protocol/openid-connect/token",
            data={
                "grant_type": "refresh_token",
                "client_id": "hopper-api",
                "refresh_token": tokens["refresh_token"],
            },
        )
        response.raise_for_status()
        refreshed = response.json()
    assert refreshed["access_token"] != tokens["access_token"]
    assert jwt.get_unverified_claims(refreshed["access_token"])["exp"] >= int(time.time())


@pytest.mark.asyncio
async def test_jwks_validates_signature_issuer_and_expiry(configured_keycloak):
    tokens = await _issue_token(configured_keycloak)
    async with httpx.AsyncClient(base_url=configured_keycloak, timeout=15) as client:
        jwks = (await client.get("/realms/hopper-test/protocol/openid-connect/certs")).json()
    claims = jwt.decode(
        tokens["access_token"],
        jwks,
        algorithms=["RS256"],
        issuer=f"{configured_keycloak}/realms/hopper-test",
        options={"verify_aud": False},
    )
    assert claims["preferred_username"] == "student"


@pytest.mark.asyncio
async def test_token_from_wrong_issuer_is_rejected(configured_keycloak):
    tokens = await _issue_token(configured_keycloak)
    async with httpx.AsyncClient(base_url=configured_keycloak, timeout=15) as client:
        jwks = (await client.get("/realms/hopper-test/protocol/openid-connect/certs")).json()
    with pytest.raises(Exception):
        jwt.decode(
            tokens["access_token"],
            jwks,
            algorithms=["RS256"],
            issuer=f"{configured_keycloak}/realms/different-realm",
            options={"verify_aud": False},
        )
