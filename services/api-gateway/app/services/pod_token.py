"""Per-pod bearer token shared by the in-VM agents.

A single stable token, HMAC(pod_id) under the platform signing secret, is handed
to the in-VM agents (idle reporter + sandbox provisioner) so they can call their
own pod's endpoints without holding a user session. One-way, so the VM never
learns the secret. Both agents authenticate the same way, so one
``HOPPER_POD_TOKEN`` in the pod env serves both.

Kept in its own module (no NATS/DB/model imports) so it can be reused — and unit
tested — without pulling in the heavier agent services.
"""
from __future__ import annotations

import hashlib
import hmac

from app.config import settings


def make_pod_token(pod_id: str) -> str:
    return hmac.new(
        settings.code_url_signing_secret.encode(),
        f"pod-heartbeat:{pod_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_pod_token(pod_id: str, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(make_pod_token(pod_id), token)
