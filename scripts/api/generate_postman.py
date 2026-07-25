#!/usr/bin/env python3
"""Generate the Hopper Postman collection from the gateway's OpenAPI spec.

The gateway is FastAPI, so /openapi.json is the single source of truth for
every route, parameter and request schema. Hand-maintaining a collection
alongside it guarantees drift, so this script derives the collection instead.

Usage:
    # from the deployed gateway (default)
    python scripts/api/generate_postman.py

    # from a local gateway or a saved spec
    python scripts/api/generate_postman.py --spec http://127.0.0.1:8000/openapi.json
    python scripts/api/generate_postman.py --spec /tmp/openapi.json

Outputs (overwritten in place):
    docs/api/hopper.postman_collection.json
    docs/api/hopper.postman_environment.production.json
    docs/api/hopper.postman_environment.local.json

What it adds on top of a plain OpenAPI import:
  - collection-level API-key auth that degrades to cookie auth when unset
  - realistic example bodies using this deployment's real plans and images
  - {{podId}}-style collection variables instead of bare :path_id placeholders
  - chained scripts so create-a-VM feeds the follow-up requests automatically
  - credentials kept in variables so nothing secret is committed
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "docs" / "api"

DEFAULT_SPEC = "https://hopper.farefin.com/api/openapi.json"
PROD_BASE_URL = "https://hopper.farefin.com/api"
LOCAL_BASE_URL = "http://127.0.0.1:8000"

# Deterministic ids: regenerating an unchanged spec must produce an identical
# file, otherwise every run shows up as noise in git.
NAMESPACE = uuid.UUID("6f6b1f9a-1f7a-5a1e-9d4c-2a1b3c4d5e6f")


def _uuid(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))


# --------------------------------------------------------------------------
# Ordering and prose
# --------------------------------------------------------------------------

# Auth first because every other folder depends on it; health last because
# it is the least interesting. Anything not listed sorts after these.
TAG_ORDER = [
    "auth",
    "pods",
    "credits",
    "usage",
    "files",
    "ssh-keys",
    "settings",
    "notifications",
    "issues",
    "admin",
    "health",
]

TAG_TITLES = {
    "auth": "1. Auth & API keys",
    "pods": "2. VMs (pods)",
    "credits": "3. Credits",
    "usage": "4. Usage & metrics",
    "files": "5. Files",
    "ssh-keys": "6. SSH keys",
    "settings": "7. Settings",
    "notifications": "8. Notifications",
    "issues": "9. Issues",
    "admin": "10. Admin",
    "health": "11. Health probes",
}

TAG_DESCRIPTIONS = {
    "auth": (
        "Start here. `Login` seeds Postman's cookie jar with the `session_token` "
        "cookie and everything else in this collection will then work.\n\n"
        "For scripted access, run `Create API key` once while logged in, paste the "
        "returned `key` into the `apiKey` environment variable, and requests will "
        "authenticate with the `X-API-Key` header instead of the cookie. Note that "
        "a `read_only` key is rejected on anything other than GET/HEAD/OPTIONS."
    ),
    "pods": (
        "A pod is a VM. `Create VM` returns immediately and the VM boots "
        "asynchronously, so poll `Get VM` until `state` is `running`.\n\n"
        "If the cluster is full the request is queued rather than rejected — check "
        "`Queue position` and `Availability`. `Create VM` saves the new id into the "
        "`podId` variable, so the rest of this folder targets it without editing."
    ),
    "credits": (
        "Credit balances and transfers. Admins allocate to teachers, teachers "
        "allocate to their students. VMs bill per hour against the owner's balance "
        "while they are in the `running` state."
    ),
    "usage": "Per-VM resource samples and the aggregated series behind the dashboard charts.",
    "files": "Browse, upload and download files inside a running VM's workspace.",
    "ssh-keys": "Public keys injected into VMs at boot so you can SSH in directly.",
    "settings": "Per-user preferences, currently the VS Code editor settings blob.",
    "notifications": (
        "In-app notifications. `Stream` is Server-Sent Events — Postman shows it as "
        "a long-running response rather than a normal JSON body."
    ),
    "issues": "Student-reported problems and the admin queue that resolves them.",
    "admin": (
        "Admin-only. A non-admin session gets 403 on every request in this folder.\n\n"
        "Covers user and role management, teacher approvals, the plan and image "
        "catalogues, cluster nodes, audit logs and platform stats."
    ),
    "health": (
        "Unauthenticated probes. `/healthz` is liveness (shallow by design — "
        "restarting the pod cannot fix a down database). `/readyz` is readiness and "
        "returns 503 with a per-dependency breakdown when the gateway cannot serve "
        "real traffic."
    ),
}

# Endpoints that only make sense in a browser. Kept for completeness, but
# separated so they do not clutter the folder you actually work in.
BROWSER_ONLY = {
    ("get", "/auth/login"),
    ("get", "/auth/callback"),
}


# --------------------------------------------------------------------------
# Path parameters -> collection variables
# --------------------------------------------------------------------------

# `name` and `template` are ambiguous on their own, so they are disambiguated
# by the route they appear in.
PARAM_VARS = {
    ("/admin/plans/{name}", "name"): "planName",
    ("/admin/images/{template}", "template"): "imageTemplate",
}

PARAM_VARS_BY_NAME = {
    "pod_id": "podId",
    "user_id": "userId",
    "key_id": "keyId",
    "entry_id": "queueEntryId",
    "notification_id": "notificationId",
    "issue_id": "issueId",
    "path": "vscodePath",
}


def var_for_param(path: str, param: str) -> str:
    if (path, param) in PARAM_VARS:
        return PARAM_VARS[(path, param)]
    if param in PARAM_VARS_BY_NAME:
        return PARAM_VARS_BY_NAME[param]
    head, *rest = param.split("_")
    return head + "".join(w.capitalize() for w in rest)


# --------------------------------------------------------------------------
# Example request bodies
# --------------------------------------------------------------------------

# Values match what this deployment actually accepts: plans are seeded as
# small/medium/large (migration 017) and images as ubuntu/python-ml/cpp/java
# (migration 018). Credentials stay as variables so none are committed.
BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "LoginRequest": {"email": "{{userEmail}}", "password": "{{userPassword}}"},
    "SignupRequest": {
        "email": "{{userEmail}}",
        "password": "{{userPassword}}",
        "name": "Ada Lovelace",
        "role": "student",
    },
    "VerifyEmailRequest": {"email": "{{userEmail}}", "code": "123456"},
    "ResendCodeRequest": {"email": "{{userEmail}}", "purpose": "verify_email"},
    "ForgotPasswordRequest": {"email": "{{userEmail}}"},
    "ResetPasswordRequest": {
        "email": "{{userEmail}}",
        "code": "123456",
        "password": "{{userPassword}}",
    },
    "CreateApiKeyRequest": {"name": "postman", "scope": "read_only"},
    "CreatePodRequest": {
        "plan": "small",
        "template": "ubuntu",
        "image": None,
        "network_group": None,
    },
    "AllocateRequest": {
        "user_id": "{{userId}}",
        "amount": 100,
        "description": "allocation",
    },
    "ChangeRoleRequest": {"role": "teacher"},
    "PlanCreateRequest": {
        "name": "xlarge",
        "display_name": "Extra Large",
        "cpu": "8",
        "memory": "16Gi",
        "disk": "40Gi",
        "credits_per_hour": 8.0,
        "workspace_gb": 200,
    },
    "PlanUpdateRequest": {"display_name": "Extra Large", "credits_per_hour": 8.0},
    "ImageCreateRequest": {
        "template": "rust",
        "display_name": "Rust",
        "image": "ghcr.io/crevios/hopper-vm-rust:latest",
        "description": "Rust toolchain preinstalled",
        "is_default": False,
    },
    "ImageUpdateRequest": {"display_name": "Rust", "is_default": False},
    "AddKeyRequest": {
        "name": "laptop",
        "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyReplaceMe you@example.com",
    },
    "IssueCreate": {
        "pod_id": "{{podId}}",
        "description": "The VM is stuck in the provisioning state.",
    },
}

# The settings blob is a free-form object in the schema; show a usable shape.
INLINE_BODY_EXAMPLES = {
    "/settings/vscode": {"theme": "vs-dark", "fontSize": 14, "tabSize": 4},
}


def example_from_schema(schema: dict, spec: dict, depth: int = 0) -> Any:
    """Fallback example builder for schemas without a curated override."""
    schema = resolve_ref(schema, spec)
    if depth > 4:
        return None
    if "default" in schema:
        return schema["default"]
    if "example" in schema:
        return schema["example"]
    if "anyOf" in schema:
        # Prefer the non-null branch so the example shows the useful shape.
        for branch in schema["anyOf"]:
            if resolve_ref(branch, spec).get("type") != "null":
                return example_from_schema(branch, spec, depth + 1)
        return None
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        return {
            k: example_from_schema(v, spec, depth + 1)
            for k, v in schema.get("properties", {}).items()
        }
    if t == "array":
        return [example_from_schema(schema.get("items", {}), spec, depth + 1)]
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return False
    if t == "null":
        return None
    return ""


def resolve_ref(schema: dict, spec: dict) -> dict:
    seen = 0
    while isinstance(schema, dict) and "$ref" in schema and seen < 10:
        ref = schema["$ref"]
        node: Any = spec
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        schema = node
        seen += 1
    return schema if isinstance(schema, dict) else {}


# --------------------------------------------------------------------------
# Per-request scripts
# --------------------------------------------------------------------------

# Chaining: a handful of requests produce ids that later requests need. Saving
# them automatically is the difference between a collection you can run and one
# where you copy ids by hand.
REQUEST_SCRIPTS: dict[tuple[str, str], list[str]] = {
    ("post", "/auth/login"): [
        "pm.test('Login succeeded', () => pm.response.to.have.status(200));",
        "if (pm.response.code === 200) {",
        "  const me = pm.response.json();",
        "  pm.collectionVariables.set('userId', me.id);",
        "  console.log('Signed in as', me.email, '- role:', me.role);",
        "  console.log('The session_token cookie is now in the jar; other requests will use it.');",
        "}",
    ],
    ("post", "/auth/api-keys"): [
        "pm.test('API key created', () => pm.response.to.have.status(201));",
        "if (pm.response.code === 201) {",
        "  const body = pm.response.json();",
        "  // The plaintext key is returned exactly once. Store it now.",
        "  pm.collectionVariables.set('apiKey', body.key);",
        "  console.log('Saved apiKey. Copy it somewhere safe - it is not retrievable again.');",
        "}",
    ],
    ("post", "/pods/"): [
        "pm.test('VM accepted', () => pm.expect(pm.response.code).to.be.oneOf([200, 201, 202]));",
        "if (pm.response.code < 300) {",
        "  const body = pm.response.json();",
        "  if (body.id) {",
        "    pm.collectionVariables.set('podId', body.id);",
        "    console.log('Saved podId =', body.id, '- state:', body.state);",
        "  }",
        "  if (body.queue_position !== undefined && body.queue_position !== null) {",
        "    console.log('Cluster is full; queued at position', body.queue_position);",
        "  }",
        "}",
    ],
    ("get", "/pods/"): [
        "pm.test('Listed VMs', () => pm.response.to.have.status(200));",
        "const pods = pm.response.code === 200 ? pm.response.json() : [];",
        "if (Array.isArray(pods) && pods.length && !pm.collectionVariables.get('podId')) {",
        "  pm.collectionVariables.set('podId', pods[0].id);",
        "  console.log('Seeded podId from the first VM:', pods[0].id);",
        "}",
    ],
    ("post", "/ssh-keys/"): [
        "if (pm.response.code < 300) {",
        "  const b = pm.response.json();",
        "  if (b.id) pm.collectionVariables.set('keyId', b.id);",
        "}",
    ],
    ("post", "/issues/"): [
        "if (pm.response.code < 300) {",
        "  const b = pm.response.json();",
        "  if (b.id) pm.collectionVariables.set('issueId', b.id);",
        "}",
    ],
    ("get", "/readyz"): [
        "pm.test('Gateway is ready', () => pm.response.to.have.status(200));",
        "const checks = pm.response.json().checks || {};",
        "Object.keys(checks).forEach((dep) => {",
        "  pm.test('dependency up: ' + dep, () => pm.expect(checks[dep]).to.be.true);",
        "});",
    ],
}

# Extra prose for requests whose behaviour is not obvious from the summary.
REQUEST_NOTES: dict[tuple[str, str], str] = {
    ("post", "/auth/login"): (
        "Direct email + password grant. Responds with the user object and sets the "
        "httpOnly `session_token` cookie, which Postman stores automatically — you "
        "do not need to copy a token anywhere.\n\n"
        "Set `userEmail` and `userPassword` in your environment first. Passwords "
        "must be at least 12 characters to satisfy the Keycloak realm policy.\n\n"
        "Rate limited to 10/min, and 3 *failed* attempts per (IP, email) trips a "
        "temporary 429 block."
    ),
    ("get", "/auth/login"): (
        "Browser-only. Redirects to Keycloak for the SSO flow. Use `POST /auth/login` "
        "from Postman instead."
    ),
    ("get", "/auth/callback"): (
        "Browser-only. Keycloak redirects here after SSO; not callable directly."
    ),
    ("post", "/auth/api-keys"): (
        "Returns the plaintext key **once** — only its SHA-256 hash is stored, so a "
        "lost key must be revoked and recreated. The test script saves it into the "
        "`apiKey` variable for you.\n\n"
        "Requires a real cookie session: you cannot mint a new key using an existing "
        "API key. `read_only` scope is restricted to GET/HEAD/OPTIONS; use "
        "`full_access` if you need to create or delete things."
    ),
    ("post", "/pods/"): (
        "Creates a VM. Returns immediately — the VM boots asynchronously, so poll "
        "`Get VM` until `state` is `running`.\n\n"
        "If the cluster has no room the request is admitted to a queue instead of "
        "failing; the response carries a queue position. `plan` is one of "
        "`small`, `medium`, `large`. `template` is one of `ubuntu`, `python-ml`, "
        "`cpp`, `java`. Leave `image` null to use the template's default image."
    ),
    ("get", "/pods/availability"): (
        "Free capacity across the cluster. A VM reserves a quarter of its plan's CPU "
        "and bursts to the full limit when cores are idle, so the reserved figure is "
        "what admission actually checks against."
    ),
    ("get", "/notifications/stream"): (
        "Server-Sent Events. This response never completes — Postman will show it "
        "streaming until you cancel it. That is expected, not a hang."
    ),
    ("post", "/files/{pod_id}/upload"): (
        "multipart/form-data. Pick a local file for the `file` form field in Postman's "
        "Body tab before sending; the exported collection cannot embed file contents."
    ),
    ("post", "/credits/allocate"): (
        "Admins allocate to teachers; teachers allocate to their own students. "
        "Allocating to a user outside your scope returns 403."
    ),
}


# --------------------------------------------------------------------------
# Collection assembly
# --------------------------------------------------------------------------


def build_url(path: str, params: list[dict], spec: dict) -> dict:
    """Turn an OpenAPI path into a Postman URL with {{var}} placeholders."""
    postman_path = path
    for p in params:
        if p.get("in") == "path":
            postman_path = postman_path.replace(
                "{" + p["name"] + "}", "{{" + var_for_param(path, p["name"]) + "}}"
            )

    # Keep the trailing slash exactly as FastAPI registered it. Dropping it is
    # not cosmetic: the ingress serves the gateway under /api, but FastAPI's
    # redirect_slashes builds the 307 Location from its own root, so
    # GET /api/pods redirects to /pods/ — the frontend SPA, not the API.
    segments = [s for s in postman_path.split("/") if s]
    if postman_path.endswith("/") and segments:
        segments.append("")

    query = []
    for p in params:
        if p.get("in") != "query":
            continue
        schema = resolve_ref(p.get("schema", {}), spec)
        default = schema.get("default")
        value = "" if default is None else str(default).lower() if isinstance(default, bool) else str(default)
        query.append(
            {
                "key": p["name"],
                "value": value,
                "description": p.get("description", "") or schema.get("title", ""),
                # Optional params start disabled so a fresh send is the simple case.
                "disabled": not p.get("required", False),
            }
        )

    raw = "{{baseUrl}}" + ("/" + "/".join(segments) if segments else "")
    if query:
        enabled = [q for q in query if not q["disabled"]]
        if enabled:
            raw += "?" + "&".join(f"{q['key']}={q['value']}" for q in enabled)

    url: dict[str, Any] = {"raw": raw, "host": ["{{baseUrl}}"], "path": segments}
    if query:
        url["query"] = query
    return url


def build_body(op: dict, path: str, spec: dict) -> tuple[dict | None, list[dict]]:
    """Return (postman body, extra headers) for an operation."""
    rb = op.get("requestBody")
    if not rb:
        return None, []
    content = rb.get("content", {})

    if "multipart/form-data" in content:
        schema = resolve_ref(content["multipart/form-data"].get("schema", {}), spec)
        formdata = []
        for field, fschema in schema.get("properties", {}).items():
            fschema = resolve_ref(fschema, spec)
            is_file = fschema.get("format") == "binary" or field == "file"
            entry = {"key": field, "type": "file" if is_file else "text"}
            if is_file:
                entry["src"] = []
                entry["description"] = "Choose a local file in Postman's Body tab."
            else:
                entry["value"] = str(example_from_schema(fschema, spec) or "")
            formdata.append(entry)
        # Content-Type is set by Postman with the correct multipart boundary.
        return {"mode": "formdata", "formdata": formdata}, []

    if "application/json" in content:
        schema = content["application/json"].get("schema", {})
        title = resolve_ref(schema, spec).get("title", "")
        if path in INLINE_BODY_EXAMPLES:
            example = INLINE_BODY_EXAMPLES[path]
        elif title in BODY_EXAMPLES:
            example = BODY_EXAMPLES[title]
        else:
            example = example_from_schema(schema, spec)
        body = {
            "mode": "raw",
            "raw": json.dumps(example, indent=2),
            "options": {"raw": {"language": "json"}},
        }
        return body, [{"key": "Content-Type", "value": "application/json"}]

    return None, []


# FastAPI derives each summary from its handler's function name, which yields
# labels like "Me", "Callback", "List Api Keys" and five identical entries
# called "Vscode Proxy". These are what you actually read in Postman's sidebar,
# so name them the way someone using the API would describe them.
NAME_OVERRIDES: dict[tuple[str, str], str] = {
    ("get", "/auth/login"): "Login via SSO (browser)",
    ("post", "/auth/login"): "Login",
    ("post", "/auth/signup"): "Sign up",
    ("post", "/auth/verify-email"): "Verify email",
    ("post", "/auth/resend-code"): "Resend code",
    ("post", "/auth/forgot-password"): "Forgot password",
    ("post", "/auth/reset-password"): "Reset password",
    ("get", "/auth/callback"): "SSO callback (browser)",
    ("post", "/auth/refresh"): "Refresh session",
    ("get", "/auth/me"): "Current user",
    ("post", "/auth/logout"): "Log out",
    ("get", "/auth/api-keys"): "List API keys",
    ("post", "/auth/api-keys"): "Create API key",
    ("delete", "/auth/api-keys/{key_id}"): "Revoke API key",

    ("get", "/pods/plans"): "List plans",
    ("get", "/pods/templates"): "List base images",
    ("get", "/pods/"): "List VMs",
    ("post", "/pods/"): "Create VM",
    ("get", "/pods/availability"): "Cluster availability",
    ("get", "/pods/queue"): "Queue position",
    ("delete", "/pods/queue/{entry_id}"): "Leave the queue",
    ("get", "/pods/{pod_id}"): "Get VM",
    ("delete", "/pods/{pod_id}"): "Terminate VM",
    ("get", "/pods/{pod_id}/metrics"): "Stream VM metrics",
    ("get", "/pods/{pod_id}/vscode/{path}"): "VS Code proxy — GET",
    ("post", "/pods/{pod_id}/vscode/{path}"): "VS Code proxy — POST",
    ("put", "/pods/{pod_id}/vscode/{path}"): "VS Code proxy — PUT",
    ("delete", "/pods/{pod_id}/vscode/{path}"): "VS Code proxy — DELETE",
    ("patch", "/pods/{pod_id}/vscode/{path}"): "VS Code proxy — PATCH",

    ("get", "/credits/balance"): "My balance",
    ("get", "/credits/history"): "Transaction history",
    ("get", "/credits/teachers"): "List teachers",
    ("get", "/credits/students"): "List students",
    ("post", "/credits/allocate"): "Allocate credits",

    ("get", "/usage/{pod_id}"): "Usage for a VM",
    ("get", "/usage/summary/me/series"): "My usage series",
    ("get", "/usage/summary/me"): "My usage summary",

    ("get", "/files/{pod_id}/list"): "List directory",
    ("post", "/files/{pod_id}/upload"): "Upload file",
    ("get", "/files/{pod_id}/download"): "Download file",

    ("get", "/ssh-keys/"): "List SSH keys",
    ("post", "/ssh-keys/"): "Add SSH key",
    ("delete", "/ssh-keys/{key_id}"): "Delete SSH key",

    ("get", "/settings/vscode"): "Read VS Code settings",
    ("put", "/settings/vscode"): "Save VS Code settings",

    ("get", "/notifications/"): "List notifications",
    ("post", "/notifications/read-all"): "Mark all read",
    ("post", "/notifications/{notification_id}/read"): "Mark one read",
    ("get", "/notifications/stream"): "Stream notifications (SSE)",

    ("post", "/issues/"): "Report issue",
    ("get", "/issues/me"): "My issues",
    ("get", "/issues/admin"): "All issues",
    ("post", "/issues/admin/{issue_id}/resolve"): "Resolve issue",

    ("get", "/admin/users"): "List users",
    ("get", "/admin/teacher-requests"): "Pending teacher requests",
    ("post", "/admin/teacher-requests/{user_id}/approve"): "Approve teacher",
    ("post", "/admin/teacher-requests/{user_id}/reject"): "Reject teacher",
    ("get", "/admin/courses"): "List courses",
    ("get", "/admin/nodes"): "List cluster nodes",
    ("get", "/admin/stats"): "Platform stats",
    ("get", "/admin/active-vms"): "Active VMs",
    ("patch", "/admin/users/{user_id}/role"): "Change user role",
    ("get", "/admin/audit-logs"): "Audit logs",
    ("get", "/admin/plans"): "List plans (catalogue)",
    ("post", "/admin/plans"): "Create plan",
    ("put", "/admin/plans/{name}"): "Update plan",
    ("delete", "/admin/plans/{name}"): "Delete plan",
    ("get", "/admin/images"): "List base images (catalogue)",
    ("post", "/admin/images"): "Create base image",
    ("put", "/admin/images/{template}"): "Update base image",
    ("delete", "/admin/images/{template}"): "Delete base image",

    ("get", "/healthz"): "Liveness",
    ("get", "/readyz"): "Readiness",
}


def humanise(op: dict, method: str, path: str) -> str:
    override = NAME_OVERRIDES.get((method, path))
    if override:
        return override
    # A new route lands here until it is named above. Title-casing FastAPI's
    # summary is a serviceable placeholder, not a good label.
    summary = (op.get("summary") or "").strip()
    if summary and summary.lower() not in {"", "none"}:
        return summary
    return f"{method.upper()} {path}"


def build_request_item(method: str, path: str, op: dict, spec: dict) -> dict:
    params = op.get("parameters", [])
    body, headers = build_body(op, path, spec)

    description_parts = []
    note = REQUEST_NOTES.get((method, path))
    if note:
        description_parts.append(note)
    doc = (op.get("description") or "").strip()
    if doc and doc != note:
        description_parts.append(doc)
    path_vars = [p["name"] for p in params if p.get("in") == "path"]
    if path_vars:
        rendered = ", ".join(
            f"`{{{{{var_for_param(path, p)}}}}}`" for p in path_vars
        )
        description_parts.append(f"Set {rendered} in your environment or let an earlier request populate it.")
    description_parts.append(f"`{method.upper()} {path}`")

    request: dict[str, Any] = {
        "method": method.upper(),
        "header": headers,
        "url": build_url(path, params, spec),
        "description": "\n\n".join(description_parts),
    }
    if body:
        request["body"] = body

    item: dict[str, Any] = {
        "name": humanise(op, method, path),
        "id": _uuid(f"{method} {path}"),
        "request": request,
        "response": [],
    }

    script = REQUEST_SCRIPTS.get((method, path))
    if script:
        item["event"] = [
            {
                "listen": "test",
                "script": {"type": "text/javascript", "exec": script},
            }
        ]
    return item


def build_collection(spec: dict, base_url: str) -> dict:
    info = spec.get("info", {})
    folders: dict[str, list[dict]] = {}

    for path, path_item in spec.get("paths", {}).items():
        shared_params = path_item.get("parameters", [])
        for method, op in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            # HEAD/OPTIONS duplicates of a GET add noise without adding coverage.
            if method in {"head", "options"}:
                continue
            merged = dict(op)
            if shared_params:
                merged["parameters"] = shared_params + op.get("parameters", [])
            tag = (op.get("tags") or ["health"])[0]
            folders.setdefault(tag, []).append(
                build_request_item(method, path, merged, spec)
            )

    items = []
    for tag in sorted(folders, key=lambda t: (TAG_ORDER.index(t) if t in TAG_ORDER else 99, t)):
        requests = folders[tag]

        # Split the code-server proxy out of the pods folder — it exists for the
        # browser and would otherwise bury the endpoints you actually call.
        if tag == "pods":
            proxy = [r for r in requests if "/vscode/" in r["request"]["url"]["raw"]]
            requests = [r for r in requests if "/vscode/" not in r["request"]["url"]["raw"]]
            if proxy:
                requests.append(
                    {
                        "name": "VS Code proxy (browser-only)",
                        "id": _uuid("folder:vscode-proxy"),
                        "description": (
                            "Passthrough to the code-server running inside a VM. These "
                            "exist so the browser IDE works through the gateway; calling "
                            "them from Postman is rarely useful."
                        ),
                        "item": proxy,
                    }
                )

        items.append(
            {
                "name": TAG_TITLES.get(tag, tag),
                "id": _uuid(f"folder:{tag}"),
                "description": TAG_DESCRIPTIONS.get(tag, ""),
                "item": requests,
            }
        )

    overview = f"""# Hopper API

{info.get('description', '')}

Hopper slices a Kubernetes cluster into per-student VMs with credit-based
billing. This collection is generated from the gateway's OpenAPI spec, so it
matches the deployed API exactly.

## Getting started

1. Select the **Hopper — Production** environment (top-right).
2. Set `userEmail` and `userPassword` to your account.
3. Send **1. Auth & API keys → Login**. That is all the setup there is — the
   `session_token` cookie lands in Postman's cookie jar and every other request
   uses it automatically.

## The two ways to authenticate

**Session cookie** (what `Login` gives you) — httpOnly, expires in ~5 minutes,
refreshed via `Refresh session`. Best for clicking around.

**API key** — send `X-API-Key: hop_...` (or `Authorization: Bearer hop_...`).
Create one with **Create API key** while logged in; the test script stores it in
the `apiKey` variable and the collection then prefers it over the cookie.
Best for scripts and CI.

Collection-level auth is configured as the API-key header. When `apiKey` is
empty the gateway ignores the header and falls back to the cookie, so both
paths work without you changing any settings.

Two constraints worth knowing before you debug a confusing 4xx:
- A `read_only` key is rejected with **403** on anything that is not
  GET/HEAD/OPTIONS.
- Creating or revoking API keys deliberately requires a cookie session, so an
  API key cannot mint another API key. Log in first.

## Variables

`baseUrl` and credentials live in the environment. Resource ids
(`podId`, `userId`, `keyId`, ...) are collection variables that the test scripts
fill in as you go — create a VM and the rest of the pods folder targets it
without you copying anything.

## Rate limits

Per-user for cookie sessions and per-key for API keys, so a script cannot
exhaust your browser session's budget. Login is 10/min, and 3 failed sign-ins
per (IP, email) trips a temporary block. A 429 carries `X-RateLimit-*` headers.

## Regenerating

```
python scripts/api/generate_postman.py
```

Re-run it after changing any route or schema and commit the result.
"""

    return {
        "info": {
            "_postman_id": _uuid("collection:hopper"),
            "name": "Hopper API",
            "description": overview,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "X-API-Key", "type": "string"},
                {"key": "value", "value": "{{apiKey}}", "type": "string"},
                {"key": "in", "value": "header", "type": "string"},
            ],
        },
        "event": [
            {
                "listen": "test",
                "script": {
                    "type": "text/javascript",
                    "exec": [
                        "// Applies to every request in the collection.",
                        "pm.test('No server error', function () {",
                        "  pm.expect(pm.response.code, 'HTTP status').to.be.below(500);",
                        "});",
                        "",
                        "if (pm.response.code === 401) {",
                        "  console.warn('401 - run \"Login\" first, or set apiKey. Sessions expire after ~5 minutes.');",
                        "}",
                        "if (pm.response.code === 403) {",
                        "  console.warn('403 - insufficient role, or a read_only API key on a write request.');",
                        "}",
                        "if (pm.response.code === 429) {",
                        "  console.warn('429 - rate limited. Retry-After:', pm.response.headers.get('Retry-After'));",
                        "}",
                    ],
                },
            }
        ],
        "variable": [
            {"key": "baseUrl", "value": base_url, "type": "string"},
            {"key": "apiKey", "value": "", "type": "string"},
            {"key": "podId", "value": "", "type": "string"},
            {"key": "userId", "value": "", "type": "string"},
            {"key": "keyId", "value": "", "type": "string"},
            {"key": "queueEntryId", "value": "", "type": "string"},
            {"key": "notificationId", "value": "", "type": "string"},
            {"key": "issueId", "value": "", "type": "string"},
            {"key": "planName", "value": "small", "type": "string"},
            {"key": "imageTemplate", "value": "ubuntu", "type": "string"},
            {"key": "vscodePath", "value": "", "type": "string"},
        ],
        "item": items,
    }


def build_environment(name: str, base_url: str) -> dict:
    return {
        "id": _uuid(f"env:{name}"),
        "name": name,
        "values": [
            {"key": "baseUrl", "value": base_url, "type": "default", "enabled": True},
            {"key": "userEmail", "value": "", "type": "default", "enabled": True},
            # secret => Postman masks it and leaves it out of shared exports.
            {"key": "userPassword", "value": "", "type": "secret", "enabled": True},
            {"key": "apiKey", "value": "", "type": "secret", "enabled": True},
        ],
        "_postman_variable_scope": "environment",
    }


def load_spec(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as resp:  # noqa: S310
            return json.load(resp)
    return json.loads(Path(source).read_text())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", default=DEFAULT_SPEC, help="OpenAPI URL or file path")
    ap.add_argument("--base-url", default=PROD_BASE_URL, help="baseUrl baked into the collection")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="output directory")
    args = ap.parse_args()

    try:
        spec = load_spec(args.spec)
    except Exception as exc:
        print(f"error: could not load spec from {args.spec}: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    collection = build_collection(spec, args.base_url)
    targets = [
        (out_dir / "hopper.postman_collection.json", collection),
        (
            out_dir / "hopper.postman_environment.production.json",
            build_environment("Hopper — Production", PROD_BASE_URL),
        ),
        (
            out_dir / "hopper.postman_environment.local.json",
            build_environment("Hopper — Local", LOCAL_BASE_URL),
        ),
    ]
    for dest, payload in targets:
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {dest.relative_to(REPO_ROOT)}")

    n_requests = sum(
        len([i for i in folder["item"] if "request" in i])
        + sum(len(sub["item"]) for sub in folder["item"] if "item" in sub)
        for folder in collection["item"]
    )
    print(f"{len(collection['item'])} folders, {n_requests} requests")

    # Drift guards. Neither is fatal — the collection is still usable — but an
    # unnamed route ships a label like "Vscode Proxy" into the sidebar, and a
    # stale override means a route was renamed or removed upstream.
    live = {
        (m, p)
        for p, item in spec.get("paths", {}).items()
        for m in item
        if m in {"get", "post", "put", "patch", "delete"}
    }
    unnamed = sorted(live - set(NAME_OVERRIDES))
    stale = sorted(set(NAME_OVERRIDES) - live)
    for m, p in unnamed:
        print(f"  note: no name override for {m.upper()} {p}", file=sys.stderr)
    for m, p in stale:
        print(f"  note: override no longer matches any route: {m.upper()} {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
