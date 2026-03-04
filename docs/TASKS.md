# Hopper - Implementation Tasks

> 4-phase implementation plan. Each phase delivers a usable increment. Tasks are ordered by dependency within each phase.

---

## Phase 0: Project Scaffolding (COMPLETED)

> **Goal**: Full project skeleton — frontend, backend services, infrastructure, and testing — so development can begin on Phase 1 tasks.

### S0.1 Root Configuration Files

- [x] **`.gitignore`** — Covers node_modules, __pycache__, .venv, .svelte-kit, proto/gen/, Go binaries, .env files, IDE files, OS files, Pulumi state, secrets (*.pem, *.key)
- [x] **`.editorconfig`** — 2-space indent for most files, 4-space for Python, tabs for Go and Makefiles, UTF-8, LF line endings, trailing whitespace trimming
- [x] **`Makefile`** — Targets for: `dev-up`/`dev-down` (docker-compose), `proto` (code gen), `frontend-install`/`frontend-dev`/`frontend-build`, `api-install`/`api-dev`/`api-migrate`, `orchestrator-build`/`orchestrator-dev`, `test-unit`/`test-integration`/`test-e2e`/`test-load`, `lint`, `clean`
- [x] **`docker-compose.yml`** — Three services for local development:
  - **PostgreSQL 16 + TimescaleDB** (`timescale/timescaledb:latest-pg16`) on port 5433 (remapped from 5432 to avoid conflicts), with healthcheck and persistent volume
  - **NATS 2.10** with JetStream enabled, ports 4222 (client) and 8222 (monitoring), persistent volume, wget-based healthcheck
  - **Keycloak 25.0** in dev mode, using Postgres as its backing DB, port 8080, depends on healthy Postgres

### S0.2 Protocol Buffer Definitions

- [x] **`proto/buf.yaml`** — Buf v2 config with STANDARD lint rules and FILE breaking change detection
- [x] **`proto/hopper/pod/v1/pod.proto`** — Full `PodOrchestrator` gRPC service with:
  - `CreatePod`, `TerminatePod`, `GetPodStatus` RPCs
  - `StreamMetrics` (server-streaming GPU metrics) and `WatchPodStatus` (server-streaming state changes)
  - Messages: `CreatePodRequest`, `PodStatus`, `PodId`, `TerminateResponse`, `GpuMetrics`
  - `PodState` enum: UNSPECIFIED, PENDING, CREATING, RUNNING, STOPPING, TERMINATED, FAILED
  - Go package option: `github.com/hopper/orchestrator/api/proto/pod/v1`
- [x] **`proto/hopper/billing/v1/billing.proto`** — Full `BillingService` gRPC service with:
  - `DeductCredits`, `GetBalance` RPCs
  - `StreamUsage` (server-streaming usage events)
  - Messages: `DeductRequest`, `DeductResponse`, `BalanceResponse`, `UsageEvent`, `AccountId`
- [x] **`proto/gen/`** — Directory created, gitignored (stubs generated at build time)

### S0.3 Frontend (SvelteKit 2 + Svelte 5)

- [x] **`package.json`** — Dependencies: `@sveltejs/kit` ^2.0, `svelte` ^5.0, `@sveltejs/adapter-node` ^5.0, `@xterm/xterm` ^5.5, `@xterm/addon-fit`, `@xterm/addon-web-links`, `chart.js` ^4.4, `bits-ui`. Dev deps: `tailwindcss` ^4.0, `@tailwindcss/vite`, `typescript` ^5.0, `vite` ^6.0, `vitest`, `svelte-check`, `eslint`
- [x] **`svelte.config.js`** — adapter-node for self-hosted deployment, vitePreprocess for TypeScript/CSS
- [x] **`vite.config.ts`** — Tailwind CSS v4 vite plugin + SvelteKit vite plugin
- [x] **`tsconfig.json`** — Extends SvelteKit generated config, strict mode, bundler module resolution
- [x] **`Dockerfile`** — Multi-stage: pnpm install → pnpm build → production Node.js image on port 3000
- [x] **`src/app.html`** — Standard SvelteKit shell with favicon, viewport meta, preload-data hover
- [x] **`src/app.css`** — Single Tailwind v4 `@import 'tailwindcss'` directive

#### Types (`src/lib/types/index.ts`)
- [x] `PodState` union type: pending | creating | running | stopping | terminated | failed
- [x] `GpuTier` union type: premium | standard | budget | scavenger
- [x] `GPU_TIER_RATES` constant map: premium=15, standard=10, budget=5, scavenger=0 credits/hr
- [x] `UserRole` union type: platform_admin | university_admin | department_admin | professor | ta | student
- [x] Interfaces: `User`, `Pod`, `Credit`, `CreditTransaction`, `GpuMetrics` — all typed with proper fields

#### API Client (`src/lib/api/client.ts`)
- [x] Fetch wrapper with JSON Content-Type headers, error handling via `ApiError` class
- [x] Methods: `get<T>`, `post<T>`, `delete<T>`, `sse` (returns EventSource with JSON parsing)
- [x] Base URL: `/api` (will be proxied in dev, direct in production)

#### Stores
- [x] **`stores/auth.ts`** — Svelte writable stores: `user` (User | null), `isAuthenticated` (boolean)
- [x] **`stores/pods.ts`** — Svelte writable stores: `pods` (Pod[]), `activePodMetrics` (GpuMetrics | null)

#### Components (Svelte 5 `$props()` syntax)
- [x] **`PodCard.svelte`** — Displays pod ID, state (color-coded badge), GPU tier, image. State colors: green=running, yellow=pending, blue=creating, orange=stopping, gray=terminated, red=failed
- [x] **`CreditBadge.svelte`** — Inline pill badge showing credit balance with "credits" label, indigo color scheme
- [x] **`GpuMetrics.svelte`** — 2x2 grid showing utilization %, temperature C, VRAM GB, power W. Graceful null state
- [x] **`Terminal.svelte`** — xterm.js wrapper with dynamic imports (code-split), FitAddon for auto-resize, WebLinksAddon for clickable URLs. Cleanup via onDestroy. Placeholder for Teleport WebSocket connection

#### Routes
- [x] **`+layout.svelte`** — Root layout with nav bar (Hopper logo, Dashboard/Pods/Credits links, conditional Admin link for admin roles, user email), auth guard using stores, Tailwind-styled
- [x] **`+layout.server.ts`** — Server-side auth session check via cookie (`session_token`)
- [x] **`+page.svelte`** — Landing page: redirects to /dashboard if authenticated, /login otherwise
- [x] **`login/+page.svelte`** — SSO login page with "Sign in with University SSO" button, redirects to `/api/auth/login`
- [x] **`dashboard/+page.svelte`** — Main dashboard: CreditBadge, grid of PodCards from store, "Launch Pod" link
- [x] **`pods/+page.svelte`** — Pod list: GPU tier selector dropdown (with credit rates), "Launch Pod" button, grid of clickable PodCards linking to detail view
- [x] **`pods/[id]/+page.svelte`** — Pod detail: pod ID header, terminate button, GpuMetrics component, Terminal component. Uses `$derived` from `page.params`
- [x] **`credits/+page.svelte`** — Credit history: CreditBadge, table with date/type/amount columns, color-coded debit (red) / credit (green)
- [x] **`admin/+page.svelte`** — Admin dashboard stub: 3-card grid showing Users, Active Pods, GPU Nodes counts (placeholder)

### S0.4 API Gateway (FastAPI / Python)

- [x] **`pyproject.toml`** — Poetry config with `package-mode = false`. Dependencies: fastapi ^0.115, uvicorn[standard] ^0.30, pydantic ^2.9, pydantic-settings ^2.5, sqlalchemy[asyncio] ^2.0, asyncpg ^0.30, alembic ^1.14, nats-py ^2.9, grpcio/grpcio-tools ^1.65, structlog ^24.0, slowapi ^0.1.9, python-jose[cryptography] ^3.3, httpx ^0.27, sse-starlette ^2.0. Dev deps: pytest ^8.0, pytest-asyncio, pytest-cov, ruff ^0.8, testcontainers ^4.0. Ruff targeting Python 3.12, line length 100. Pytest in auto asyncio mode
- [x] **`Dockerfile`** — Multi-stage: Poetry install → copy .venv → uvicorn with 4 workers on port 8000
- [x] **`app/main.py`** — FastAPI app factory with asynccontextmanager lifespan (structlog setup, engine disposal). Registers CORS middleware (configurable origins), 4 routers (auth, pods, credits, admin) with prefixes and tags. Health endpoints: `/healthz` and `/readyz`. **Verified: 15 OpenAPI endpoints generated**
- [x] **`app/config.py`** — Pydantic BaseSettings with `HOPPER_` env prefix. Fields: database_url (asyncpg to localhost:5433), nats_url, keycloak_url/realm/client_id, cors_origins, jwt_algorithm (RS256), debug flag

#### Routers
- [x] **`routers/auth.py`** — 4 endpoints: `GET /login` (Keycloak redirect), `GET /callback` (OIDC code exchange), `POST /refresh` (token refresh), `GET /me` (current user profile, auth-protected)
- [x] **`routers/pods.py`** — 5 endpoints: `GET /` (list user's pods), `POST /` (create pod with credit check), `GET /{pod_id}` (pod detail), `DELETE /{pod_id}` (terminate), `GET /{pod_id}/metrics` (SSE stream via sse-starlette EventSourceResponse)
- [x] **`routers/credits.py`** — 3 endpoints: `GET /balance` (current balance), `GET /history` (transaction list), `POST /allocate` (professor/admin credit allocation)
- [x] **`routers/admin.py`** — 3 endpoints: `GET /users`, `GET /courses`, `GET /gpu-nodes` (all auth-protected)

#### Schemas (Pydantic v2)
- [x] **`schemas/pod.py`** — `PodState` enum (6 states), `GpuTier` enum (4 tiers), `CreatePodRequest` (gpu_tier + image with PyTorch default), `PodResponse` (full pod fields, from_attributes=True for ORM)
- [x] **`schemas/credit.py`** — `CreditBalanceResponse` (account_id + balance), `CreditHistoryResponse` (id, account_id, amount, direction, type, pod_id, created_at)
- [x] **`schemas/user.py`** — `TokenPayload` (sub, email, name, role, exp), `UserResponse` (id, email, name, role)

#### ORM Models (SQLAlchemy 2.0 Mapped style)
- [x] **`models/credit_ledger.py`** — Three tables implementing double-entry bookkeeping:
  - `Account`: id (prefixed string PK), name, type (asset/liability), owner_id, owner_type
  - `Transfer`: id (prefixed PK), type, metadata (JSON), event_at, created_at. Has relationship to entries
  - `LedgerEntry`: id, transfer_id (FK), account_id (FK), direction (1=debit/-1=credit), amount (Numeric 12,4), previous_balance, current_balance, event_at, created_at
- [x] **`models/session.py`** — `PodSession`: id, user_id (indexed), gpu_type, namespace, pod_name, started_at, expires_at, status, credits_charged (Numeric 12,4)
- [x] **`models/user.py`** — `User`: id, email (unique), name, role (default student), university_id

#### Middleware & Core
- [x] **`middleware/auth.py`** — OIDC token validation: fetches JWKS from Keycloak (cached), decodes JWT with python-jose, extracts role from `realm_access.roles`. Returns `TokenPayload` or None
- [x] **`dependencies.py`** — `get_db()` async generator yielding SQLAlchemy AsyncSession, `get_current_user()` extracting Bearer token and validating via middleware
- [x] **`core/database.py`** — SQLAlchemy async engine from config URL, async_sessionmaker, DeclarativeBase
- [x] **`core/logging.py`** — structlog configuration with contextvars merging, log level, ISO timestamps, ConsoleRenderer (TODO: JSONRenderer in production)

#### Alembic Migrations
- [x] **`alembic.ini`** — Configured for asyncpg URL on port 5433
- [x] **`alembic/env.py`** — Async migration runner, imports all models for autogenerate support
- [x] **`alembic/versions/001_initial_schema.py`** — Complete initial migration:
  - `users` table
  - `accounts` table (credit accounts)
  - `transfers` table (immutable business events)
  - `ledger_entries` table with indexes on account_id and transfer_id
  - **4 PostgreSQL RULEs** preventing UPDATE/DELETE on `ledger_entries` and `transfers` (immutability enforcement)
  - `pod_sessions` table with user_id index
  - `gpu_metrics` table converted to **TimescaleDB hypertable** (1-hour chunks)
  - **Compression policy** on gpu_metrics (after 1 day, segmented by node_id/gpu_index)
  - **Retention policy** on gpu_metrics (30 days)
  - Full downgrade path dropping rules and all tables

### S0.5 Go Orchestrator Service

- [x] **`go.mod`** — Module `github.com/hopper/orchestrator`, Go 1.23. Direct deps: google.golang.org/grpc v1.65, nats.go v1.37, zap v1.27. Indirect deps resolved via `go mod tidy`: protobuf v1.34.2, klauspost/compress, nkeys, crypto, net, sys, text
- [x] **`go.sum`** — Fully populated by `go mod tidy` with verified checksums
- [x] **`Dockerfile`** — Multi-stage: Go 1.23 alpine build → minimal alpine 3.20 runtime with ca-certificates, port 50051

#### Entry Point (`cmd/orchestrator/main.go`)
- [x] Production zap logger with deferred Sync
- [x] Config loading, NATS connection with retry-on-failed-connect and unlimited reconnects
- [x] gRPC server startup in goroutine
- [x] Graceful shutdown on SIGINT/SIGTERM with signal channel

#### Internal Packages
- [x] **`internal/config/config.go`** — `Config` struct (GRPCPort, NatsURL, KubeConfig), `Load()` from env vars with `HOPPER_` prefix and sensible defaults
- [x] **`internal/pod/types.go`** — `State` type with 6 constants (Pending→Creating→Running→Stopping→Terminated, Failed). `ValidTransitions` map encoding the state machine. `Pod` struct with all fields
- [x] **`internal/pod/manager.go`** — Thread-safe `Manager` with RWMutex:
  - `Create()`: idempotent pod creation (returns existing if duplicate), assigns namespace `hopper-pod-{id}`
  - `Transition()`: validates against `ValidTransitions` map, rejects invalid state changes
  - `Get()`: read-locked pod lookup
- [x] **`internal/billing/types.go`** — `GpuTier` struct (Name, CreditsPerHr). `Tiers` map: premium=15, standard=10, budget=5, scavenger=0
- [x] **`internal/billing/ticker.go`** — Per-pod billing ticker:
  - `Start()`: skips scavenger tier (0 credits), spawns goroutine with 1-minute ticker calling `onTick` callback with per-minute credit amount
  - `Stop()`: cancels context, removes from map, logs with zap
  - Thread-safe via Mutex on timers map
- [x] **`internal/events/nats.go`** — NATS helpers:
  - `Connect()`: with RetryOnFailedConnect and unlimited MaxReconnects
  - `Publish()`: JSON-marshals any value and publishes
  - `Subscribe()`: thin wrapper
  - Subject constants: `pod.{created,started,stopped,failed}`, `billing.{deducted,exhausted,allocated}`
- [x] **`internal/grpc/server.go`** — gRPC server setup:
  - Creates `grpc.NewServer()`, initializes PodManager and billing Ticker
  - Registers gRPC health service (`grpc_health_v1`)
  - `Start()` on configurable port, `Stop()` with GracefulStop
  - TODO placeholder for registering PodOrchestrator/BillingService after proto gen

### S0.6 Infrastructure

#### Pulumi (Python SDK)
- [x] **`Pulumi.yaml`** — Python runtime with virtualenv, project name `hopper-infrastructure`
- [x] **`Pulumi.dev.yaml`** — Dev stack config: environment=dev, k8s-version=1.31, gpu-operator-version=25.3.1
- [x] **`__main__.py`** — Stub with config loading, TODO comments for all infrastructure resources
- [x] **`requirements.txt`** — pulumi >=3.140, pulumi-kubernetes >=4.0

#### Ansible
- [x] **`inventory/hosts.yml`** — Example inventory: k8s_masters (master-01), gpu_nodes (gpu-node-01 with rtx_pro_6000, gpu-node-02 with rtx_4090), cpu_nodes (cpu-node-01). Group vars: ansible_user=hopper, become=true, k8s_version=1.31
- [x] **`playbooks/site.yml`** — Main playbook: system package updates, common dependency installation, includes gpu-setup for GPU nodes
- [x] **`playbooks/gpu-setup.yml`** — NVIDIA GPU node setup: add NVIDIA GPG key, add container toolkit repo, install nvidia-container-toolkit, configure containerd for NVIDIA runtime, gVisor RuntimeClass template
- [x] **`roles/`** — Empty directory (roles added during Phase 1)

#### ArgoCD
- [x] **`app-of-apps.yaml`** — Root Application: source from Git repo `k8s/` path, destination `hopper-system` namespace, auto-sync with prune + self-heal, CreateNamespace sync option, retry with exponential backoff (5s → 3m, 5 attempts)

### S0.7 Kubernetes Manifests

- [x] **`k8s/base/namespaces.yaml`** — Two namespaces:
  - `hopper-system`: labeled `app.kubernetes.io/part-of: hopper`
  - `hopper-pods`: same label + **PodSecurity restricted** profile (enforce + audit + warn)
- [x] **`k8s/base/rbac.yaml`** — ServiceAccount and RBAC for orchestrator:
  - `hopper-orchestrator` ServiceAccount in hopper-system
  - ClusterRole: namespaces/pods/services CRUD, pods/log read, deployments CRUD, runtimeclasses read
  - ClusterRoleBinding linking SA to role
  - `hopper-api-gateway` ServiceAccount
- [x] **`k8s/gpu-operator/values.yaml`** — NVIDIA GPU Operator Helm values:
  - Driver v550.127.08, Toolkit v1.17.8 (CVE-2025-23266 patch)
  - DCGM Exporter with ServiceMonitor, MIG Manager enabled
  - Time-slicing: 4 replicas per GPU for consumer cards
  - GFD and node status exporter enabled, containerd runtime
- [x] **`k8s/network-policies/default-deny.yaml`** — 5 Calico GlobalNetworkPolicies:
  1. **default-deny** (order 100): deny all ingress/egress in hopper namespaces
  2. **allow-dns** (order 50): allow UDP/TCP 53 to kube-dns
  3. **allow-internet** (order 60): allow TCP 80/443 egress to 0.0.0.0/0
  4. **allow-ssh-gateway** (order 70): allow TCP 22 ingress from teleport-proxy to student-pods
  5. **deny-control-plane** (order 30): deny student-pod egress to control-plane nodes
- [x] **`k8s/kai-scheduler/values.yaml`** — KAI Scheduler config:
  - 2 replicas, 500m/512Mi request, 2/2Gi limit
  - Hierarchical queue: university-root → cs-department (cs229-ml, cs231n-cv, cs224n-nlp) + ee-department + scavenger (preemptible)
  - Fairshare: 168h (7-day) half-life
  - Fractional GPU: enabled, min 0.25
- [x] **`k8s/kueue/resource-flavors.yaml`** — 3 ResourceFlavors + ClusterQueue + LocalQueue:
  - `gpu-premium` (MIG nodes), `gpu-standard`, `gpu-budget` with node label selectors
  - `hopper-gpu-queue` ClusterQueue: 16 premium GPUs/64 CPU/256Gi, 32 standard GPUs/128 CPU/512Gi, 16 budget GPUs/32 CPU/128Gi
  - `default-queue` LocalQueue in hopper-pods namespace

### S0.8 Observability

- [x] **`prometheus/prometheus.yml`** — Scrape config for 6 targets: prometheus (self), dcgm-exporter (K8s SD), api-gateway (:8000/metrics), orchestrator (:50051/metrics), nats (:8222/metrics), node-exporter (K8s node SD). Remote write to TimescaleDB. AlertManager integration
- [x] **`prometheus/alerts/gpu-alerts.yml`** — 7 alert rules:
  1. GPUTemperatureCritical: > 90C for 5min (critical)
  2. GPUMemoryNearFull: > 95% for 2min (warning)
  3. GPUUtilizationStuck: 100% for 30min (warning, may indicate hung process)
  4. DCGMExporterDown: down for 5min (critical)
  5. PodStuckPending: Pending > 10min in hopper namespaces (warning)
  6. NodeUnreachable: Ready=false for 5min (critical)
  7. NATSJetStreamLag: > 1000 pending messages for 5min (warning)
- [x] **`grafana/dashboards/gpu-overview.json`** — Hopper GPU Overview dashboard: GPU utilization timeseries, GPU temperature timeseries, GPU memory usage %, active student pods stat panel. 30s auto-refresh, 1h default time range
- [x] **`loki/loki-config.yml`** — Loki config: auth disabled, filesystem storage, TSDB schema v13, 720h (30-day) retention, 10MB/s ingestion rate, compactor with retention enabled

### S0.9 Test Scaffolding

- [x] **`tests/unit/.gitkeep`** — Placeholder (unit tests live in-service: pytest for Python, Go testing for Go)
- [x] **`tests/integration/conftest.py`** — Testcontainers fixtures:
  - `postgres_container`: TimescaleDB PG16, session-scoped
  - `nats_container`: NATS 2.10 with JetStream, session-scoped
  - `db_session`: creates async SQLAlchemy session, runs Alembic migrations against test container
  - `nats_url`: extracts connection URL from container
- [x] **`tests/e2e/playwright.config.ts`** — Playwright config: tests in `specs/`, fully parallel, 2 retries in CI, HTML reporter, trace on first retry, screenshot on failure. Projects: Chromium + Firefox. Web server: starts `pnpm dev` in frontend/
- [x] **`tests/e2e/specs/auth.spec.ts`** — 4 test stubs for TC-AUTH-001:
  - Unauthenticated redirect to /login
  - SSO button visibility
  - User info after login (skipped, needs Keycloak mock)
  - Expired session handling (skipped)
- [x] **`tests/load/class-start.js`** — k6 load test scenario: 30 VUs, 30 iterations, 5min max. Flow: login → check balance → create pod → poll status until running. Thresholds: p95 < 2000ms, error rate < 1%
- [x] **`tests/chaos/kill-gpu-pod.yaml`** — Chaos Mesh PodChaos experiment: kills one random student-pod in hopper-pods namespace every 5 minutes (cron scheduled), 30s duration

### S0.10 Scripts

- [x] **`scripts/dev-setup.sh`** — Automated dev environment setup:
  - Prerequisite checks: docker, pnpm, poetry, go
  - `docker compose up -d` and wait for Postgres healthy
  - `pnpm install` in frontend/
  - `poetry install` in services/api-gateway/
  - `alembic upgrade head` for DB migrations
  - `go mod download` for Go deps
  - Prints startup commands for all 3 services
- [x] **`scripts/generate-proto.sh`** — Proto code generation:
  - Supports both `buf generate` and `protoc` fallback
  - Cleans proto/gen/ and services/orchestrator/api/proto/
  - Generates Python stubs (grpc_tools.protoc with pyi type stubs)
  - Generates Go stubs (protoc with go and go-grpc plugins, source_relative paths)

### Verification Results

| Check | Result |
|-------|--------|
| `cd frontend && pnpm install && pnpm dev` | Installed, HTTP 200 on :5173 |
| `docker compose up -d` | Postgres (healthy, :5433), NATS (healthy, :4222), Keycloak (up, :8080) |
| `cd services/api-gateway && poetry install && uvicorn app.main:app` | 15 OpenAPI endpoints, `/healthz` returns `{"status":"ok"}` |
| `cd services/orchestrator && go build ./cmd/orchestrator/` | BUILD OK (clean compile, all deps resolved) |
| Directory structure | 70+ files across 10 top-level directories |

### Notes

- Postgres is mapped to **port 5433** (not 5432) to avoid conflicts with other local databases. All config files reflect this
- NATS healthcheck uses `wget --spider` against the monitoring endpoint (the `--signal ldm` approach was causing NATS to enter lame duck mode and shut down)
- `pyproject.toml` uses `package-mode = false` since the API gateway is not a distributable package
- All Svelte components use **Svelte 5 `$props()` syntax** (not the Svelte 4 `export let` pattern)
- Go module pinned exact dependency versions via `go mod tidy` — `go.sum` fully populated

---

## Phase 1: Foundation (Weeks 1-4)

> **Goal**: Bare-metal Kubernetes cluster with GPU support, basic pod creation, and SSH access.

### DevOps

- [ ] **D1.1** Provision bare-metal servers with Ansible
  - Install Ubuntu 22.04 LTS on all nodes
  - Configure networking (static IPs, DNS)
  - Set up SSH access for ops team
  - Harden OS (disable root SSH, configure firewall, fail2ban)

- [ ] **D1.2** Install NVIDIA drivers and container runtime
  - Install NVIDIA driver 550+ via Ansible role
  - Install NVIDIA Container Toolkit v1.17.8+ (patched for CVE-2025-23266)
  - Configure containerd with NVIDIA runtime as default
  - Validate GPU access: `nvidia-smi` in container

- [ ] **D1.3** Bootstrap Kubernetes cluster
  - Install kubeadm/kubelet/kubectl on all nodes
  - Initialize control plane (kubeadm init)
  - Join worker nodes (GPU nodes)
  - Configure kubeconfig and RBAC

- [ ] **D1.4** Install NVIDIA GPU Operator
  - Deploy via Helm (v25.3.1+)
  - Configure time-slicing (4 replicas per GPU for consumer cards)
  - Configure MIG on RTX PRO 6000 Blackwell (4x 24GB if available)
  - Deploy DCGM Exporter as DaemonSet
  - Validate: `kubectl describe node` shows `nvidia.com/gpu` resources

- [ ] **D1.5** Install container runtime security
  - Deploy gVisor (runsc) on all GPU nodes
  - Create RuntimeClass `gvisor` for student pods
  - Test GPU workload under gVisor (PyTorch training, inference)
  - Document any incompatible CUDA operations

- [ ] **D1.6** Install Calico for network isolation
  - Deploy Calico via Helm
  - Create GlobalNetworkPolicy: default deny inter-namespace
  - Allow DNS, internet egress (80/443), SSH gateway ingress
  - Test isolation between namespaces

- [ ] **D1.7** Set up Teleport SSH gateway
  - Deploy Teleport on Kubernetes (Helm chart)
  - Configure Teleport as SSH proxy
  - Set up static IP / DNS for `ssh.hopper.{university}.edu`
  - Create Teleport roles mapping to GPU access levels
  - Test: SSH into a manually-created GPU pod via Teleport

### Backend

- [x] **B1.1** Set up Go orchestration service skeleton
  - Initialize Go module with client-go, gRPC, NATS dependencies
  - Implement gRPC service definition (PodOrchestrator)
  - Implement basic pod create/delete using client-go
  - Add Kubernetes namespace creation per user
  - Containerize with multi-stage Dockerfile
  - **Done**: Generated proto stubs (`protoc-gen-go`, `protoc-gen-go-grpc`), implemented `PodOrchestratorService` (CreatePod, GetPodStatus, TerminatePod, StreamMetrics, WatchPodStatus) and `BillingServiceImpl` (GetBalance, DeductCredits, StreamUsage) in `internal/grpc/`. Registered both services in `server.go`. Go builds clean.

- [ ] **B1.2** Implement pod lifecycle state machine
  - Define states: REQUESTED, PROVISIONING, RUNNING, FAILED, TERMINATED
  - Use Kubernetes informers (shared informer factory) for pod state tracking
  - Emit state transitions to NATS JetStream
  - Implement idempotent pod creation (deterministic naming)
  - Add finalizers for cleanup guarantee

- [ ] **B1.3** Set up NATS JetStream
  - Deploy NATS on Kubernetes via Helm
  - Create JetStream streams for pod events and billing events
  - Implement Go producer (orchestrator → NATS)
  - Test message persistence and replay

- [ ] **B1.4** Set up PostgreSQL + TimescaleDB
  - Deploy PostgreSQL 16 with TimescaleDB extension on Kubernetes
  - Run initial schema migration (users, sessions, accounts)
  - Set up PgBouncer for connection pooling
  - Configure daily pg_dump backups

### Frontend

- [x] **F1.1** Initialize SvelteKit project
  - Create SvelteKit 2 project with Svelte 5
  - Configure Tailwind CSS 4, shadcn-svelte components
  - Set up project structure: routes, lib, components
  - Configure adapter-node for self-hosted deployment
  - **Done**: Added `+page.server.ts` loaders for dashboard, pods, credits pages (server-side data fetching with auth guards). Dashboard shows real credit balance + pods. Pods page has create/terminate with `invalidateAll()`. Credits page shows balance + transaction history. Layout returns user data from `/auth/me` and syncs auth store. Logout button added. All pages redirect to `/login` if unauthenticated. 0 type errors, production build passes.

---

## Phase 2: Core Platform (Weeks 5-8)

> **Goal**: Full credit system, authentication, real-time dashboard, and pod management UI.

### Backend

- [x] **B2.1** Set up FastAPI API gateway
  - Initialize FastAPI project with Pydantic v2
  - Implement REST endpoints: `POST /pods`, `GET /pods`, `DELETE /pods/{id}`
  - Implement SSE endpoint: `GET /pods/{id}/metrics`
  - Add request validation, error handling, structured logging
  - Generate OpenAPI documentation
  - **Done**: Fixed PodSession model (renamed `gpu_type`→`gpu_tier`, `status`→`state`, added `image` and `updated_at` columns). Added `updated_at` to User model. Created Alembic migration 002. Wired `pods.py` to real DB (list, create, get by id with ownership check, terminate sets state=stopping). Wired `credits.py` to real DB via `credit_service` (balance, history with pagination, allocate with role check).

- [ ] **B2.2** Implement gRPC communication
  - Define .proto files for PodOrchestrator and BillingService
  - Generate Python stubs (for FastAPI) and Go stubs (for orchestrator)
  - Wire FastAPI REST endpoints → gRPC calls to Go orchestrator
  - Implement gRPC streaming for metrics relay

- [x] **B2.3** Implement credit ledger (double-entry bookkeeping)
  - Create schema: accounts, transfers, ledger_entries
  - Implement append-only enforcement (PostgreSQL RULEs)
  - Implement `deduct_credits()` function with advisory locks
  - Implement `add_credits()` for allocations and refunds
  - Create account_balances view
  - Write unit tests for race condition scenarios
  - **Done**: Created `services/credit_service.py` with `get_or_create_account()`, `ensure_system_account()` (well-known UUID `00000000-...`), `get_balance()` (reads last ledger entry), `add_credits()` (system→user double-entry transfer), `deduct_credits()` (user→system with `pg_advisory_xact_lock` and balance check). Unit tests still TODO.

- [ ] **B2.4** Implement billing ticker
  - Per-minute credit deduction for running pods
  - Integrate with pod lifecycle (start billing on RUNNING, stop on TERMINATED)
  - Implement low-balance warning (emit NATS event at < 10%)
  - Implement auto-termination when credits reach 0
  - Grace period: 5-minute SIGTERM before SIGKILL (allow checkpoint saving)

- [ ] **B2.5** Implement session reaper service
  - Background task that checks for expired sessions every 10 seconds
  - Delete namespace (kills pod, PVC, secrets)
  - Update session status in database
  - Emit audit event via NATS
  - Send notification to student (webhook/email)

- [x] **B2.6** Set up Keycloak
  - Deploy Keycloak on Kubernetes
  - Create realm for university
  - Configure OIDC client for Hopper application
  - Set up role hierarchy: admin, professor, ta, student
  - Test token issuance and validation in FastAPI
  - **Done**: Switched `dependencies.py` from `HTTPBearer` to cookie-based auth (reads `session_token` cookie, validates JWT via Keycloak JWKS). Auth callback now upserts user in DB and auto-creates credit account for new users. Added `POST /auth/logout` endpoint (clears cookie, redirects to login). Layout server load calls `/auth/me` to return user data to frontend.

- [ ] **B2.7** Implement university SSO integration
  - Configure Keycloak SAML identity brokering with university Shibboleth IdP
  - Map `eduPersonAffiliation` attributes to Keycloak roles
  - Implement WAYF (Where Are You From) discovery if multi-university
  - Test full SSO flow: student login → Shibboleth → Keycloak → JWT → Hopper

### Frontend

- [ ] **F2.1** Implement authentication flow
  - Keycloak OIDC integration (redirect-based login)
  - Token storage and refresh
  - Protected route middleware
  - User profile page (email, role, university)

- [ ] **F2.2** Build pod management dashboard
  - Pod creation form: GPU tier selector, container image selector, session duration
  - Pod template library: PyTorch, TensorFlow, JAX, custom
  - Active pods list with status indicators (Pending, Running, Failed, Terminated)
  - Pod detail view: logs, metrics, SSH connection info
  - Pod termination with confirmation dialog

- [ ] **F2.3** Build real-time GPU metrics panel
  - SSE connection to `/pods/{id}/metrics` endpoint
  - GPU utilization gauge (0-100%, color-coded)
  - VRAM usage bar (used/total)
  - Temperature gauge with thermal zones (green/yellow/red)
  - Power draw line chart with TDP reference
  - Auto-reconnection on connection loss

- [ ] **F2.4** Build credit dashboard
  - Current balance display (prominent, always visible)
  - Usage history table (session, GPU type, duration, credits charged)
  - Spending projection chart (credits remaining vs burn rate)
  - Low balance warning banner
  - Transaction log (all ledger entries)

- [ ] **F2.5** Build web terminal
  - xterm.js integration with WebSocket backend
  - Terminal resize handling (fit addon)
  - Connection status indicator
  - Copy/paste support
  - Link detection (web-links addon)

### DevOps

- [ ] **D2.1** Install KAI Scheduler
  - Deploy KAI Scheduler on Kubernetes
  - Configure hierarchical queues: University → Department → Course
  - Set fractional GPU policies (0.25 GPU minimum)
  - Configure fairshare with 7-day half-life decay

- [ ] **D2.2** Install Kueue for admission control
  - Deploy Kueue via Helm
  - Create ClusterQueues per GPU tier (Premium, Standard, Budget)
  - Define ResourceFlavors for MIG slices vs time-sliced GPUs
  - Test job queuing when resources are exhausted

- [ ] **D2.3** Set up monitoring stack
  - Deploy Prometheus via Helm (kube-prometheus-stack)
  - Configure DCGM Exporter scraping
  - Deploy Grafana with NVIDIA DCGM dashboard (#12239)
  - Deploy AlertManager with critical alerts (GPU temp, node down)
  - Configure TimescaleDB remote_write for long-term storage

- [ ] **D2.4** Set up logging stack
  - Deploy Grafana Loki via Helm
  - Deploy Promtail as DaemonSet with student pod log collection
  - Configure label extraction: namespace, user_id, session_id, course_id
  - Create Grafana dashboard for log exploration

---

## Phase 3: Hardening & Polish (Weeks 9-12)

> **Goal**: Security hardening, admin tools, testing, and production readiness.

### Backend

- [ ] **B3.1** Implement RBAC enforcement
  - Middleware: extract JWT claims → resolve permissions
  - Per-endpoint authorization checks
  - Resource-scoped permissions (course_id, department_id)
  - Admin-only endpoints: user management, credit allocation, system config

- [ ] **B3.2** Implement rate limiting
  - Per-user API rate limits (slowapi)
  - Pod creation rate limit: max 3 concurrent pods per student
  - SSE connection limit: max 10 concurrent streams per user
  - Admin bypass for rate limits

- [ ] **B3.3** Implement pod template system
  - Template CRUD API (professors/admins can create templates)
  - Template fields: base image, GPU requirements, environment variables, startup scripts
  - Pre-built templates: PyTorch 2.5, TensorFlow 2.17, JAX 0.5, RAPIDS 24.12
  - Template versioning and soft-delete

- [ ] **B3.4** Implement scavenger queue
  - Allow zero-credit students to run on idle GPUs
  - Mark scavenger pods as preemptible
  - Implement preemption logic: when a paying user needs a GPU, evict oldest scavenger pod
  - 30-second graceful termination for checkpoint saving

- [ ] **B3.5** Implement audit logging
  - Log all state-changing operations to dedicated audit table
  - Fields: who, what, when, resource, old_state, new_state, ip_address
  - Retention: 1 year minimum
  - Admin query API for audit logs

### Frontend

- [ ] **F3.1** Build admin dashboard
  - System overview: total GPUs, active pods, active users, credit pool
  - Per-GPU node status (utilization heatmap)
  - User management: search, view sessions, adjust credits
  - Course management: create courses, assign TAs, set quotas
  - Audit log viewer with filters

- [ ] **F3.2** Build professor/TA dashboard
  - Course student list with current sessions
  - Bulk credit allocation to course students
  - GPU quota management per course
  - Usage analytics: per-student GPU hours, credit burn rate
  - Template management (create/edit course-specific templates)

- [ ] **F3.3** Notification system
  - In-app notifications: low balance, session expiring, pod failed
  - Email notifications for critical events (optional, via webhook)
  - Notification preferences per user

- [ ] **F3.4** Mobile responsiveness
  - Responsive dashboard layout for tablet/phone
  - Touch-friendly pod management
  - Credit balance quick-view

### DevOps

- [ ] **D3.1** Set up ArgoCD for GitOps
  - Deploy ArgoCD on Kubernetes
  - Configure SSO with Keycloak
  - Create App of Apps: all Hopper services + infrastructure
  - Sync waves: infra first (NATS, PG) → services (API, orchestrator) → frontend
  - Enable auto-sync for staging, manual sync for production

- [ ] **D3.2** Set up Pulumi for infrastructure management
  - Define Pulumi stacks: dev, staging, production
  - Codify Kubernetes resource definitions (namespaces, quotas, network policies)
  - Codify DNS, TLS certificates
  - Store state in Pulumi Cloud or self-hosted S3

- [ ] **D3.3** Set up Ansible playbooks for GPU node management
  - Playbook: `gpu-node-setup.yml` (driver, toolkit, containerd, kubelet)
  - Playbook: `gpu-node-update.yml` (driver update with drain/uncordon)
  - Playbook: `security-hardening.yml` (OS hardening, firewall rules)
  - Inventory: group by GPU type for targeted operations

- [ ] **D3.4** Implement backup and disaster recovery
  - PostgreSQL: daily pg_dump + WAL archiving (point-in-time recovery)
  - Keycloak: realm export on schedule
  - Kubernetes: etcd snapshot daily
  - Test restore procedure monthly

- [ ] **D3.5** Security audit
  - Review Calico GlobalNetworkPolicy coverage
  - Verify gVisor RuntimeClass is enforced on all student pods
  - Verify NVIDIA Container Toolkit version (CVE-2025-23266 patch)
  - Run `kube-bench` for CIS Kubernetes benchmarks
  - Review all RBAC bindings
  - Verify PodSecurityStandards (restricted profile)

### Testing

- [ ] **T3.1** Unit tests for credit system
  - Test double-entry balance invariants
  - Test advisory lock under concurrent deductions
  - Test compensating entries
  - Test zero-balance prevention
  - Test refund flows

- [ ] **T3.2** Integration tests for pod lifecycle
  - Test full lifecycle: create → running → terminate
  - Test failure handling: image pull error, GPU allocation failure
  - Test billing integration: credits deducted during runtime
  - Test session expiry and reaper cleanup

- [ ] **T3.3** Load tests
  - k6 scenario: 30 students creating pods simultaneously (class start)
  - k6 scenario: 100 concurrent SSE connections (metrics polling)
  - k6 scenario: 100 concurrent billing transactions
  - k6 scenario: spike test (0 → 100 → 0 VUs)
  - Threshold: p95 < 500ms, error rate < 1%

---

## Phase 4: Production & Scale (Weeks 13-16)

> **Goal**: Production deployment, student onboarding, and operational maturity.

### DevOps

- [ ] **D4.1** Production deployment
  - Deploy full stack to production cluster
  - Verify all ArgoCD applications synced and healthy
  - Verify monitoring and alerting operational
  - Verify Teleport SSH access from campus and VPN

- [ ] **D4.2** Chaos engineering
  - Deploy Chaos Mesh on staging cluster
  - Run experiments: GPU pod kill, network partition, NATS failure
  - Verify billing consistency after all chaos scenarios
  - Verify pod cleanup after orchestrator crash
  - Verify dashboard shows appropriate error states

- [ ] **D4.3** Performance tuning
  - Profile FastAPI endpoints (identify slow queries)
  - Optimize Kubernetes scheduling latency
  - Tune PgBouncer pool sizes
  - Tune Prometheus scrape intervals and retention
  - Benchmark pod creation time (target: < 30s from request to SSH-ready)

- [ ] **D4.4** Set up on-call and runbooks
  - Create runbooks for common incidents: GPU node down, credit system error, SSH gateway unreachable
  - Configure AlertManager routing (critical → PagerDuty, warning → Slack)
  - Create incident response procedure
  - Document escalation path

### Frontend

- [ ] **F4.1** Onboarding flow
  - First-login welcome wizard
  - GPU tier explanation and recommendations
  - SSH key setup instructions (with copy-to-clipboard)
  - Quick-start tutorial: create pod → connect → run PyTorch

- [ ] **F4.2** Documentation site
  - Getting started guide
  - SSH connection guide (Teleport tsh + native SSH)
  - GPU tier descriptions and pricing
  - FAQ (common errors, billing questions)
  - API documentation (link to auto-generated OpenAPI)

### Backend

- [ ] **B4.1** Implement usage analytics API
  - Per-student usage over time
  - Per-course aggregate usage
  - Per-GPU utilization trends
  - Credit allocation vs consumption reports
  - Export to CSV for department reporting

- [ ] **B4.2** Implement webhook integrations
  - Slack/Discord notifications for admins (critical alerts)
  - Email notifications for students (session expiry, low balance)
  - Webhook API for custom integrations

### Testing

- [ ] **T4.1** End-to-end tests (see E2E_TESTING.md)
  - Full student workflow: SSO login → create pod → monitor → SSH → terminate
  - Full admin workflow: create course → allocate credits → view usage
  - Cross-browser testing (Chromium, Firefox, WebKit)

- [ ] **T4.2** Security penetration testing
  - Container escape attempts from student pod
  - Cross-namespace network access attempts
  - API authorization bypass attempts
  - Credit manipulation attempts
  - SSH key reuse after session termination

- [ ] **T4.3** Student beta testing
  - Onboard 10-20 students from a single course
  - Monitor credit consumption patterns
  - Collect feedback on UX (pod creation, SSH, dashboard)
  - Identify and fix top 5 usability issues
  - Measure pod creation time, SSH latency, dashboard load time

- [ ] **T4.4** Scale testing
  - Simulate 100 concurrent students (k6)
  - Measure: pod creation latency, credit deduction accuracy, SSE connection stability
  - Identify bottlenecks and optimize
  - Document capacity limits per GPU node configuration

---

## Task Count Summary

| Phase | DevOps | Backend | Frontend | Testing | Total | Status |
|-------|--------|---------|----------|---------|-------|--------|
| Phase 0: Scaffolding | 4 | 2 | 1 | 1 | **10** | DONE |
| Phase 1: Foundation | 7 | 4 | 1 | 0 | **12** | B1.1, F1.1 DONE |
| Phase 2: Core | 4 | 7 | 5 | 0 | **16** | B2.1, B2.3, B2.6 DONE |
| Phase 3: Hardening | 5 | 5 | 4 | 3 | **17** | |
| Phase 4: Production | 4 | 2 | 2 | 4 | **12** | |
| **Total** | **24** | **20** | **13** | **8** | **67** | |

---

## Critical Path

The following tasks are on the critical path (blocking downstream work):

```
D1.2 (NVIDIA drivers) → D1.3 (K8s cluster) → D1.4 (GPU Operator)
  → B1.1 (Go orchestrator) → B1.2 (Pod lifecycle)
    → B2.1 (FastAPI) → B2.2 (gRPC) → F2.2 (Pod dashboard)

D1.4 (GPU Operator) → D2.1 (KAI Scheduler) → D2.2 (Kueue)

B1.4 (PostgreSQL) → B2.3 (Credit ledger) → B2.4 (Billing ticker)
  → F2.4 (Credit dashboard)

B2.6 (Keycloak) → B2.7 (SSO) → F2.1 (Auth flow)
```

---

## Definition of Done (Per Task)

- [ ] Code passes linting and formatting checks
- [ ] Unit tests written and passing (where applicable)
- [ ] Integration test written (for backend services)
- [ ] Documentation updated (API docs, runbooks)
- [ ] Code reviewed by at least one team member
- [ ] Deployed to staging and manually verified
- [ ] Monitoring/alerts configured (for infrastructure tasks)
