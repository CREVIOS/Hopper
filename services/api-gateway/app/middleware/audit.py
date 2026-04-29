"""Audit logging middleware.

Logs all mutating requests (POST, PUT, DELETE) to the audit_logs table.
Runs as a background task after the response is sent — does not block the request.
"""

import asyncio
import logging
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.database import async_session
from app.middleware.auth import verify_token
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

# Map URL patterns to action names
_ACTION_MAP = [
    (re.compile(r"^/pods/?$"), "POST", "create_pod", "pod"),
    (re.compile(r"^/pods/([^/]+)$"), "DELETE", "terminate_pod", "pod"),
    (re.compile(r"^/credits/allocate$"), "POST", "allocate_credits", "credit"),
    (re.compile(r"^/auth/login$"), "GET", "login", "auth"),
    (re.compile(r"^/auth/logout$"), "POST", "logout", "auth"),
    (re.compile(r"^/ssh-keys/?$"), "POST", "add_ssh_key", "ssh_key"),
    (re.compile(r"^/ssh-keys/([^/]+)$"), "DELETE", "delete_ssh_key", "ssh_key"),
]


def _resolve_action(path: str, method: str) -> tuple[str, str, str | None]:
    """Resolve request path+method to (action, resource_type, resource_id)."""
    for pattern, m, action, rtype in _ACTION_MAP:
        if method == m:
            match = pattern.match(path)
            if match:
                rid = match.group(1) if match.lastindex else None
                return action, rtype, rid
    return f"{method.lower()}:{path}", "unknown", None


async def _extract_user_id(request: Request) -> str | None:
    """Extract user ID from a *verified* JWT. Returns None if unverified or missing.

    Audit attribution must be trustworthy — we fully validate the token rather
    than reading unverified claims. An unauth'd request gets a NULL user_id row.
    """
    token = request.cookies.get("session_token")
    if not token:
        return None
    payload = await verify_token(token)
    return payload.sub if payload else None


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Only audit mutating requests
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return response

        # Skip health checks
        if request.url.path in ("/healthz", "/readyz"):
            return response

        # Fire-and-forget audit log
        asyncio.create_task(self._log(request, response.status_code))
        return response

    async def _log(self, request: Request, status_code: int):
        try:
            user_id = await _extract_user_id(request)
            action, resource_type, resource_id = _resolve_action(request.url.path, request.method)
            ip = request.client.host if request.client else "unknown"

            async with async_session() as db:
                entry = AuditLog(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    ip_address=ip,
                    status_code=status_code,
                )
                db.add(entry)
                await db.commit()
        except Exception:
            logger.exception("Failed to write audit log")
