# Hopper frontend — local development

SvelteKit + Vite frontend for Hopper. You can develop it **without running the
backend locally** by pointing it at a deployed environment
(`https://hopper.farefin.com`). This guide covers that setup end to end,
including the two things that don't work out of the box against a remote backend:
**login** and the **in-browser terminal / VS Code WebSockets**.

## TL;DR

```bash
cd frontend
cp .env.example .env          # defaults already point at https://hopper.farefin.com
# put a dev password in .env -> DEV_LOGIN_PASS=...
pnpm install
pnpm dev                      # http://127.0.0.1:5173
```

Open http://127.0.0.1:5173, click **"Dev login (skip SSO)"** → you're in.

> Use `127.0.0.1`, not `localhost` (keeps the cookie host stable and matches the
> dev server bind). If a port other than 5173 is used, see "CORS / origin" below.

## Requirements

- Node 22 (`.nvmrc`-style — match the Docker image `node:22`)
- pnpm 9+ (the repo's Docker build pins pnpm 9; pnpm 10/11 also work, see
  `pnpm-workspace.yaml`)

If you're on pnpm 10/11 and `pnpm install` fails with
`ERR_PNPM_IGNORED_BUILDS: esbuild`, that's the build-script block introduced in
pnpm 10. It's already handled by `pnpm-workspace.yaml`:

```yaml
allowBuilds:
  esbuild: true
```

## Configuration (`.env`)

Copy `.env.example` to `.env` (gitignored). All values default to the deployed
environment. The vars fall into three groups.

### 1. Client-side calls — browser → Vite proxy → backend

The browser calls `fetch('/api/...')`. `vite dev` proxies `/api/*` to the
backend.

| Var | Default | Meaning |
|-----|---------|---------|
| `API_PROXY_TARGET` | `https://hopper.farefin.com` | Where `/api/*` is forwarded. Local gateway: `http://127.0.0.1:8000`. |
| `API_PROXY_STRIP_PREFIX` | `false` | `true` for a local gateway (serves routes without `/api`); `false` for the deployed ingress (it strips `/api` itself). |
| `API_PROXY_SECURE` | `true` | Verify TLS certs on an https backend. |
| `API_PROXY_ORIGIN` | `https://hopper.farefin.com` | **Origin header presented to the backend.** Required for WebSockets — see below. |

### 2. Server-side calls — SvelteKit SSR load functions → backend

SSR `+page.server.ts` / `+layout.server.ts` fetch the backend directly via
`apiUrl()` (they don't go through the Vite proxy).

| Var | Default | Meaning |
|-----|---------|---------|
| `API_INTERNAL_URL` | `https://hopper.farefin.com/api` | Base URL for SSR fetches, **including** the `/api` prefix the ingress expects. |

### 3. Dev login (the "Dev login (skip SSO)" button)

| Var | Default | Meaning |
|-----|---------|---------|
| `KEYCLOAK_EXTERNAL_URL` | `https://hopper.farefin.com` | Keycloak base URL. |
| `KEYCLOAK_REALM` | `hopper` | Realm. |
| `KEYCLOAK_CLIENT_ID` | `hopper-api` | OIDC client (public, PKCE). |
| `KEYCLOAK_CLIENT_SECRET` | _(empty)_ | Only for a confidential client. |
| `DEV_LOGIN_USER` | `admin` | Admin account — `/dev-login` or `/dev-login?as=admin`. |
| `DEV_LOGIN_PASS` | _(empty)_ | Admin password — put a real dev credential in `.env`. |
| `DEV_LOGIN_USER_ALT` | `testuser` | Regular (non-admin) account — `/dev-login?as=user`. |
| `DEV_LOGIN_PASS_ALT` | _(empty)_ | Regular-account password. |

## Why login needs a workaround

The real **"Continue with University SSO"** button hits `/api/auth/login`, which
redirects to Keycloak. The **deployed backend builds the OAuth `redirect_uri`
from its own host** (`HOPPER_CALLBACK_URL = https://hopper.farefin.com/api/auth/callback`).
So after you authenticate, Keycloak returns the browser to the **remote**
callback, which sets the session cookie on `hopper.farefin.com` — your localhost
dev server never sees it. You end up logged in on the remote site, not locally.

Fixing the real flow needs backend + Keycloak config changes on the shared
remote host (a per-client redirect_uri allowlist), which is out of scope for
frontend work.

### The fix: `/dev-login`

`src/routes/dev-login/+server.ts` is a **dev-only** endpoint (guarded by
SvelteKit's `dev` flag — it 404s in any production build). It does a Keycloak
Resource Owner Password grant with `DEV_LOGIN_USER`/`DEV_LOGIN_PASS`, then sets
the same `session_token` / `refresh_token` / `id_token` cookies the real
`/auth/callback` would, and redirects to `/dashboard`.

The token is a stateless RS256 JWT validated against Keycloak's JWKS, so the
remote API accepts it no matter which host presents it. Both call paths then
authenticate: SSR loads (via `API_INTERNAL_URL`) and client fetches (via the
Vite `/api` proxy).

The login page shows two dev-only buttons (only when `dev` is true):

- **Dev: admin** → `/dev-login?as=admin` (role `admin`)
- **Dev: user** → `/dev-login?as=user` (regular non-admin account, role `student`)

Test any other account without editing `.env`:

```
http://127.0.0.1:5173/dev-login?user=someone&pass=secret
```

**Session lifetime:** the access token is short-lived (~5 min). Two things keep
the session alive:

1. `+layout.server.ts` refreshes on each SSR navigation, and
2. `+layout.svelte` runs a **client-side keepalive** — it POSTs
   `/api/auth/refresh` every 4 minutes while authenticated.

The keepalive matters for long-lived pages with no navigation (chiefly the pod
**terminal**): without it the access cookie expires, and the first transient
WebSocket drop would reconnect with a dead cookie (close 1008) and never
recover. With it, the terminal stays connected indefinitely.

## Why the terminal / VS Code need `API_PROXY_ORIGIN`

The in-browser terminal connects over a WebSocket
(`ws://127.0.0.1:5173/api/pods/{id}/terminal`, proxied to the backend). The
backend's WebSocket handlers **gate by `Origin`** and reject anything not in
their CORS allowlist (production = `https://hopper.farefin.com`).

Vite's `changeOrigin: true` rewrites only the **Host** header, not **Origin**, so
the browser's `http://127.0.0.1:5173` Origin reaches the backend and is rejected
(HTTP 403 → the terminal shows *"Connection lost — Reconnecting"*, WS close code
1006).

The Vite proxy (`vite.config.ts`) fixes this by overriding the `Origin` header on
proxied HTTP and WebSocket requests to `API_PROXY_ORIGIN`. With it set to
`https://hopper.farefin.com`, the upgrade is accepted and the terminal reaches a
live shell. The same applies to the VS Code WebSocket.

`API_PROXY_ORIGIN` defaults to the `API_PROXY_TARGET` origin for https targets,
so the remote setup works even if you don't set it explicitly. Leave it **unset**
when targeting a local gateway (it already allows localhost).

### VS Code (code-server) — extra proxy rule

"Open VS Code" navigates to `/{userId}/code/{podId}/` (and the port-preview proxy
at `.../proxy/{port}/`). These are **not** under `/api`, so the default proxy
wouldn't forward them — they'd hit SvelteKit and 404. `vite.config.ts` adds a
regex proxy rule (`^/[^/]+/code/`) that forwards the whole code-server path tree
to the backend with `ws: true` (code-server's RPC socket) and the same Origin
override. With it, the full VS Code workbench loads in the browser locally.

> The 404s on `vsda.js` / `vsda_bg.wasm` in the console are harmless — that's
> code-server's optional proprietary signing module; it 404s on the real
> deployment too.

### CORS / origin gotcha

The backend allowlist is checked against the **Origin you send**, which the proxy
forces to `API_PROXY_ORIGIN`. So the dev server port (5173 vs another) doesn't
affect WebSocket auth here. If you point at a **local** backend instead, make
sure its `HOPPER_CORS_ORIGINS` includes your dev origin (`http://localhost:5173`).

## Running against a local backend instead

If you do run the api-gateway locally:

```ini
API_PROXY_TARGET=http://127.0.0.1:8000
API_PROXY_STRIP_PREFIX=true
API_PROXY_SECURE=false
API_PROXY_ORIGIN=            # leave empty
API_INTERNAL_URL=            # leave empty -> relative /api
```

The real SSO flow works locally if the local backend's `HOPPER_CALLBACK_URL`
points at `http://localhost:5173/api/auth/callback` and Keycloak allows that
redirect URI. Otherwise use **Dev login** as above.

## Scripts

| Command | What it does |
|---------|--------------|
| `pnpm dev` | Start the dev server (http://127.0.0.1:5173) |
| `pnpm build` | Production build (`adapter-node`) |
| `pnpm preview` | Preview the production build |
| `pnpm check` | `svelte-check` type checking |
| `pnpm lint` | ESLint |
| `pnpm test` | Vitest |

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Login bounces to `hopper.farefin.com` | Expected for the real SSO button on localhost. Use **Dev login**. |
| `/dev-login` shows `?error=devlogin` | Keycloak token request failed — check `DEV_LOGIN_USER`/`DEV_LOGIN_PASS` and `KEYCLOAK_*`. |
| Terminal: *"Connection lost — Reconnecting"* | `API_PROXY_ORIGIN` not set / wrong. Must be the backend's origin. |
| Terminal drops after a few minutes | Was the expiring access token; the `+layout.svelte` keepalive fixes it. If it still drops, check `/api/auth/refresh` returns 200 through the proxy. |
| VS Code: blank page / 404 / 502 | Missing the `^/[^/]+/code/` proxy rule, or the session cookie expired (re-click **Dev login**). |
| App goes 401 after idle | Access token expired; click **Dev login** again. |
| `ERR_PNPM_IGNORED_BUILDS: esbuild` | pnpm 10/11 — ensure `pnpm-workspace.yaml` has `allowBuilds: { esbuild: true }`, then `pnpm install`. |
| 404 on `/api/...` | `API_PROXY_STRIP_PREFIX` wrong for your target (false for remote ingress, true for local gateway). |
