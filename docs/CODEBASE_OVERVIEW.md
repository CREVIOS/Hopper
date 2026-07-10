# Hopper — Codebase Overview & System Workflow

> Generated from a full code-level exploration of the repository (every claim below was verified
> against actual source files; file paths are given so you can jump to the evidence).
> Where the README/docs and the code disagree, the discrepancy is called out explicitly in §11.

---

## 1. What Hopper Is

Hopper is a **self-hosted "VM cloud" platform for universities**. Students and professors launch
isolated Linux environments ("VMs" — actually hardened Kubernetes pods) with SSH access, an
in-browser terminal, and in-browser VS Code (code-server). Usage is metered through a
**double-entry credit ledger**: every running VM burns credits per minute, and when a user's
balance hits zero the VM is automatically terminated. Identity is handled by **Keycloak (OIDC)**
with three roles: `admin`, `professor`, `student`.

The production deployment is a **single-node k3s cluster on an Azure VM**
(`hopper.farefin.com`, node IP `10.0.0.6`) behind nginx ingress with Let's Encrypt TLS.

---

## 2. High-Level Architecture

```
                            Browser
                               │
                    Nginx Ingress (hopper.farefin.com, TLS)
        ┌───────────────┬──────┴────────────┬──────────────────────┐
        │ /              │ /api/*            │ /realms,/resources    │ /{uid}/code/{podId}/*
        ▼                ▼                   ▼                       ▼
   Frontend         API Gateway          Keycloak            API Gateway (vscode proxy)
   (SvelteKit,      (FastAPI, :8000)     (OIDC, :8080)
    :3000, SSR)          │
                         ├── PostgreSQL + TimescaleDB (users, pod_sessions, credit ledger,
                         │                             metrics hypertable, audit log)
                         ├── NATS (core pub/sub — billing + metrics events)
                         │
                         ▼ gRPC (hopper.pod.v1.PodOrchestrator, :50051)
                    Orchestrator (Go)
                         │
                         ▼ Kubernetes API
              VM Pods (label app=hopper-vm) + NodePort Services (SSH:22, code-server:8080)
                         │
              Billing Ticker (60s/pod) ──► NATS billing.deducted ──► API Gateway (ledger deduct)
              Metrics Publisher (5s)   ──► NATS metrics.<pod>    ──► API Gateway (SSE + hypertable)
                                             API Gateway ──► NATS billing.exhausted ──► Orchestrator kills pod
```

| Service | Language / Framework | Port | Source |
|---|---|---|---|
| Frontend | SvelteKit 2 / Svelte 5 (runes), adapter-node, SSR | 3000 | `frontend/` |
| API Gateway | Python 3.12 / FastAPI (uvicorn, 4 workers) | 8000 | `services/api-gateway/` |
| Orchestrator | Go 1.23 / gRPC | 50051 | `services/orchestrator/` |
| PostgreSQL | TimescaleDB (pg16) | 5432 (5433 on host in dev) | docker-compose / `k8s/deploy/01-infra.yaml` |
| NATS | 2.10 (server started with `--jetstream`, but clients use **core** pub/sub) | 4222 | same |
| Keycloak | 25.0, realm `hopper` | 8080 | same |
| VM images | Ubuntu 22.04 + sshd + supervisord + code-server | 22, 8080 | `images/hopper-vm*/` |

---

## 3. Repository Layout

```
Hopper/
├── frontend/                 SvelteKit web UI
├── services/
│   ├── api-gateway/          FastAPI REST API, auth, ledger, NATS consumers
│   └── orchestrator/         Go gRPC service: pod lifecycle, billing ticker, metrics
├── proto/hopper/             Canonical protobuf contracts (pod/v1, billing/v1) — buf v2
├── images/                   VM container images (base + python/cpp/java variants)
├── k8s/
│   ├── deploy/               ✅ REAL production manifests (00-secrets … 05-cert-manager)
│   ├── base/, gpu-operator/, kai-scheduler/, kueue/, network-policies/   ⚠️ skeleton/aspirational
├── infrastructure/           ⚠️ ansible / argocd / pulumi — skeletons, not driving the deploy
├── observability/            ⚠️ Prometheus/Grafana/Loki configs — not installed by any manifest
├── scripts/                  deploy-local.sh, dev-setup.sh, generate-proto.sh,
│                             keycloak-harden.sh, ci/, cd/
├── tests/                    unit (pytest), integration (Testcontainers), e2e (Playwright),
│                             load (k6, semi-stub), chaos (Chaos Mesh, stub)
├── docs/                     ARCHITECTURE, SDD, SRS, TECH_STACK, testing docs
├── docker-compose.yml        Local dev infra only (postgres, nats, keycloak)
└── Makefile                  Convenience targets for everything above
```

---

## 4. The API Gateway (FastAPI) — `services/api-gateway/`

### 4.1 Startup lifecycle (`app/main.py`)

`create_app()` builds the app; the `lifespan` handler runs, in order:
1. `setup_logging()` (structlog — note: hardwired to console renderer)
2. `orchestrator_client.connect()` — async gRPC channel to the orchestrator
3. `nats_client.connect()` — core NATS connection
4. `start_billing_consumer()` — subscribes `billing.deducted` + `billing.exhausted`
5. `start_metrics_consumer()` — subscribes `metrics.*`

Middleware: `AuditMiddleware` (fire-and-forget audit logging of all mutating requests to
`audit_logs`, with JWT re-verification for attribution), CORS (startup **refuses to boot** if
`*` is in allowed origins), security headers, and slowapi rate limiting (default 120/min,
stricter per-route limits on auth and pod creation). Runs with `uvicorn --workers 4` — which is
why the NATS consumers use **queue groups** (`billing-workers`, `metrics-workers`) so only one
worker processes each message.

### 4.2 Routers & endpoints

| Prefix | File | Highlights |
|---|---|---|
| `/auth` | `app/routers/auth.py` | OIDC redirect login (`GET /login`, PKCE + state + nonce), `GET /callback`, direct-grant `POST /login`, `POST /signup` (teacher signups become `student` + `pending_teacher=true`), `POST /verify-email`, `/resend-code`, `/forgot-password`, `/reset-password`, `POST /refresh`, `GET /me`, `POST /logout` (RP-initiated Keycloak logout). Tokens live in **HttpOnly cookies** (`session_token`, `refresh_token`, `id_token`), never exposed to JS. |
| `/pods` | `app/routers/pods.py` | `GET /plans` (public), `GET /` list, `POST /` create (402 if balance < plan rate, 429 if ≥3 concurrent pods), `GET/DELETE /{id}`, **SSE** `GET /{id}/metrics`, HTTP+WS reverse proxy `/{id}/vscode/{path}` to code-server, and **WS `/{id}/terminal`** — an in-browser SSH terminal implemented with `asyncssh` to the pod's port 22 (via `kubectl port-forward`, NodePort fallback), enforcing JWT-cookie + ownership + Origin, 64 KB input cap, 10-min idle timeout. |
| `/credits` | `app/routers/credits.py` | `GET /balance`, `GET /history`, `GET /teachers` (admin), `GET /students` (admin or professor), `POST /allocate` — role-aware: admin grants from the system account; professor transfers from their own balance to a student. |
| `/admin` | `app/routers/admin.py` | All gated on `role == "admin"`. Users list, teacher-request approve/reject (promotes to `professor` in Keycloak + DB and force-logs-out the user), `PATCH /users/{id}/role` (blocks self-demotion and removing the last admin), `GET /nodes` (gRPC `ListNodes`), `GET /stats`, `GET /active-vms`, `GET /audit-logs`. `GET /courses` is a stub returning `[]`. |
| `/ssh-keys` | `app/routers/ssh_keys.py` | CRUD, SHA-256 fingerprint dedup, `pg_advisory_xact_lock` per user, max 10 keys. |
| `/files` | `app/routers/files.py` | Pod file browser: list / upload / download via `sshpass` + SCP over port-forward. Owner + running-state required. |
| `/usage` | `app/routers/usage.py` | Historical usage from the TimescaleDB hypertable using `time_bucket` (falls back to `date_trunc` without Timescale). Per-pod and per-user series/summary. |
| `/issues` | `app/routers/issues.py` | User issue reports + admin resolution. |
| `/settings` | `app/routers/settings.py` | `PUT /vscode` — **stub**, accepts and discards. |
| — | `/healthz`, `/readyz` | Health probes. |

### 4.3 Auth & RBAC (`app/middleware/auth.py`, `app/dependencies.py`)

- `verify_token` fetches Keycloak **JWKS** (cached by `kid`, 10-min TTL, force-refresh on rotation)
  and verifies RS256 signature, `aud` (= `hopper-api`), `iss`, `exp`.
- `get_current_user` reads the **`session_token` cookie** (not a Bearer header).
- Role = first of `realm_access.roles ∩ {admin, professor, student}`, defaulting to `student`.
  "Teacher" is *not* a role — it's the `users.pending_teacher` flag until an admin approves,
  at which point the user becomes `professor`.
- Keycloak mutations (create user, set role, verify email, reset password, force logout) go
  through a confidential service-account client `hopper-admin`
  (`app/services/keycloak_admin.py`).

### 4.4 The credit ledger (`app/services/credit_service.py`, `app/models/credit_ledger.py`)

A textbook **double-entry ledger**:

- Tables: `accounts` (system account `0000…0000` = liability; user accounts = asset),
  `transfers` (one per logical movement; **the transfer ID is the primary key and the
  idempotency key**), `ledger_entries` (paired debit/credit rows carrying
  `previous_balance`/`current_balance` running totals).
- `get_balance` reads the latest entry's `current_balance` (O(1), not a SUM).
- `add_credits` — admin grant, system → user.
- `allocate_between_users` — professor → student transfer, serialized with
  `pg_advisory_xact_lock`, fails on insufficient balance.
- `deduct_credits` — user → system, **idempotent via `tx_id` as the Transfer PK**: a redelivered
  billing message hits a duplicate-key error and becomes a no-op.

### 4.5 Database models (`app/models/`, migrations in `alembic/versions/001–012`)

| Table | Purpose |
|---|---|
| `users` | id, email, name, role, `pending_teacher`, university_id |
| `pod_sessions` | plan, image, cpu/memory, namespace, `pod_name` (K8s name), ssh/vscode NodePorts, `ssh_password`, state, timestamps |
| `accounts` / `transfers` / `ledger_entries` | double-entry credit ledger (above) |
| `metrics_samples` | **TimescaleDB hypertable** (composite PK time+pod_id, 30-day retention policy; degrades to a plain table if Timescale is absent — migration 008) |
| `audit_logs` | who did what (from AuditMiddleware + explicit admin actions) |
| `ssh_keys` | user public keys + fingerprints |
| `issue_reports` | user-filed issues |
| `email_codes` | SHA-256-hashed verification/reset codes, attempt-capped, single-use |

### 4.6 Configuration

`app/config.py` (pydantic-settings, env prefix **`HOPPER_`**): `database_url` (default port
5433 to match the dev compose mapping), `nats_url`, Keycloak internal/external URLs + realm +
client IDs/secrets, `orchestrator_url`, `frontend_url`, `cors_origins`, email/SMTP block
(empty `smtp_host` ⇒ DEV mode: codes are logged, not emailed), `allowed_email_domains`,
`node_ip`, rate/TTL knobs.

---

## 5. The Orchestrator (Go) — `services/orchestrator/`

### 5.1 Startup (`cmd/orchestrator/main.go`)

1. Connect NATS (infinite reconnect).
2. Build K8s clientset (in-cluster config first, then `KUBECONFIG`); metrics-server client is
   optional — without it live CPU/RAM read as 0.
3. Build the gRPC server (registers **health**, **PodOrchestrator**, **BillingService**).
4. Subscribe `billing.exhausted` (auto-terminate handler).
5. **`watcher.Reconcile`** — synchronous crash recovery (below), then `go watcher.Watch`.
6. Start the 5-second metrics publisher.
7. Serve gRPC on `:50051` (hardcoded port). Graceful stop on SIGINT/SIGTERM.

There is **no database**: authoritative runtime state is an in-memory `pod.Manager`
(`internal/pod/manager.go`, mutex-guarded map with a validated state machine
pending → creating → running → stopping → terminated, any → failed). **Kubernetes itself is the
durable store** — on restart, `Reconcile` rebuilds everything from live pods labeled
`app=hopper-vm`: state from pod phase, NodePorts from the `ssh-<name>` Service, the SSH password
from the pod annotation, and it **restarts billing tickers** for running pods.

### 5.2 gRPC contract (`proto/hopper/pod/v1/pod.proto`)

Service `hopper.pod.v1.PodOrchestrator`:

| RPC | Used by gateway? | What it does |
|---|---|---|
| `CreatePod` | ✅ (`POST /pods/`) | Full VM provisioning (below) |
| `TerminatePod` | ✅ (`DELETE /pods/{id}`) | Stop billing, delete K8s resources |
| `ListNodes` | ✅ (`GET /admin/nodes`) | Node capacity + hopper-vm pod counts |
| `GetPodStatus` | ❌ defined, never called | Reads in-memory state |
| `StreamMetrics` | ❌ unused | Server-stream; superseded by NATS metrics |
| `WatchPodStatus` | ❌ unused | Sends one status then returns (not a real watch) |

`hopper.billing.v1.BillingService` (`DeductCredits`/`GetBalance`/`StreamUsage`) is registered but
**all handlers are placeholders** — real billing flows over NATS (§7).

### 5.3 VM pod creation (`internal/k8s/pod.go`)

For each `CreatePod`, the orchestrator creates in namespace `hopper`:

- **Pod** named `vm-<unixNano>`, labels `app=hopper-vm`, `role=user-vm`, `hopper.dev/pod-id`
  (the gateway's session UUID), `hopper.dev/user-id`, `hopper.dev/plan`.
  - Container runs `chpasswd` with a fresh **24-char crypto/rand root password** (also stored as
    pod annotation `hopper.dev/ssh-password` for crash recovery), then `supervisord` (which runs
    sshd + code-server). Env `CS_BASE_PATH=/{userId}/code/{podId}` path-prefixes code-server.
  - **Resources**: CPU request = ¼ of the plan limit (min 100m, for bin-packing), CPU limit =
    plan; memory request = limit (pinned). Plans: small 1 CPU/2 GB, medium 2/4, large 4/8.
  - **Security**: service-account token not mounted, seccomp `RuntimeDefault`, all capabilities
    dropped then a minimal set re-added (no `NET_RAW`), `allowPrivilegeEscalation=false`.
  - **LXCFS** hostPath mounts over `/proc/{meminfo,cpuinfo,…}` so `free`/`nproc` inside the VM
    show the cgroup limits, not the host's (requires `lxcfs` on each node).
- **NodePort Service** `ssh-<podName>` exposing container ports 22 (SSH) and 8080 (code-server);
  the auto-assigned NodePorts (30000–32767) are returned to the gateway and shown to the user
  (`ssh root@<node-ip> -p <nodePort>`).
- PVC support (`ws-<podName>` mounted at `/workspace`) exists in the K8s layer, **but the
  `CreatePod` handler never plumbs the proto `disk` field through** — so in practice VMs are
  ephemeral (see §11).

`TerminatePod` / exhaustion / external deletion all: stop the billing ticker → delete Service →
delete Pod (5 s grace, preStop `pkill -HUP sshd`) → delete PVC → publish `pod.stopped`.

The **watcher** (`internal/k8s/watcher.go`) keeps a continuous K8s watch on `app=hopper-vm`:
syncs in-memory state on pod modifications, and on external failure/deletion stops billing and
publishes `pod.stopped` with a reason.

### 5.4 Billing ticker (`internal/billing/ticker.go`)

- One goroutine per running pod, ticking every **60 seconds**.
- Each tick publishes `billing.deducted` with amount `credits_per_hour / 60` and a
  **deterministic `tx_id` = `<podId>:<seq>`** — this is what makes ledger deduction idempotent.
- `StopAndProrate` (final partial-minute charge) is implemented but **never called**; terminate
  paths use plain `Stop`, so the last partial minute is not billed.

### 5.5 Metrics publisher (`internal/events/metrics_publisher.go`)

Every **5 seconds**, for every running pod: read usage from **metrics-server**
(`CPUNanoCores`, `MemoryBytes`) and publish to `metrics.<k8sPodName>` — keyed by the K8s pod
name (`vm-…`), which is exactly what the gateway's SSE endpoint and metrics consumer subscribe to.

---

## 6. The Frontend (SvelteKit) — `frontend/`

### 6.1 Architecture

- **Full SSR** (adapter-node, `node build`, port 3000). Every protected page has a
  `+page.server.ts` load that fetches from the gateway and gates auth; there is no client-side
  auth logic beyond a 401→refresh→retry interceptor.
- Two API layers:
  - `src/lib/api/client.ts` (browser): base `/api`, `credentials: 'include'`; on 401 it silently
    `POST /auth/refresh` once and retries; typed `ApiError`.
  - `src/lib/api/server.ts` (SSR): `apiUrl()` — uses `API_INTERNAL_URL` (direct to
    `api-gateway:8000` inside the cluster) when set, otherwise the `/api` ingress path.
- Dev: `vite.config.ts` proxies `/api/*` to the gateway with special rules for auth redirects,
  WebSockets, and code-server paths.

### 6.2 Auth flow (cookie-based; the browser never sees tokens)

1. Email+password pages call `POST /api/auth/login` (Keycloak direct grant via the gateway);
   the "Sign in as admin" SSO button navigates to `/api/auth/login` (full OIDC redirect w/ PKCE).
2. The gateway sets HttpOnly cookies. The root `+layout.server.ts` resolves the session on every
   SSR request via `GET /auth/me`, transparently refreshing with `POST /auth/refresh` and
   re-setting cookies when the access token expired.
3. A 4-minute keepalive refresh in `+layout.svelte` keeps the terminal WebSocket alive
   (access tokens last ~5 min).
4. Dev-only `/dev-login?as=admin|user` does a resource-owner grant straight to Keycloak
   (404s in production).

### 6.3 Routes & RBAC

| Route | Who | Backs onto |
|---|---|---|
| `/dashboard` | any user | balance, pods, recent transactions, usage summary |
| `/pods`, `/pods/[id]` | owner | launch panel (plan + image template), pod detail: multi-tab **xterm.js terminal** (WS `/api/pods/{id}/terminal`, resize + ping + backoff-reconnect), live **SSE metrics** (`EventSource /api/pods/{id}/metrics`), file browser, usage charts, SSH command display (uses `NODE_IP` env), **"Open VS Code"** link → `/{userId}/code/{podId}/` (ingress-routed code-server) |
| `/credits` | any user | balance + full ledger history |
| `/settings/ssh-keys` | any user | SSH key CRUD |
| `/teacher` | `professor` only (redirects otherwise) | student list + allocate-credits dialog bounded by teacher balance |
| `/admin` | `admin` only (redirects otherwise) | stats, users (role changes, credit grants), teacher-request approve/reject, active VMs, node capacity, audit log |
| `/login`, `/signup`, `/verify-email`, `/forgot-password` | public | auth flows incl. 2-step signup with email code |

Sidebar nav is role-gated (`Sidebar.svelte`): teachers see only "Teaching", admins see "Admin" —
matching commit `a6a9c48` (RBAC fix). Self-demotion is also blocked in the admin UI.

---

## 7. Event Backbone — NATS Subjects (verified end-to-end)

**Important:** despite the NATS *server* running with `--jetstream` and code comments mentioning
JetStream, **both services use core NATS pub/sub** (fire-and-forget, no persistence/redelivery).
Reliability instead comes from the deterministic `tx_id` idempotency + reconcile-on-restart.

| Subject | Publisher | Consumer | Payload / effect |
|---|---|---|---|
| `billing.deducted` | Orchestrator ticker (60 s/pod) | Gateway `billing_consumer` (queue `billing-workers`) | `{pod_id, amount, user_id, tx_id, seq}` → `deduct_credits()` on the ledger |
| `billing.exhausted` | Gateway (when deduction fails on insufficient balance) | **Both**: Orchestrator (`events/handlers.go` → kill the pod) and Gateway itself (marks `pod_sessions.state=terminated`) | `{pod_id, user_id}` |
| `metrics.<k8sPodName>` | Orchestrator (every 5 s per running pod) | Gateway: `metrics_consumer` (queue `metrics-workers` → TimescaleDB hypertable) **and** per-request SSE subscriptions in `GET /pods/{id}/metrics` | `{pod_id, user_id, cpu_percent, memory_used_bytes, memory_limit_bytes}` |
| `pod.created`, `pod.stopped`, `pod.failed` | Orchestrator | **Nobody** (published but unconsumed — informational only) | lifecycle events |

---

## 8. End-to-End Workflows

### 8.1 Signup → verified account
`POST /auth/signup` → Keycloak user created (unverified) + `users` row + 6-digit code emailed
(SHA-256-hashed in `email_codes`, 5 attempts, 10-min TTL; logged to console if SMTP unset) →
`POST /auth/verify-email` flips Keycloak `emailVerified` → user can log in. A "teacher" signup
is stored as `student` + `pending_teacher=true`; an admin later approves it in `/admin`
(Requests tab) which promotes the Keycloak+DB role to `professor` and force-logs-out the user.

### 8.2 VM creation
1. User picks a plan/template on `/pods` → `POST /pods/`.
2. Gateway: balance ≥ plan hourly rate? (402) · < 3 running pods? (429) · insert
   `PodSession(state=pending)` · gRPC `CreatePod(user_id, plan, image, cpu, memory, pod_id=UUID)`.
3. Orchestrator: create Pod + NodePort Service (§5.3), transition pending→creating→running,
   publish `pod.created`, **start the billing ticker**, return `PodStatus` with SSH/VS Code
   NodePorts + generated root password.
4. Gateway stores ports/password on the session, returns it; the UI shows
   `ssh root@<node> -p <sshPort>`, the in-browser terminal, and the VS Code link.

### 8.3 Billing loop & auto-termination
Every 60 s per VM: orchestrator publishes `billing.deducted` (idempotent `tx_id`) → gateway
deducts user→system on the double-entry ledger. If the balance is insufficient, the gateway
publishes `billing.exhausted` → the orchestrator stops the ticker and deletes the pod/service;
the gateway's own `billing.exhausted` handler marks the DB session `terminated`. A NATS
redelivery or double-processing cannot double-charge because `tx_id` is the Transfer primary key.

### 8.4 Live metrics
Orchestrator → `metrics.<podName>` every 5 s (source: metrics-server). Two consumers:
(a) the metrics consumer persists samples into the `metrics_samples` hypertable (30-day
retention) which powers the `/usage` history charts; (b) the SSE endpoint
`GET /pods/{id}/metrics` bridges the subject to the browser's `EventSource` for the live gauges.

### 8.5 Interactive access to a VM
- **Browser terminal**: WS `/pods/{id}/terminal` → gateway authenticates the cookie, spawns
  `kubectl port-forward` to the pod, opens an `asyncssh` session as `root` using the stored
  per-pod password, and bridges bytes to xterm.js.
- **VS Code**: ingress routes `/{userId}/code/{podId}/…` → gateway's `vscode` reverse proxy
  (HTTP + WS) → port-forward → code-server on pod:8080 (code-server itself runs `auth: none`;
  the JWT cookie + ownership check at the proxy is the gate).
- **Native SSH**: directly to `<node-ip>:<NodePort>` (allowed by the `user-vm-allow-external-ssh`
  Cilium policy).
- **Files**: `/files/{podId}/…` endpoints shell out to SCP (`sshpass`) over a port-forward.

### 8.6 Credits & teaching
Admins grant credits from the system account (`POST /credits/allocate`); professors transfer from
their own balance to students (advisory-locked, balance-checked). The `/teacher` console lists
students and drives these transfers; every movement is a balanced pair of ledger entries.

### 8.7 Crash recovery
Gateway restart: stateless — consumers resubscribe (queue groups prevent duplicate processing
across its 4 uvicorn workers). Orchestrator restart: `Reconcile` rebuilds all pod state from the
cluster (labels, service NodePorts, password annotation) and **restarts billing tickers**, so
running VMs keep billing. Note the orchestrator must be a **single replica** — leader election
code exists (`internal/leader/election.go`) but is never called, so >1 replica would double-bill.

---

## 9. Deployment

### 9.1 Local development
- `docker compose up -d` → TimescaleDB (host 5433), NATS (`--jetstream`), Keycloak 25 (dev mode,
  admin/admin, backed by the same Postgres).
- `scripts/deploy-local.sh` — full orchestration: readiness waits, dependency installs, Alembic
  migrations, then runs frontend (Vite :5173), gateway (uvicorn --reload :8000) and orchestrator
  natively with PID tracking/cleanup. `make dev`, `make api-dev`, etc. wrap the pieces.
- Proto regeneration: `scripts/generate-proto.sh` (buf if available, else protoc → Python stubs
  into the gateway, Go stubs into `services/orchestrator/api/proto`).

### 9.2 Production (what actually runs)
Everything lives in namespace **`hopper`** on single-node k3s (Cilium CNI), applied in order from
`k8s/deploy/`:

| File | Contents |
|---|---|
| `00-secrets.yaml` | DB creds, Keycloak admin, `hopper-admin` client secret (placeholder in repo — provisioned in-cluster), SMTP |
| `01-infra.yaml` | Postgres (Deployment + 10 Gi PVC), NATS (JetStream on **emptyDir** — ephemeral), Keycloak in production `start` mode (`KC_HOSTNAME=https://hopper.farefin.com`) |
| `02-apps.yaml` | api-gateway (2 workers, full `HOPPER_*` env, `hostAliases` SMTP-relay workaround), orchestrator (+ inline RBAC: pods/exec/portforward/PVC/lease Role, node-reader ClusterRole), frontend. All images `imagePullPolicy: Never` (imported into k3s containerd) |
| `03-ingress.yaml` | nginx: `/` → frontend, `/api/*` → gateway (prefix stripped), `/realms|/resources|/js` → Keycloak (**`/admin` deliberately not exposed**), `/{uuid}/code/{uuid}/…` → gateway vscode proxy. TLS via cert-manager |
| `04-network-policies.yaml` | **Cilium**: default-deny, DNS, platform-internal, ingress-only entry, VM egress to the internet *minus* cluster CIDRs and cloud-metadata IPs (IMDS SSRF defense), external SSH to :22, kube-api access for the orchestrator |
| `05-cert-manager.yaml` | Let's Encrypt staging + prod ClusterIssuers (HTTP-01) |

Keycloak hardening is scripted (`scripts/keycloak-harden.sh`): brute-force protection,
refresh-token rotation, 12-char complexity password policy, PKCE S256, locked redirect URIs,
role scope-mappings + audience mapper.

### 9.3 CI/CD (`.github/workflows/`)
- **`ci.yml`** (push/PR): frontend lint/check/vitest/build · gateway Poetry install + import
  smoke · orchestrator `go vet` + `go test -race` · Testcontainers integration tests · Docker
  build smoke.
- **`publish.yml`**: builds & pushes `ghcr.io/<owner>/hopper-{api-gateway,orchestrator,frontend}:<sha12>`,
  then (gated on `AUTO_DEPLOY_K8S` or manual dispatch) **SSHes into the VPS** and runs
  `scripts/cd/k8s-rollout.sh` (`kubectl set image` + rollout status). Deployment is imperative
  SSH+kubectl — **not** the ArgoCD app in `infrastructure/argocd/` (that's a placeholder).
- **`lint-python.yml`**: Ruff on the gateway.

---

## 10. Testing

| Suite | Location | Status |
|---|---|---|
| Unit (pytest) | `tests/unit/` (~3.9 k lines) | ✅ Substantive — routers, credit service, billing consumer, auth middleware, Keycloak admin, schemas |
| Integration | `tests/integration/` (~2.1 k lines) | ✅ Substantive — **Testcontainers** spins real TimescaleDB + NATS, runs Alembic, truncates between tests; covers all routers |
| E2E | `tests/e2e/` | ✅ Real Playwright specs (auth, authorization, dashboard, pods) — auth-dependent tests self-skip without `E2E_*` credentials |
| Load | `tests/load/class-start.js` | ⚠️ k6 scenario exists (30-VU class start) but has hardcoded test credentials — not runnable as-is |
| Chaos | `tests/chaos/kill-gpu-pod.yaml` | ⚠️ Chaos Mesh stub targeting labels/namespaces that don't exist in the live deploy |

---

## 11. Reality Check — What's Real vs. Aspirational / Dead Code

This repo contains an ambitious documented design (`docs/TECH_STACK.md`, `docs/ARCHITECTURE.md`)
and a leaner reality. Trust the code, not the docs, on these points:

### Documented but NOT actually implemented/deployed
| Claim | Reality |
|---|---|
| "NATS JetStream" messaging | Server runs with `--jetstream`, but **all client code is core NATS** — no streams/consumers/acks. NAK/redelivery code paths in the billing consumer are dead (guarded by `NotJSMessageError`). Idempotent `tx_id` + reconcile is the actual safety net. |
| Teleport SSH gateway | No Teleport anywhere. SSH is plain sshd on NodePorts. |
| Calico network policies | Live policies are **Cilium** (`k8s/deploy/04-…`). The Calico file in `k8s/network-policies/` is unused and conflicts. |
| gVisor/runsc sandboxing | Only an Ansible TODO; the referenced template file doesn't exist. |
| GPU Operator / KAI Scheduler / Kueue | Helm values / CRDs exist (`k8s/gpu-operator`, `k8s/kai-scheduler`, `k8s/kueue`) but target a nonexistent `hopper-pods` namespace and nothing installs them. No GPU support exists in the orchestrator either (no GPU resource requests). |
| ArgoCD GitOps | Placeholder Application (`your-org/hopper.git`, wrong namespace). Real deploys are SSH + `kubectl set image`. |
| Pulumi IaC | Empty skeleton, zero resources. |
| Prometheus/Grafana/Loki stack | Config files only (`observability/`); nothing in the repo installs them, and DCGM metrics depend on the un-deployed GPU operator. |
| Multi-node RKE2/kubeadm | Actual: single-node k3s. |
| `k8s/base/` namespaces (`hopper-system`/`hopper-pods`) + RBAC | Unused; the live deploy uses namespace `hopper` with inline RBAC. |
| README's `pod.created/stopped/failed` event consumers | Published by the orchestrator, consumed by nobody. |

### Dead / stub code worth knowing about
- `services/api-gateway/app/routers/terminal.py` — a second (kubectl-exec) terminal implementation, **never registered** in `main.py`; the live one is in `pods.py`.
- `hopper.billing.v1.BillingService` gRPC — registered on the orchestrator but all handlers are placeholders; generated Python stubs are unused by the gateway.
- `GetPodStatus`, `StreamMetrics`, `WatchPodStatus` RPCs — implemented, never called.
- `internal/leader/election.go` — complete Lease-based leader election, never invoked ⇒ orchestrator must stay single-replica or billing double-fires.
- `internal/billing/ticker.go::StopAndProrate` — final prorated charge implemented, never called (last partial minute is unbilled).
- Proto `CreatePodRequest.disk` + the PVC/`ws-<pod>` machinery — not plumbed through `CreatePod`, so VMs have no persistent `/workspace` in practice.
- `app/services/k8s_pod_lookup.py` — direct pod-IP resolution (NetworkPolicy-friendly), unused; live code paths use `kubectl port-forward`.
- Stub endpoints: `PUT /settings/vscode` (no persistence), `GET /admin/courses` (returns `[]`).
- `frontend/src/lib/stores/auth.ts` — auth stores exist but layout `data` is the real source of truth.
- Minor: gateway config defaults DB port 5433 (host mapping) while README says 5432; structlog is hardwired to console rendering.

---

## 12. Quick "Where Do I Look?" Index

| I want to understand… | Read |
|---|---|
| App boot & consumers | `services/api-gateway/app/main.py` |
| Login/OIDC/cookies | `services/api-gateway/app/routers/auth.py`, `app/middleware/auth.py` |
| VM create/terminate API | `services/api-gateway/app/routers/pods.py` |
| Credit ledger | `services/api-gateway/app/services/credit_service.py`, `app/models/credit_ledger.py` |
| Billing consumption | `services/api-gateway/app/services/billing_consumer.py` |
| Orchestrator boot | `services/orchestrator/cmd/orchestrator/main.go` |
| Pod spec / security / NodePorts | `services/orchestrator/internal/k8s/pod.go` |
| Billing ticker | `services/orchestrator/internal/billing/ticker.go` |
| Crash recovery / watch | `services/orchestrator/internal/k8s/watcher.go` |
| NATS subjects | `services/orchestrator/internal/events/nats.go` |
| gRPC contract | `proto/hopper/pod/v1/pod.proto` |
| Frontend session handling | `frontend/src/routes/+layout.server.ts`, `frontend/src/lib/api/client.ts` |
| Browser terminal | `frontend/src/lib/components/Terminal.svelte` + gateway `pods.py` WS |
| Production manifests | `k8s/deploy/00–05*.yaml` |
| Deploy pipeline | `.github/workflows/publish.yml`, `scripts/cd/k8s-rollout.sh` |
| VM image | `images/hopper-vm/Dockerfile` + `config/` |
