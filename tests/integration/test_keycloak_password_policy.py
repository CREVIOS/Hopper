"""Password-policy behaviour against an ephemeral real Keycloak server.

The unit tests mock Keycloak, so they only prove we handle the payloads we
*think* it sends. This suite proves we handle what it actually sends. It is
what caught app.services.keycloak_admin reading the rejection reason from
`errorMessage` when Keycloak 25 reports password failures in
`error_description` — a mock-only test suite passes happily with that bug, and
the user still sees "Could not create the account. Try again later."

The realm here carries the production password policy verbatim from
scripts/keycloak-harden.sh. If that policy changes, these tests are the
tripwire for app.services.password_policy having drifted from it.
"""

import httpx
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from app.services.keycloak_admin import (
    KeycloakAdminClient,
    KeycloakPasswordPolicyError,
    KeycloakUserExistsError,
)
from app.services.password_policy import unmet_requirements

# Verbatim from scripts/keycloak-harden.sh — the whole point is to test the
# real thing, so this string must not be "simplified" for the test.
REALM_PASSWORD_POLICY = (
    "length(12) and digits(1) and lowerCase(1) and upperCase(1) "
    "and notUsername(undefined) and passwordHistory(3)"
)
REALM = "hopper-policy-test"
STRONG = "CorrectHorse9Battery"


def _docker_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(
        not _docker_available(), reason="Docker is required for Keycloak integration tests"
    ),
    pytest.mark.asyncio,
]


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
        wait_for_logs(container, "Running the server in development mode", timeout=180)
        yield f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8080)}"


@pytest.fixture(scope="module")
def admin_secret(keycloak_url) -> str:
    """Realm with the production policy + the gateway's service-account client."""
    with httpx.Client(base_url=keycloak_url, timeout=30) as client:
        token = client.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": "admin",
                "password": "admin",
            },
        )
        token.raise_for_status()
        headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

        realm = {
            "realm": REALM,
            "enabled": True,
            "passwordPolicy": REALM_PASSWORD_POLICY,
            "roles": {"realm": [{"name": "student"}, {"name": "professor"}, {"name": "admin"}]},
            "clients": [
                {
                    "clientId": "hopper-admin",
                    "enabled": True,
                    "publicClient": False,
                    "serviceAccountsEnabled": True,
                    "standardFlowEnabled": False,
                    "secret": "test-admin-secret",
                }
            ],
        }
        resp = client.post("/admin/realms", headers=headers, json=realm)
        assert resp.status_code in (201, 409), resp.text

        # The service account needs realm-management rights to create users.
        clients = client.get(
            f"/admin/realms/{REALM}/clients", headers=headers, params={"clientId": "hopper-admin"}
        ).json()
        admin_client_id = clients[0]["id"]
        sa_user = client.get(
            f"/admin/realms/{REALM}/clients/{admin_client_id}/service-account-user",
            headers=headers,
        ).json()
        rm = client.get(
            f"/admin/realms/{REALM}/clients", headers=headers, params={"clientId": "realm-management"}
        ).json()[0]
        rm_roles = client.get(
            f"/admin/realms/{REALM}/clients/{rm['id']}/roles", headers=headers
        ).json()
        wanted = [
            r for r in rm_roles if r["name"] in {"manage-users", "view-users", "view-clients"}
        ]
        client.post(
            f"/admin/realms/{REALM}/users/{sa_user['id']}/role-mappings/clients/{rm['id']}",
            headers=headers,
            json=wanted,
        ).raise_for_status()

        # Confirm the policy really took — a typo would silently make every
        # rejection assertion below vacuous.
        applied = client.get(f"/admin/realms/{REALM}", headers=headers).json()["passwordPolicy"]
        assert applied == REALM_PASSWORD_POLICY
    return "test-admin-secret"


@pytest.fixture
def kc_admin(keycloak_url, admin_secret, monkeypatch) -> KeycloakAdminClient:
    """The gateway's real admin client, pointed at the ephemeral Keycloak."""
    monkeypatch.setattr("app.services.keycloak_admin.settings.keycloak_url", keycloak_url)
    monkeypatch.setattr("app.services.keycloak_admin.settings.keycloak_realm", REALM)
    client = KeycloakAdminClient()
    client._base = keycloak_url.rstrip("/")
    client._realm = REALM
    client._client_id = "hopper-admin"
    client._client_secret = admin_secret
    return client


def _email(unique: str) -> str:
    return f"probe-{unique}@cs.du.ac.bd"


@pytest.mark.parametrize(
    ("case", "password", "expected_fragment"),
    [
        # The exact password from the bug report.
        ("all_digits", "111111111111111", "upper case"),
        ("no_uppercase", "lowercase12345", "upper case"),
        ("no_digits", "NoDigitsHereOk", "numerical digits"),
        ("too_short", "Ab1", "minimum length 12"),
    ],
)
async def test_realm_rejections_surface_as_typed_errors(kc_admin, case, password, expected_fragment):
    """Keycloak's real 400 must arrive as KeycloakPasswordPolicyError carrying
    its own reason — not as a generic error the router turns into a 502."""
    with pytest.raises(KeycloakPasswordPolicyError) as exc_info:
        await kc_admin.create_user(email=_email(case), name="Probe User", password=password)

    assert expected_fragment in str(exc_info.value)


async def test_compliant_password_is_accepted(kc_admin):
    user_id = await kc_admin.create_user(
        email=_email("compliant"), name="Probe User", password=STRONG
    )

    assert user_id


async def test_duplicate_email_is_typed_separately_from_a_policy_failure(kc_admin):
    email = _email("duplicate")
    await kc_admin.create_user(email=email, name="Probe User", password=STRONG)

    with pytest.raises(KeycloakUserExistsError):
        await kc_admin.create_user(email=email, name="Probe User", password=STRONG)


async def test_password_history_is_rejected_on_reset(kc_admin):
    """passwordHistory(3) is the rule password_policy cannot mirror — only
    Keycloak knows previous hashes, so this typed error is the only way the
    user ever learns they reused a password."""
    email = _email("history")
    user_id = await kc_admin.create_user(email=email, name="Probe User", password=STRONG)

    with pytest.raises(KeycloakPasswordPolicyError) as exc_info:
        await kc_admin.reset_password(user_id, STRONG)

    assert "last 3 passwords" in str(exc_info.value)


async def test_reset_to_a_fresh_compliant_password_succeeds(kc_admin):
    email = _email("fresh-reset")
    user_id = await kc_admin.create_user(email=email, name="Probe User", password=STRONG)

    await kc_admin.reset_password(user_id, "Different8Passphrase")  # must not raise


async def test_realm_does_not_enforce_not_username(kc_admin):
    """Documents why password_policy enforces not_username itself.

    Keycloak stores usernames lower-cased and its notUsername check is
    case-sensitive, so an email-as-password that also satisfies upperCase(1)
    slips through the realm entirely. If this test ever starts failing, the
    realm has begun enforcing it and the gateway rule becomes redundant.
    """
    email = "Probe-NotUsername1A@cs.du.ac.bd"

    user_id = await kc_admin.create_user(email=email, name="Probe User", password=email)

    assert user_id, "expected Keycloak to accept password == username"
    # ...which is exactly what the gateway mirror refuses to allow.
    assert "not_username" in {r.id for r in unmet_requirements(email, username=email.lower())}


async def test_mirror_and_realm_agree_on_a_sample_of_passwords(kc_admin):
    """Drift tripwire: for each password, the gateway mirror's verdict must
    match the realm's. A mismatch means password_policy.py and
    scripts/keycloak-harden.sh have diverged."""
    samples = [
        "111111111111111",
        "lowercase12345",
        "NoDigitsHereOk",
        "Ab1",
        "CorrectHorse9Battery",
        "Another7Passphrase",
    ]
    for index, password in enumerate(samples):
        email = _email(f"agree-{index}")
        mirror_rejects = bool(unmet_requirements(password, username=email))
        try:
            await kc_admin.create_user(email=email, name="Probe User", password=password)
            realm_rejects = False
        except KeycloakPasswordPolicyError:
            realm_rejects = True

        assert mirror_rejects == realm_rejects, (
            f"{password!r}: gateway mirror rejects={mirror_rejects}, "
            f"realm rejects={realm_rejects} — password_policy.py has drifted "
            f"from the realm policy in scripts/keycloak-harden.sh"
        )
