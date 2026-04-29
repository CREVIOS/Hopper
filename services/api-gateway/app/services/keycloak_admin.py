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

    async def list_realm_roles(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(await self._admin_url("/roles"), headers=await self._headers())
        if resp.status_code != 200:
            raise KeycloakAdminError(f"list roles failed: {resp.text}")
        return resp.json()

    async def get_user_realm_roles(self, user_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                await self._admin_url(f"/users/{user_id}/role-mappings/realm"),
                headers=await self._headers(),
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

        async with httpx.AsyncClient(timeout=10.0) as client:
            if to_remove:
                resp = await client.request(
                    "DELETE",
                    await self._admin_url(f"/users/{user_id}/role-mappings/realm"),
                    headers={**(await self._headers()), "Content-Type": "application/json"},
                    json=[{"id": r["id"], "name": r["name"]} for r in to_remove],
                )
                if resp.status_code not in (204, 200):
                    raise KeycloakAdminError(f"remove old roles failed: {resp.text}")

            already_has = any(r.get("name") == new_role for r in existing)
            if not already_has:
                resp = await client.post(
                    await self._admin_url(f"/users/{user_id}/role-mappings/realm"),
                    headers={**(await self._headers()), "Content-Type": "application/json"},
                    json=[{"id": wanted["id"], "name": wanted["name"]}],
                )
                if resp.status_code not in (204, 200):
                    raise KeycloakAdminError(f"add new role failed: {resp.text}")

    async def logout_user(self, user_id: str) -> None:
        """Force-revoke all of the user's Keycloak sessions and refresh tokens."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                await self._admin_url(f"/users/{user_id}/logout"),
                headers=await self._headers(),
            )
        if resp.status_code not in (204, 200):
            raise KeycloakAdminError(f"force logout failed: {resp.text}")


keycloak_admin = KeycloakAdminClient()
