# Hopper API — Postman collection

A ready-to-run Postman collection covering all 73 endpoints of the Hopper API
gateway, plus environments for the deployed and local backends.

| File | Purpose |
| --- | --- |
| `hopper.postman_collection.json` | The collection — 11 folders, 73 requests |
| `hopper.postman_environment.production.json` | Points at `https://hopper.farefin.com/api` |
| `hopper.postman_environment.local.json` | Points at `http://127.0.0.1:8000` |

## Import

**By link** (stays current as the file changes on `main`):

```
https://raw.githubusercontent.com/CREVIOS/Hopper/main/docs/api/hopper.postman_collection.json
```

In Postman: **Import → Link → paste → Continue**. Import the environment file
the same way.

**By file:** clone the repo and drag the three files onto the Postman window.

Everything works in Insomnia, Bruno, and Hoppscotch too — they all read the
Postman v2.1 format.

## First run

1. Select the **Hopper — Production** environment (top-right dropdown).
2. Fill in `userEmail` and `userPassword`.
3. Send **1. Auth & API keys → Login**.

That is the whole setup. Login sets the httpOnly `session_token` cookie, Postman
keeps it in its cookie jar, and every other request picks it up automatically —
there is no token to copy anywhere.

## Authentication

The gateway accepts two credentials, and this collection supports both.

**Session cookie.** What `Login` gives you. The access cookie tracks the access
token's TTL (~5 minutes), so a long Postman session will start returning 401 —
send **Refresh session** or log in again.

**API key.** Send `X-API-Key: hop_...`, or `Authorization: Bearer hop_...`.
Create one with **Create API key** while logged in; its test script writes the
value into the `apiKey` variable for you. The plaintext key is returned exactly
once — only its SHA-256 hash is stored — so a lost key must be revoked and
recreated.

Collection-level auth is set to the API-key header. When `apiKey` is empty the
gateway ignores the header and falls through to the cookie, so both paths work
without touching any settings.

Two rules that otherwise produce confusing failures:

- A `read_only` key returns **403** on anything that is not GET/HEAD/OPTIONS.
  Use `full_access` if you need to create or delete.
- Creating and revoking API keys requires a real cookie session — a key cannot
  mint another key. Log in first.

## Variables

`baseUrl` and credentials live in the **environment**. Resource ids live in
**collection variables** and are filled in by test scripts as you work:

| Variable | Set by |
| --- | --- |
| `podId` | `Create VM`, or `List VMs` (first result) |
| `userId` | `Login` |
| `apiKey` | `Create API key` |
| `keyId` | `Add SSH key` |
| `issueId` | `Report issue` |

So the usual path — create a VM, then check its metrics, files and usage — needs
no copy-pasting of ids.

## Notes on specific endpoints

- **`POST /pods/` is asynchronous.** It returns before the VM boots; poll
  `Get VM` until `state` is `running`. If the cluster is full the request is
  queued rather than rejected, and the response carries a queue position.
- **`GET /notifications/stream` is Server-Sent Events.** It never completes.
  Postman showing it as still-running is expected, not a hang.
- **`POST /files/{pod_id}/upload` is multipart.** Pick a local file for the
  `file` field in Postman's Body tab; an exported collection cannot carry file
  contents.
- **The VS Code proxy folder is browser-only.** It exists so the in-browser IDE
  reaches code-server through the gateway. Calling it from Postman is rarely
  useful, which is why it is filed separately.
- **Trailing slashes matter.** The gateway is served under `/api` by the
  ingress, but FastAPI builds its redirect from its own root — so `/api/pods`
  307s to `/pods/`, which is the frontend, not the API. The collection always
  uses the exact registered path.

## Rate limits

Limits are per-user for cookie sessions and per-key for API keys, so a script
cannot exhaust your browser session's budget. Login is 10/min, and 3 *failed*
sign-ins per (IP, email) trips a temporary block — counting only failures keeps
a shared campus NAT from locking everyone out at once. A 429 response carries
`X-RateLimit-*` headers, and the collection logs a warning when it sees one.

## Regenerating

The collection is generated from the gateway's OpenAPI spec — FastAPI is the
single source of truth, so the collection cannot drift from the routes.

```bash
# from the deployed gateway
python scripts/api/generate_postman.py

# from a local gateway, or a saved spec
python scripts/api/generate_postman.py --spec http://127.0.0.1:8000/openapi.json
python scripts/api/generate_postman.py --spec /tmp/openapi.json
```

Output is deterministic — regenerating an unchanged spec produces a byte
-identical file, so a diff always means the API actually changed. Re-run it
after adding or changing a route and commit the result.

Curated prose, example bodies and chaining scripts live in
`scripts/api/generate_postman.py`; edit them there, not in the generated JSON.
