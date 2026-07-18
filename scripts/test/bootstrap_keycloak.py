#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


KEYCLOAK = os.environ.get("KEYCLOAK_URL", "http://127.0.0.1:8080").rstrip("/")
REALM = os.environ.get("KEYCLOAK_REALM", "hopper")
ADMIN_USER = os.environ.get("KEYCLOAK_ADMIN", "admin")
ADMIN_PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
ADMIN_CLIENT_SECRET = os.environ.get("HOPPER_KEYCLOAK_ADMIN_CLIENT_SECRET", "hopper-admin-secret")
FRONTEND_URL = os.environ.get("HOPPER_FRONTEND_URL", "http://127.0.0.1:4173")
CALLBACK_URL = os.environ.get("HOPPER_CALLBACK_URL", f"{FRONTEND_URL}/api/auth/callback")


def request_json(
    method: str,
    path: str,
    *,
    data: dict | list | None = None,
    form: dict[str, str] | None = None,
    token: str | None = None,
) -> tuple[int, object | None]:
    url = f"{KEYCLOAK}{path}"
    headers = {}
    payload: bytes | None = None

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if form is not None:
        payload = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        payload = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            if not raw:
                return response.status, None
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        parsed = None
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw.decode()
        return exc.code, parsed


def ensure(status: int, expected: tuple[int, ...], context: str) -> None:
    if status not in expected:
        raise RuntimeError(f"{context} failed with status={status}")


def admin_token() -> str:
    status, body = request_json(
        "POST",
        "/realms/master/protocol/openid-connect/token",
        form={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD,
        },
    )
    ensure(status, (200,), "admin token exchange")
    assert isinstance(body, dict)
    return str(body["access_token"])


def get_client(token: str, client_id: str) -> dict | None:
    status, body = request_json(
        "GET",
        f"/admin/realms/{REALM}/clients?clientId={urllib.parse.quote(client_id)}",
        token=token,
    )
    ensure(status, (200,), f"lookup client {client_id}")
    assert isinstance(body, list)
    return body[0] if body else None


def create_or_update_realm(token: str) -> None:
    status, _ = request_json("GET", f"/admin/realms/{REALM}", token=token)
    realm_body = {
        "realm": REALM,
        "enabled": True,
        "loginWithEmailAllowed": True,
        "registrationAllowed": True,
        "resetPasswordAllowed": True,
        "duplicateEmailsAllowed": False,
        "editUsernameAllowed": False,
        "sslRequired": "none",
        "roles": {"realm": [{"name": "student"}, {"name": "professor"}, {"name": "admin"}]},
    }

    if status == 404:
        status, _ = request_json("POST", "/admin/realms", data=realm_body, token=token)
        ensure(status, (201, 409), "create realm")
    else:
        ensure(status, (200,), "get realm")

    status, _ = request_json("PUT", f"/admin/realms/{REALM}", data=realm_body, token=token)
    ensure(status, (204,), "update realm")


def create_or_update_clients(token: str) -> None:
    public_client = {
        "clientId": "hopper-api",
        "enabled": True,
        "publicClient": True,
        "directAccessGrantsEnabled": True,
        "standardFlowEnabled": True,
        "redirectUris": [CALLBACK_URL],
        "webOrigins": [FRONTEND_URL],
        "defaultClientScopes": ["profile", "email", "roles"],
        "attributes": {"pkce.code.challenge.method": "S256"},
    }
    admin_client = {
        "clientId": "hopper-admin",
        "enabled": True,
        "publicClient": False,
        "serviceAccountsEnabled": True,
        "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "secret": ADMIN_CLIENT_SECRET,
    }

    for body in (public_client, admin_client):
        client = get_client(token, body["clientId"])
        if client is None:
            status, _ = request_json(
                "POST", f"/admin/realms/{REALM}/clients", data=body, token=token
            )
            ensure(status, (201, 409), f"create client {body['clientId']}")
            client = get_client(token, body["clientId"])
            if client is None:
                raise RuntimeError(f"client {body['clientId']} still missing after create")
        body["id"] = client["id"]
        status, _ = request_json(
            "PUT", f"/admin/realms/{REALM}/clients/{client['id']}", data=body, token=token
        )
        ensure(status, (204,), f"update client {body['clientId']}")

    grant_realm_management_roles(token)


def grant_realm_management_roles(token: str) -> None:
    admin_client = get_client(token, "hopper-admin")
    if admin_client is None:
        raise RuntimeError("hopper-admin client is missing")

    status, service_account = request_json(
        "GET",
        f"/admin/realms/{REALM}/clients/{admin_client['id']}/service-account-user",
        token=token,
    )
    ensure(status, (200,), "get hopper-admin service account")
    assert isinstance(service_account, dict)

    status, clients = request_json(
        "GET",
        f"/admin/realms/{REALM}/clients?clientId=realm-management",
        token=token,
    )
    ensure(status, (200,), "lookup realm-management client")
    assert isinstance(clients, list) and clients
    realm_management = clients[0]

    status, roles = request_json(
        "GET",
        f"/admin/realms/{REALM}/clients/{realm_management['id']}/roles",
        token=token,
    )
    ensure(status, (200,), "list realm-management roles")
    assert isinstance(roles, list)
    wanted = [role for role in roles if role["name"] in {"manage-users", "view-users", "view-clients"}]
    status, _ = request_json(
        "POST",
        f"/admin/realms/{REALM}/users/{service_account['id']}/role-mappings/clients/{realm_management['id']}",
        data=wanted,
        token=token,
    )
    ensure(status, (204,), "grant service-account realm-management roles")


def get_user(token: str, email: str) -> dict | None:
    status, body = request_json(
        "GET",
        f"/admin/realms/{REALM}/users?email={urllib.parse.quote(email)}",
        token=token,
    )
    ensure(status, (200,), f"lookup user {email}")
    assert isinstance(body, list)
    for user in body:
        if user.get("email", "").lower() == email.lower():
            return user
    return None


def assign_roles(token: str, user_id: str, role_names: list[str]) -> None:
    status, roles = request_json("GET", f"/admin/realms/{REALM}/roles", token=token)
    ensure(status, (200,), "list realm roles")
    assert isinstance(roles, list)
    payload = [role for role in roles if role["name"] in set(role_names)]
    status, _ = request_json(
        "POST",
        f"/admin/realms/{REALM}/users/{user_id}/role-mappings/realm",
        data=payload,
        token=token,
    )
    ensure(status, (204,), f"assign roles to {user_id}")


def create_or_update_user(
    token: str,
    *,
    username: str,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
    roles: list[str],
) -> None:
    existing = get_user(token, email)
    body = {
        "username": username,
        "email": email,
        "enabled": True,
        "emailVerified": True,
        "firstName": first_name,
        "lastName": last_name,
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }

    if existing is None:
        status, _ = request_json("POST", f"/admin/realms/{REALM}/users", data=body, token=token)
        ensure(status, (201, 409), f"create user {email}")
        existing = get_user(token, email)
        if existing is None:
            raise RuntimeError(f"user {email} still missing after create")
    else:
        status, _ = request_json(
            "PUT", f"/admin/realms/{REALM}/users/{existing['id']}", data=body, token=token
        )
        ensure(status, (204,), f"update user {email}")

    assign_roles(token, existing["id"], roles)
    status, _ = request_json(
        "PUT",
        f"/admin/realms/{REALM}/users/{existing['id']}/reset-password",
        data={"type": "password", "value": password, "temporary": False},
        token=token,
    )
    ensure(status, (204,), f"reset password for {email}")


def seed_users(token: str) -> None:
    create_or_update_user(
        token,
        username="student-1",
        email=os.environ.get("E2E_STUDENT_EMAIL", "student-1@test.edu"),
        first_name="Student",
        last_name="One",
        password=os.environ.get("E2E_STUDENT_PASSWORD", "e2e-student"),
        roles=["student"],
    )
    create_or_update_user(
        token,
        username="professor-1",
        email=os.environ.get("E2E_PROFESSOR_EMAIL", "professor@test.edu"),
        first_name="Professor",
        last_name="One",
        password=os.environ.get("E2E_PROFESSOR_PASSWORD", "e2e-professor"),
        roles=["professor"],
    )
    create_or_update_user(
        token,
        username="admin-1",
        email=os.environ.get("E2E_ADMIN_EMAIL", "admin@test.edu"),
        first_name="Admin",
        last_name="One",
        password=os.environ.get("E2E_ADMIN_PASSWORD", "e2e-admin"),
        roles=["admin"],
    )


def main() -> int:
    try:
        token = admin_token()
        create_or_update_realm(token)
        create_or_update_clients(token)
        seed_users(token)
    except Exception as exc:
        print(f"bootstrap_keycloak failed: {exc}", file=sys.stderr)
        return 1

    print(f"Keycloak bootstrap ready for realm={REALM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
