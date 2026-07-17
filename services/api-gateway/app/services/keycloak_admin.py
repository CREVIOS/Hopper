"""Keycloak admin REST client.

Used for actions that mutate Keycloak state from inside Hopper — role changes,
forced logouts, etc. Authenticates with a confidential service-account client
using the client_credentials grant, never a user token.

Required Keycloak setup (one time, in the master/hopper realm admin UI):
  1. Create client `hopper-admin` (or set HOPPER_KEYCLOAK_ADMIN_CLIENT_ID).
  2. Type: confidential, Service Accounts Enabled = true.
  3. In Service Account Roles, grant the *realm-management* roles:
     - manage-users   (so we can mutate role-mappings)
     - view-users     (so we can list)
     - view-clients   (so we can resolve client-role IDs if used later)
  4. Drop the client secret into the `hopper-keycloak-admin` K8s Secret as
     `client-secret` and reference it via HOPPER_KEYCLOAK_ADMIN_CLIENT_SECRET.

The client never trusts user input for `role` — callers must pre-validate
against the {admin, professor, student} allowlist.
"""
from __future__ import annotations

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class KeycloakAdminError(Exception):
    pass


class KeycloakUserExistsError(KeycloakAdminError):
    """A user with that email/username already exists (409)."""


class KeycloakPasswordPolicyError(KeycloakAdminError):
    """Keycloak rejected the password against the realm password policy (400).

    Distinct from the base class so callers can answer with a 400 naming the
    real reason instead of a blanket 502 "try again later" — a policy rejection
    is the user's to fix, not a transient upstream failure. The message is
    Keycloak's own (e.g. "must contain at least 1 upper case characters"), which
    is user-safe and stays correct even if the realm policy drifts from the
    mirror in app.services.password_policy.
    """


# Keycloak prefixes every password-policy rejection with this, in every realm
# locale we ship (English). Matching on it keeps unrelated 400s — a malformed
# user profile, say — from being mislabelled as a password problem.
#
# Observed on Keycloak 25 with the hopper realm policy, e.g.
#   {"error": "invalidPasswordMinUpperCaseCharsMessage",
#    "error_description": "Invalid password: must contain at least 1 upper case characters."}
# Password rejections carry `error_description`; other admin errors (a 409, for
# instance) use `errorMessage`. Read both — the field varies by error type and
# by Keycloak version.
_PASSWORD_ERROR_PREFIX = "invalid password"
# Keycloak's messages are short; cap anyway so a pathological upstream body
# can't be reflected wholesale into a user-facing error.
_MAX_REASON_LEN = 200


def _password_policy_reason(resp: httpx.Response) -> str | None:
    """Return Keycloak's password-policy reason from a 400, else None."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 — non-JSON body: not a policy rejection
        return None
    if not isinstance(body, dict):
        return None
    message = body.get("errorMessage") or body.get("error_description") or ""
    if not isinstance(message, str):
        return None
    if not message.strip().lower().startswith(_PASSWORD_ERROR_PREFIX):
        return None
    return message.strip()[:_MAX_REASON_LEN]


class KeycloakAdminClient:
    def __init__(self) -> None:
        self._base = settings.keycloak_url.rstrip("/")
        self._realm = settings.keycloak_realm
        self._client_id = settings.keycloak_admin_client_id
        self._client_secret = settings.keycloak_admin_client_secret
        self._token: str | None = None
        self._token_exp: float = 0.0

    async def _get_token(self) -> str:
        # Refresh ~30s before expiry so a slow Keycloak doesn't fail mid-call.
        if self._token and time.monotonic() < (self._token_exp - 30):
            return self._token
        if not self._client_secret:
            raise KeycloakAdminError(
                "HOPPER_KEYCLOAK_ADMIN_CLIENT_SECRET not configured"
            )
        token_url = f"{self._base}/realms/{self._realm}/protocol/openid-connect/token"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
        if resp.status_code != 200:
            raise KeycloakAdminError(f"admin token exchange failed: {resp.text}")
        body = resp.json()
        self._token = body["access_token"]
        self._token_exp = time.monotonic() + int(body.get("expires_in", 60))
        return self._token

    async def _headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}"}

    async def _admin_url(self, path: str) -> str:
        return f"{self._base}/admin/realms/{self._realm}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: object | None = None,
        params: dict | None = None,
        timeout: float = 10.0,
    ) -> httpx.Response:
        """Make an authenticated admin REST call, retrying once on a transient
        failure so a stale-but-not-locally-expired token doesn't surface as a
        hard error.

        This client is a process-lifetime singleton, so its cached bearer token
        can be rejected by Keycloak (401) while still looking un-expired here —
        e.g. after Keycloak restarts or rotates realm keys. It can also hit a
        transient 5xx while Keycloak is briefly busy (dev-mode restarts, GC).
        Both otherwise bubble up as an intermittent 5xx to the user that
        "works on retry". On the first 401 we drop the cached token and fetch a
        fresh one; on a 5xx we simply retry. Genuine 4xx (401 twice, 403, 404,
        409, ...) are returned to the caller unchanged.
        """
        url = await self._admin_url(path)
        resp: httpx.Response | None = None
        for attempt in (1, 2):
            headers = await self._headers()
            if json is not None:
                headers = {**headers, "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(
                    method, url, headers=headers, json=json, params=params
                )
            if attempt == 1 and (resp.status_code == 401 or resp.status_code >= 500):
                if resp.status_code == 401:
                    # Cached token was rejected server-side — force a refresh.
                    self._token = None
                    self._token_exp = 0.0
                logger.warning(
                    "keycloak admin %s %s -> %s; retrying once",
                    method, path, resp.status_code,
                )
                continue
            break
        assert resp is not None  # loop always runs at least once
        return resp

    async def list_realm_roles(self) -> list[dict]:
        resp = await self._request("GET", "/roles", timeout=5.0)
        if resp.status_code != 200:
            raise KeycloakAdminError(f"list roles failed: {resp.text}")
        return resp.json()

    async def get_user_realm_roles(self, user_id: str) -> list[dict]:
        resp = await self._request(
            "GET", f"/users/{user_id}/role-mappings/realm", timeout=5.0
        )
        if resp.status_code != 200:
            raise KeycloakAdminError(f"get user roles failed: {resp.text}")
        return resp.json()

    async def set_user_role(self, user_id: str, new_role: str) -> None:
        """Replace the user's app-level realm role with `new_role`.

        Removes any existing app-level role (admin/professor/student) and
        adds the new one. Built-in Keycloak roles are left untouched.
        """
        if new_role not in {"admin", "professor", "student"}:
            raise ValueError(f"invalid role: {new_role}")

        all_roles = await self.list_realm_roles()
        wanted = next((r for r in all_roles if r["name"] == new_role), None)
        if wanted is None:
            raise KeycloakAdminError(f"realm role {new_role!r} does not exist")

        existing = await self.get_user_realm_roles(user_id)
        app_role_set = {"admin", "professor", "student"}
        to_remove = [r for r in existing if r.get("name") in app_role_set and r.get("name") != new_role]

        if to_remove:
            resp = await self._request(
                "DELETE",
                f"/users/{user_id}/role-mappings/realm",
                json=[{"id": r["id"], "name": r["name"]} for r in to_remove],
            )
            if resp.status_code not in (204, 200):
                raise KeycloakAdminError(f"remove old roles failed: {resp.text}")

        already_has = any(r.get("name") == new_role for r in existing)
        if not already_has:
            resp = await self._request(
                "POST",
                f"/users/{user_id}/role-mappings/realm",
                json=[{"id": wanted["id"], "name": wanted["name"]}],
            )
            if resp.status_code not in (204, 200):
                raise KeycloakAdminError(f"add new role failed: {resp.text}")

    async def create_user(
        self,
        *,
        email: str,
        name: str,
        password: str,
        role: str = "student",
        email_verified: bool = True,
    ) -> str:
        """Create a Keycloak user with a password credential and app role.

        Returns the new user's id. Raises KeycloakUserExistsError on a 409 and
        KeycloakPasswordPolicyError when the realm rejects the password, so the
        caller can surface a clean 409 / 400 instead of a blanket 502. `name` is
        stored as firstName (Keycloak has no single "name" field).
        """
        # Keycloak's default user profile requires BOTH first and last name;
        # a missing lastName leaves the account "not fully set up" and blocks
        # the direct-grant login. Split the single display name into the two.
        parts = name.strip().split()
        first_name = parts[0] if parts else name.strip()
        last_name = " ".join(parts[1:]) if len(parts) > 1 else first_name
        payload = {
            "username": email,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": True,
            "emailVerified": email_verified,
            # No pending required actions (e.g. realm-default "Verify Email" /
            # "Update Password") — otherwise the immediate password-grant login
            # after signup fails with "Account is not fully set up".
            "requiredActions": [],
            "credentials": [
                {"type": "password", "value": password, "temporary": False}
            ],
        }
        resp = await self._request("POST", "/users", json=payload)
        if resp.status_code == 409:
            raise KeycloakUserExistsError("user exists")
        if resp.status_code == 400:
            reason = _password_policy_reason(resp)
            if reason:
                raise KeycloakPasswordPolicyError(reason)
        if resp.status_code not in (201, 204):
            raise KeycloakAdminError(f"create user failed: {resp.text}")

        # Keycloak returns the new user's id in the Location header.
        location = resp.headers.get("location") or resp.headers.get("Location") or ""
        user_id = location.rstrip("/").rsplit("/", 1)[-1]
        if not user_id:
            # Fallback: look it up by exact username.
            lookup = await self._request(
                "GET", "/users", params={"username": email, "exact": "true"}
            )
            rows = lookup.json() if lookup.status_code == 200 else []
            if not rows:
                raise KeycloakAdminError("created user but could not resolve id")
            user_id = rows[0]["id"]

        # Assign the app realm role (reuses the existing role-mapping logic).
        await self.set_user_role(user_id, role)
        return user_id

    async def get_user_by_email(self, email: str) -> dict | None:
        """Return the Keycloak user dict for an exact email, or None."""
        resp = await self._request(
            "GET", "/users", params={"email": email, "exact": "true"}
        )
        if resp.status_code != 200:
            raise KeycloakAdminError(f"user lookup failed: {resp.text}")
        rows = resp.json() or []
        return rows[0] if rows else None

    async def set_email_verified(self, user_id: str, verified: bool = True) -> None:
        """Flip a user's emailVerified flag."""
        resp = await self._request(
            "PUT", f"/users/{user_id}", json={"emailVerified": verified}
        )
        if resp.status_code not in (204, 200):
            raise KeycloakAdminError(f"set email verified failed: {resp.text}")

    async def reset_password(self, user_id: str, new_password: str) -> None:
        """Set a permanent (non-temporary) password for a user.

        Raises KeycloakPasswordPolicyError if the realm rejects the password —
        including passwordHistory(3) reuse, which only Keycloak can detect.
        """
        resp = await self._request(
            "PUT",
            f"/users/{user_id}/reset-password",
            json={"type": "password", "value": new_password, "temporary": False},
        )
        if resp.status_code == 400:
            reason = _password_policy_reason(resp)
            if reason:
                raise KeycloakPasswordPolicyError(reason)
        if resp.status_code not in (204, 200):
            raise KeycloakAdminError(f"reset password failed: {resp.text}")

    async def logout_user(self, user_id: str) -> None:
        """Force-revoke all of the user's Keycloak sessions and refresh tokens."""
        resp = await self._request("POST", f"/users/{user_id}/logout")
        if resp.status_code not in (204, 200):
            raise KeycloakAdminError(f"force logout failed: {resp.text}")


keycloak_admin = KeycloakAdminClient()
