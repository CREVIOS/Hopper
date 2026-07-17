# Testing Infrastructure Plan

## 1. Current System Overview;p[''''''''''4]

### Main applications and services

- `frontend/`: SvelteKit 2 application for login, dashboard, pods, credits, settings, teacher, and admin flows.
- `services/api-gateway/`: FastAPI application exposing REST endpoints, SSE metrics, WebSocket terminal access, auth flows, and background consumers.
- `services/orchestrator/`: Go gRPC service managing Kubernetes pod lifecycle, billing ticker logic, NATS events, and metrics publishing.
- `tests/mocks/*`: deterministic mock API, mock Kubernetes API, and mock DCGM exporter for isolated E2E and platform tests.
- `observability/`, `k8s/`, and `infrastructure/`: deployment and runtime support assets, not primary apps but important for environment parity.

### Technology stack

- Frontend: SvelteKit, Svelte 5, Vite, Vitest, ESLint, pnpm.
- API: Python 3.12, FastAPI, SQLAlchemy async, Alembic, Poetry, pytest, pytest-cov, Testcontainers.
- Orchestrator: Go 1.23, gRPC, client-go, NATS.
- E2E: Playwright in `tests/e2e`.
- Load: k6 in `tests/load`.
- Infrastructure services: PostgreSQL/TimescaleDB, NATS JetStream, Keycloak, Kubernetes.

### Service dependencies

- API Gateway depends on PostgreSQL, NATS, Keycloak, and the orchestrator gRPC endpoint.
- Orchestrator depends on Kubernetes and NATS.
- Frontend depends on the API Gateway and, in dev, can proxy either to local or deployed backends.
- Auth depends on Keycloak plus optional SMTP-backed email verification and password reset.
- File and terminal flows depend on running user pods and port-forward or NodePort access.

### Important user and system flows

- Signup, email verification, login, refresh, logout.
- Student pod creation, listing, details, metrics, terminal/files access, and termination.
- Credit balance/history and admin or professor allocations.
- Teacher approval and admin role management.
- Background billing deductions from orchestrator to API via NATS.
- Metrics publication from orchestrator to API and browser consumption via SSE.
- Session reaping for expired sessions.

### Components that require testing

- Frontend routes, stores, UI components, auth guards, and API proxy behavior.
- API routers, middleware, schemas, services, DB models, and lifespan tasks.
- Orchestrator lifecycle logic, billing ticker, K8s integration adapters, and event publication.
- Cross-service auth, billing, metrics, and pod lifecycle flows.
- Security and non-functional assets in `tests/security`, `tests/chaos`, and `tests/load`.

## 2. Existing Testing Audit

Observed test inventory:

- Python `pytest --collect-only` from the repo-root test tree: `285 tests collected`.
- Playwright `--list`: `38 tests in 6 files`.
- Go orchestrator black-box tests discoverable with writable `GOCACHE`: `17` named tests.
- Frontend Vitest test files present: `3`.

| Component | Existing test type | Existing framework | Current condition | Missing infrastructure | Risk level |
|---|---|---|---|---|---|
| API Gateway core, routers, middleware, schemas, services | Unit | pytest | Broad real coverage under `tests/unit`; many business rules already exercised | Unit runner paths are inconsistent in local scripts and Make targets | Medium |
| API Gateway with DB, NATS, Keycloak, files, auth | Integration | pytest + Testcontainers | Strong coverage under `tests/integration`; real DB and event-flow tests exist | No dedicated integration-only Docker Compose parity script; coverage policy is not clearly separated by layer | Medium |
| Orchestrator lifecycle and pricing | Black-box/unit-style Go tests | `go test` | Real tests exist in `tests/orchestrator` with fake clients and contract checks | Requires explicit writable `GOCACHE`; service-local `go test ./...` and external test module split can confuse contributors | Medium |
| Frontend stores/types/components | Unit | Vitest | Only 3 test files currently present | No visible browser-component harness, no coverage artifact in CI, low route/component coverage | High |
| Full UI workflows | E2E | Playwright | Real suite exists with auth, guards, pods, dashboard, admin, and seeded workflow coverage | Mostly deterministic mock-backed flows; limited proof against the real API stack and real Keycloak | High |
| Load/performance | Load | k6 | Real scenarios and thresholds exist; scheduled workflow runs smoke-style load job | No environment-specific baselines, no artifact retention, and thresholds are partly assumed rather than capacity-backed | Medium |
| Chaos testing | Chaos/staging validation | Chaos Mesh manifests + shell | Manifests and invariant script exist; scheduled workflow can apply them to staging | No result reporting pipeline, no controlled rollout gate, no local validation path | Medium |
| Security testing | Staging security checks | shell + Python + manifests | Scripts and manifests exist for isolation probes | Not integrated into main CI, depends on staging secrets/tokens, GPU checks optional/manual | High |
| Coverage reporting | Python coverage only | pytest-cov + XML artifact | Unit and integration jobs emit XML coverage | No frontend or Go coverage reports, no combined multi-app coverage view, no enforced thresholds in current CI | High |
| CI/CD automation | GitHub Actions | Actions workflows | CI, lint, publish, and scheduled test-platform workflows exist | Main CI does not enforce agreed coverage thresholds, does not run real end-to-end against the real stack, and does not surface a unified test matrix | High |

## 3. Proposed Testing Architecture

Proposed repository test structure:

```text
tests/
  unit/
    api_gateway/
    frontend/
  integration/
    api_gateway/
    orchestrator/
    contracts/
  e2e/
    specs/
    fixtures/
    helpers/
  load/
  chaos/
  security/
  fixtures/
  factories/
  mocks/
  helpers/
```

Recommended mapping to the current repo:

- Keep `tests/unit`, `tests/integration`, `tests/e2e`, `tests/load`, `tests/chaos`, `tests/security`, `tests/mocks`, and `tests/orchestrator`.
- Add sub-grouping inside `tests/unit` for `api_gateway/` and `frontend/` to make the ownership split obvious.
- Keep orchestrator black-box tests as a separate Go module when they intentionally validate public behavior from outside the service package.
- Add `tests/contracts/` for gRPC, NATS subject, and auth-cookie contract tests that assert stable cross-service payloads.
- Add shared `tests/fixtures/`, `tests/factories/`, and `tests/helpers/` for Python test data and environment bootstrap instead of duplicating builders across files.

Recommended frameworks by layer:

- Frontend unit/component: Vitest. It already exists, matches Vite, and should remain the fast feedback loop for stores, serializers, and route helpers.
- API unit and integration: pytest. It already has broad adoption and works with async code plus Testcontainers.
- Orchestrator unit/integration: native Go `testing` with fake clientsets and explicit external black-box tests in `tests/orchestrator`.
- E2E: Playwright. It already matches the stack and handles auth, SSR pages, and browser flows well.
- Load: k6. It is already present and fits HTTP-heavy student/admin workflows.
- Chaos/security: keep shell/Python/manifest-based staging checks, but formalize them as platform-gate suites instead of ad hoc assets.

## 4. Unit Testing Plan

### Highest-priority API Gateway unit targets

- `app/routers/auth.py`: signup, verification, refresh, logout, direct grant failure, domain restrictions, cookie issuance.
- `app/routers/pods.py`: plan validation, active-pod limits, ownership checks, orchestrator failure mapping, terminal/file access guards.
- `app/routers/credits.py`: allocation permissions, self-allocation rejection, balance/history formatting.
- `app/routers/admin.py`: role changes, teacher approval/rejection, read-only professor access boundaries.
- `app/services/credit_service.py`: balanced entries, idempotency, insufficient-credit handling, same-user constraints.
- `app/services/session_reaper.py`: expiry filtering, idempotence, already-deleted namespace handling, audit emission.
- `app/services/billing_consumer.py` and `metrics_consumer.py`: malformed event handling, ack/nak behavior, duplicate events, exhausted-credit flow.
- `app/middleware/auth.py` and `audit.py`: JWKS refresh, invalid token behavior, route action mapping, audit scheduling.
- `app/config.py` and `app/main.py`: env parsing, CORS safety, lifespan wiring assumptions.

### Highest-priority orchestrator unit targets

- `internal/pod/manager.go`: lifecycle transitions, idempotent creation, connection detail persistence, terminal-state behavior.
- `internal/billing/ticker.go`: plan pricing, per-minute or prorated behavior, stop semantics, idempotent final billing.
- `internal/k8s/pod.go`: resource limits, service creation, isolation/runtime-class assumptions, cleanup sequencing.
- `internal/events/*`: NATS publication formatting and failure handling.

### Highest-priority frontend unit targets

- `src/lib/stores/auth.ts` and `src/lib/stores/pods.ts`: auth state, session loss, optimistic updates, pod list transformations.
- `src/lib/api/client.ts` and `src/lib/api/server.ts`: cookie forwarding, 401 handling, refresh behavior, request normalization.
- `src/routes/+layout.server.ts`: guarded SSR bootstrap and auth propagation.
- Route server loaders for `dashboard`, `pods`, `credits`, `admin`, `teacher`, `settings`.
- UI components with logic, especially `Terminal.svelte`, `PodFiles.svelte`, `UsageChart.svelte`, and `GpuMetrics.svelte`.

### Dependencies that should be mocked

- Unit tests should mock Keycloak HTTP calls, NATS connections/messages, gRPC orchestrator stubs, SMTP, port-forward subprocesses, and Kubernetes HTTP/client-go calls.
- Frontend unit tests should mock `fetch`, SSE/EventSource, and browser storage or cookie adapters.

### Test-data factories and fixtures required

- User factory with `student`, `professor`, `admin`, and `pending_teacher` variants.
- Account and ledger-entry factories with helper methods for balance chains.
- Pod-session factory covering requested, provisioning, running, failed, terminated, and expired sessions.
- Token payload factory for auth and role combinations.
- Event payload fixtures for `billing.deducted`, `billing.exhausted`, `pod.*`, and `metrics.*`.

### Important cases

- Success, failure, boundary, validation, idempotency, retry, permission, and race-condition cases for all billing and lifecycle paths.
- Email-verification and password-reset edge cases.
- Unsafe path traversal, invalid SSH keys, malformed metrics payloads, stale cookies, and disallowed origins.

### Areas that should not be tested directly

- Third-party library internals.
- Vite/SvelteKit framework behavior already covered upstream.
- Generated protobuf code beyond smoke-level contract compatibility.
- Kubernetes, Keycloak, NATS, or PostgreSQL internals; test how Hopper uses them instead.

## 5. Integration Testing Plan

### Integration boundaries to cover

- API Gateway + PostgreSQL/TimescaleDB.
- API Gateway + NATS JetStream.
- API Gateway + Keycloak.
- API Gateway + Orchestrator gRPC client.
- Orchestrator + Kubernetes fake clientsets and event publication.
- Frontend SSR/API client + real API Gateway in a local test stack.
- Email verification flow with a local SMTP sink or capture service.

### Which dependencies should be real

- PostgreSQL/TimescaleDB should be real for integration tests.
- NATS JetStream should be real for event-flow and retry semantics.
- Keycloak should be real for token issuance, refresh, issuer, and role-claim tests.
- Alembic migrations should run against the test database.

### Which dependencies should be mocked

- Kubernetes should remain mocked or fake-client based for most integration runs unless a dedicated cluster-backed suite is introduced.
- DCGM/GPU metrics sources should stay mocked in local integration and E2E.
- SMTP should be a local capture service or log sink, not an external provider.
- Any future cloud object storage should use an emulator or local fake.

### Test database creation and cleanup

- Keep a dedicated integration database per run using Testcontainers or Compose.
- Apply Alembic migrations before tests.
- Keep table cleanup centralized in `tests/integration/conftest.py`.
- Preserve `TRUNCATE ... RESTART IDENTITY CASCADE` cleanup for deterministic isolation.

### Test isolation

- One test transaction or explicit cleanup per test module where feasible.
- Isolate NATS subjects or consumer names by run identifier when tests operate concurrently.
- Use unique user IDs, pod IDs, and idempotency keys to avoid cross-test interference.

### Container usage

- Keep Testcontainers as the default for Python integration tests.
- Add a single documented `docker compose -f docker-compose.test.yml up` path for full-stack local parity and for E2E.
- Introduce an optional `docker-compose.integration.yml` or expand the existing test compose file with profiles for API Gateway, frontend, and Keycloak seeding.

## 6. End-to-End Testing Plan

Recommended framework: Playwright should remain the E2E framework.

Most important complete flows:

| Flow | Preconditions | Steps | Expected result | Required test data | Services that must be running |
|---|---|---|---|---|---|
| Signup and email verification | Keycloak, API, DB, email capture, frontend | Register student, retrieve code, verify, sign in | Account created, verified, logged in, cookies set | Fresh email, verification code capture | Frontend, API, DB, Keycloak, email sink |
| Login failure | Existing user or Keycloak dev user | Submit invalid credentials | Stable error message, no authenticated session | Invalid password | Frontend, API, Keycloak |
| Session refresh and logout | Authenticated user | Wait for refresh path or trigger guarded navigation, then logout | Session remains valid until logout, then protected routes redirect | Valid user | Frontend, API, Keycloak |
| Student pod launch | Authenticated funded student | Open pods page, choose plan/template, create pod | Pod appears with correct state and connection details when running | Student with credits | Frontend, API, DB, orchestrator or deterministic pod mock, NATS |
| Insufficient credit block | Student with zero or low credits | Attempt pod creation | Request blocked with user-visible explanation | Student with low balance | Frontend, API, DB |
| Pod termination | Student with running pod | Terminate pod from UI | Pod state transitions and billing stops | Seeded running pod | Frontend, API, DB, orchestrator or deterministic pod mock |
| Metrics streaming | Running pod and metrics publisher | Open pod detail/dashboard and observe metrics panel | Live metrics update without reload | Seeded running pod + metrics feed | Frontend, API, NATS |
| Terminal/files access | Running pod with accessible endpoint | Open terminal and file browser/download/upload | Guarded access works only for owner; unauthorized access is blocked | Owner pod and non-owner user | Frontend, API, pod access path |
| Admin role management | Admin account and pending teacher | Approve teacher, view users/stats/nodes | Role mutation succeeds; views are restricted by role | Admin + teacher candidate | Frontend, API, DB, Keycloak |
| Cross-role authorization | Student and admin users | Attempt forbidden admin routes as student | Redirect or 403, depending on layer | Student account | Frontend, API |

Current E2E gap summary:

- Current Playwright coverage is useful but still heavily mock-backed.
- Real-stack E2E should be split into:
  - deterministic mock-backed CI E2E for speed and stability,
  - nightly or pre-release real-stack E2E with the API Gateway, Keycloak, DB, and a real seeded app stack.

## 7. Load and Performance Testing Plan

### Critical endpoints and workflows

- `POST /pods/` for launch bursts.
- `DELETE /pods/{id}` for class-end termination bursts.
- `GET /pods/` and `GET /usage/me` for dashboard refresh.
- `GET /credits/balance` and `GET /credits/history` for billing-heavy reads.
- `GET /pods/{id}/metrics` for frequent polling or SSE alternatives.
- Background billing and metrics event flow through NATS.

### Existing load assets

- `tests/load/scenarios.js` already defines class-start, metrics-polling, spike, class-end, and billing-stress scenarios.
- Those thresholds are a useful placeholder, but they are not yet tied to verified environment capacity or production-like data.

### Initial load-testing model

- Smoke test: low-VU sanity on `GET /healthz`, `GET /pods/`, `GET /credits/balance`, and one pod create/delete cycle.
- Average-load test: representative student dashboard and balance usage at moderate concurrency.
- Stress test: sustained pod creation, listing, and billing events until graceful degradation appears.
- Spike test: short burst on pod list, balance, and usage endpoints.
- Soak test: long-running metrics, billing, and refresh traffic to catch leaks and queue growth.

### Performance criteria

Use these as categories, not fixed production targets, until validated:

- Requests per second: confirm per endpoint and per scenario.
- Latency: track p50, p95, and p99 by endpoint and scenario.
- Error rate: keep under an agreed threshold per scenario.
- Throughput: track pod create/terminate completions and billing events processed.
- Concurrent users/VUs: confirm expected class-size concurrency with stakeholders.
- Resource usage: CPU, memory, DB connections, NATS stream lag, and queue latency.

Values that require confirmation:

- Real expected concurrent class size.
- Peak pod-launch burst size.
- Acceptable pod-provisioning latency in a real cluster.
- Sustained metrics and billing event rates.

## 8. Test Environment and Infrastructure

### Required test environment

- Test database: dedicated PostgreSQL/TimescaleDB instance or container.
- NATS JetStream test instance.
- Keycloak test instance with deterministic realm/client/user seeding.
- Mock Kubernetes API and mock DCGM exporter for deterministic CI.
- Optional SMTP capture service for auth flows.
- Frontend test env aligned with `.env.example`.

### Test-specific environment variables

- API: `HOPPER_DATABASE_URL`, `HOPPER_NATS_URL`, `HOPPER_KEYCLOAK_URL`, `HOPPER_KEYCLOAK_EXTERNAL_URL`, `HOPPER_KEYCLOAK_CLIENT_ID`, `HOPPER_KEYCLOAK_CLIENT_SECRET`, `HOPPER_ORCHESTRATOR_URL`, `HOPPER_FRONTEND_URL`, `HOPPER_CALLBACK_URL`, `HOPPER_CORS_ORIGINS`, `HOPPER_ALLOWED_EMAIL_DOMAINS`, SMTP settings, and code-signing secret.
- Frontend: `API_PROXY_TARGET`, `API_PROXY_STRIP_PREFIX`, `API_PROXY_SECURE`, `API_PROXY_ORIGIN`, `API_INTERNAL_URL`, `KEYCLOAK_*`, and dev-login credentials.
- E2E: `BASE_URL`, `E2E_CROSS_BROWSER`, and deterministic test-user credentials.

### Migration and seed strategy

- Apply Alembic migrations at test-stack startup.
- Seed Keycloak realm, clients, roles, and a minimal user set.
- Seed DB users/accounts/pods only through repeatable scripts or fixtures, not manual setup.
- Seed mock API data for fast E2E flows.

### Cleanup strategy

- Compose down with volumes only for disposable CI runs.
- Table truncation for Python integration tests.
- Unique namespaces or labels for any cluster-backed staging tests.
- Artifact retention for Playwright reports and load summaries before cleanup.

### Port allocation

- Keep current local defaults where possible: frontend `5173`, API `8000`, PostgreSQL `5433`, NATS `4222`, Keycloak `8080`.
- Document these centrally for local and CI parity.

### Secret handling

- Keep all secrets in GitHub Actions secrets or local `.env`, never in test code.
- Distinguish CI secrets for mock-backed runs from staging secrets for chaos/security.

### Keeping local and CI consistent

- One canonical bootstrap path should exist for each layer:
  - Python unit/integration.
  - Go orchestrator tests.
  - Frontend unit tests.
  - Playwright deterministic stack.
- Local commands should use the same env names and service definitions as CI.
- Fix stale commands that point at non-existent paths or rely on undeclared cache locations.

## 9. Coverage Reporting Plan

### Coverage tooling by application

- API Gateway: `pytest-cov`.
- Frontend: Vitest coverage with V8 provider or Istanbul-compatible output.
- Orchestrator: `go test -coverprofile`.

### Recommended commands

- Python terminal + XML:
  - `PYTHONPATH=$PWD/services/api-gateway poetry --directory services/api-gateway run pytest $PWD/tests/unit $PWD/tests/integration --cov=app --cov-report=term-missing --cov-report=xml:coverage/python.xml --cov-report=html:coverage/python-html`
- Frontend terminal + LCOV:
  - `cd frontend && npx pnpm@10 vitest run --coverage`
- Go terminal + profile:
  - `cd tests/orchestrator && GOCACHE=/private/tmp/hopper-go-test-cache go test ./... -coverprofile=../coverage/orchestrator.out`
  - Optionally convert to XML for CI reporting via `gocover-cobertura`.

### Exclusions with justification

- Generated protobuf code.
- Migration history from threshold math, while still smoke-tested by migration execution.
- Pure static assets and design files.
- Test-only mocks and helper scripts.

### Recommended initial thresholds

These should be gates on meaningful suites, not a reason to add trivial tests.

- API Gateway unit: statements 80%, branches 70%, functions 80%, lines 80%.
- API Gateway combined unit+integration: statements 85%, branches 75%, functions 85%, lines 85%.
- Frontend unit: statements 60%, branches 50%, functions 60%, lines 60% initially, then raise after route/store coverage expands.
- Orchestrator: statements 70%, branches 60%, functions 70%, lines 70% initially.

### Combining coverage

- Publish per-application reports separately first.
- Optionally aggregate in a single CI summary, but do not collapse Python, Go, and frontend into one meaningless blended percentage.
- Fail CI per application when its own threshold drops below the agreed baseline.

## 10. CI/CD Testing Pipeline

Recommended execution order:

1. Dependency installation.
2. Static analysis.
3. API Gateway unit tests + coverage.
4. Frontend unit tests + coverage.
5. Orchestrator tests + coverage.
6. Integration-service startup.
7. Database migrations and deterministic seeding.
8. API integration tests.
9. Real or fake orchestrator contract tests.
10. Frontend application startup.
11. Deterministic E2E tests.
12. Coverage artifact upload.
13. Load-test smoke check.
14. Cleanup.

Recommended workflow layout:

- `pull_request` fast path:
  - frontend lint/check/test/build
  - API import + lint
  - API unit tests with coverage
  - Go tests with coverage
  - deterministic integration tests
  - deterministic Playwright E2E
- `push` to main:
  - all of the above
  - publish combined test summary artifacts
  - optional load smoke
- nightly or scheduled:
  - cross-browser E2E
  - full load scenarios
  - chaos validation
  - security validation
  - real-stack auth and pod lifecycle E2E

### Current CI gaps to close first

- Add frontend coverage collection and artifact upload.
- Add Go coverage collection and artifact upload.
- Enforce documented coverage thresholds explicitly once agreed.
- Remove stale local test commands that point to missing paths.
- Document the required `GOCACHE` override for sandboxed or restricted environments.
- Separate deterministic CI E2E from higher-fidelity real-stack E2E so both are reliable and honest.

## 11. Immediate Infrastructure Priorities

1. Normalize local and CI test commands so every suite has one canonical invocation.
2. Add missing coverage reporting for frontend and Go before raising thresholds.
3. Introduce deterministic seeding for Keycloak, DB, and mock API so auth and role flows are reproducible.
4. Expand frontend unit coverage, especially loaders, auth state, and pod-management UI logic.
5. Add a real-stack nightly E2E layer that exercises the actual API Gateway, Keycloak, and DB instead of only mocks.
6. Treat security and chaos as platform-gate suites with explicit artifacts and result reporting, not just scripts in the tree.
