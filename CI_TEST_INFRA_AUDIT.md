# CI Test Infrastructure Audit

Date: 2026-07-17
Repository: `Hopper`
Scope: repository inspection only; no workflow edits were made.

## 1. Current CI Test Matrix

### Main PR/Push CI: `.github/workflows/ci.yml`

| Workflow | Job | Trigger | Exact command(s) | Required services | Failures block merging? | Status |
|---|---|---|---|---|---|---|
| `ci.yml` | `frontend` | `push` to `main`/`master`, `pull_request` to `main`/`master` | `pnpm install --frozen-lockfile` in `frontend`; `./scripts/test/run.sh frontend-validate`; `cd frontend && npx vitest run --coverage` | none beyond runner toolchain | PR check fails if job fails; actual branch-protection enforcement is not provable from repo contents | `complete` |
| `ci.yml` | `api-gateway` | same | `poetry install --no-interaction`; `poetry run python -c "from app.main import app; print('app.main OK')"` | none | same limitation | `partial` |
| `ci.yml` | `unit-tests` | same | `./scripts/test/run.sh test-unit` | none | same limitation | `complete` |
| `ci.yml` | `helm-chart` | same | `helm lint charts/hopper -f charts/hopper/values-prod.yaml`; `helm template ... -f charts/hopper/values-{dev,staging,prod}.yaml` | none | same limitation | `complete` |
| `ci.yml` | `lint-go` | same | install `protobuf-compiler`; `protoc ...`; install `golangci-lint`; `golangci-lint run --timeout 5m ./...` in `services/orchestrator` and `tests/orchestrator` | apt package install; Go toolchain | same limitation | `complete` |
| `ci.yml` | `orchestrator` | same | `./scripts/test/run.sh test-orchestrator`; then `go test ./... -race -count=1` in `tests/orchestrator` | none external | same limitation | `partial` |
| `ci.yml` | `integration` | same | `./scripts/test/run.sh test-integration` | Docker daemon for Testcontainers | same limitation | `complete` |
| `ci.yml` | `e2e-tests` | same | install frontend + E2E deps; `pnpm exec playwright install --with-deps chromium`; `docker compose -f docker-compose.test.yml up -d --build mock-api mock-k8s mock-dcgm postgres nats`; `./scripts/test/run.sh test-e2e`; `docker compose ... down -v` | Docker daemon; Chromium; optionally compose services | same limitation | `partial` |
| `ci.yml` | `docker` | same | `TAG="ci-${{ github.sha }}" ./scripts/ci/docker-build.sh` | Docker Buildx | same limitation | `complete` |

### Nightly/Manual/Staging Platform Checks: `.github/workflows/test-platform.yml`

| Workflow | Job | Trigger | Exact command(s) | Required services | Failures block merging? | Status |
|---|---|---|---|---|---|---|
| `test-platform.yml` | `cross-browser-e2e` | `workflow_dispatch`, nightly cron `17 2 * * *`, `release.prereleased` | install frontend + E2E deps; `pnpm exec playwright install --with-deps chromium firefox webkit`; `./scripts/test/run.sh test-e2e` with `CI=true E2E_CROSS_BROWSER=true` | browsers; no compose stack started in workflow | No, not a PR workflow | `partial` |
| `test-platform.yml` | `load` | same | `./scripts/test/run.sh test-services-up`; `./scripts/test/run.sh test-load-smoke`; `./scripts/test/run.sh test-load`; `./scripts/test/run.sh test-services-down` | Docker daemon; k6; compose test stack | No | `complete` |
| `test-platform.yml` | `chaos-manifests` | same | YAML validation via `docker run ... mikefarah/yq:4`; optionally `kubectl apply -f tests/chaos/` and `tests/chaos/verify-invariants.sh` | Docker for validation; staging kubeconfig secret for live run | No | `partial` |
| `test-platform.yml` | `security` | same | `bash -n tests/security/*.sh`; `python -m py_compile tests/security/*.py`; YAML validation via `docker run ... mikefarah/yq:4`; optionally `tests/security/run-security.sh` | Python; Docker; staging secrets and kubeconfig for live run | No | `partial` |

### Other CI-adjacent workflows

| Workflow | Job | Trigger | Exact command(s) | Required services | Failures block merging? | Status |
|---|---|---|---|---|---|---|
| `lint-python.yml` | `ruff` | `push` to `main`/`master`, `pull_request` to `main`/`master` | `poetry install --no-interaction`; `poetry run ruff check .` | none | PR check fails if job fails; branch protection still external | `complete` |
| `publish.yml` | `build-push` | `push` to `main`/`master`, `push` tags `v*`, `workflow_dispatch` | `DOCKER_PUSH=1 ... ./scripts/ci/docker-build.sh` | Docker, GHCR auth | Not a test gate | `not-applicable` |
| `publish.yml` | `deploy` | manual or auto-deploy on configured pushes | remote `scripts/cd/k8s-rollout.sh` over SSH | VPS secrets, SSH, kubectl on VPS | Not a test gate | `not-applicable` |

## 2. What Is Actually Running

### Requested test categories

| Item | Where it runs | What actually happens | Status |
|---|---|---|---|
| Python unit tests | `ci.yml` / `unit-tests` | `./scripts/test/run.sh test-unit` -> repo-root `tests/unit` via pytest with coverage XML at `coverage/python/unit.xml` | `complete` |
| Python integration tests | `ci.yml` / `integration` | `./scripts/test/run.sh test-integration` -> repo-root `tests/integration` via pytest with coverage XML; fixtures use Testcontainers for Postgres and NATS; migrations run inside `tests/integration/conftest.py` | `complete` |
| Frontend Vitest tests | `ci.yml` / `frontend` | `frontend-validate` already runs `npx vitest run`; job then reruns `npx vitest run --coverage` | `complete` |
| Go orchestrator tests | `ci.yml` / `orchestrator` | `test-orchestrator` runs `go test ./... -race -count=1 -coverpkg=... -coverprofile=...` in `tests/orchestrator` plus `go test ./internal/k8s ...` in `services/orchestrator`; job then reruns `go test ./... -race -count=1` in `tests/orchestrator` without coverage | `complete` |
| Contract tests | `ci.yml` / `orchestrator`, `unit-tests` | The repo treats `tests/orchestrator` as contract/fake-client tests and includes Python contract-style tests such as `tests/unit/services/test_session_reaper_contract.py`; there is no separate contract workflow or label | `partial` |
| Playwright E2E tests | `ci.yml` / `e2e-tests`; `test-platform.yml` / `cross-browser-e2e` | `./scripts/test/run.sh test-e2e` runs `npx playwright test`; Playwright starts its own mock control server on `127.0.0.1:18000` and Vite dev server | `partial` |
| Coverage generation for Python | `unit-tests`, `integration` | XML artifacts generated and uploaded separately | `complete` |
| Coverage generation for frontend | `frontend` | Vitest coverage generated under `coverage/frontend` and uploaded | `complete` |
| Coverage generation for Go | `orchestrator` | merged coverprofile generated at `coverage/orchestrator/orchestrator.out` and uploaded | `complete` |
| Database migrations | integration tests only | Alembic `upgrade head` runs inside `tests/integration/conftest.py` for the Testcontainers DB. There is no standalone CI migration job and no migration check in `api-gateway` smoke or E2E jobs | `partial` |
| PostgreSQL test service | integration via Testcontainers; E2E/load via compose | Integration definitely uses ephemeral Postgres. PR E2E compose starts `postgres`, but Playwright config does not target it | `partial` |
| NATS test service | integration via Testcontainers; E2E/load via compose | Integration definitely uses ephemeral NATS. PR E2E compose starts `nats`, but Playwright config does not target it | `partial` |
| Keycloak test service | integration tests via ephemeral Testcontainers in specific tests; load stack can start compose `keycloak` | No PR CI job starts Keycloak. Keycloak-specific integration coverage is only whatever repo-root pytest integration suite reaches. E2E uses a mock control server, not real Keycloak | `partial` |
| Load smoke tests | `test-platform.yml` / `load` | Both smoke and full k6 suites run against `BASE_URL=http://127.0.0.1:8000` | `complete` |
| Artifact uploads: coverage | PR CI and nightly load | Python/frontend/Go coverage artifacts are uploaded; load summaries uploaded in nightly/manual workflow | `complete` |
| Artifact uploads: logs | none explicit | No dedicated upload for compose logs, pytest logs, or service logs | `missing` |
| Artifact uploads: screenshots/traces/videos | Playwright E2E | Playwright is configured to collect them on retry/failure, but workflow uploads only `tests/e2e/playwright-report`, not `tests/e2e/test-results` | `partial` |
| Artifact uploads: reports | Playwright and load | HTML Playwright report uploaded; load summaries uploaded | `partial` |

### Important repo-verified behavior

1. PR CI does run real Python unit, Python integration, frontend Vitest, and Go orchestrator test jobs.
2. Python integration tests are the only place where database migrations are definitely exercised automatically.
3. PR E2E does not exercise a real API gateway, real Keycloak, or the compose Postgres/NATS services. Playwright points the frontend at `E2E_CONTROL_URL` defaulting to `http://127.0.0.1:18000`, and the workflow never overrides that.
4. Nightly/manual load tests do run, but against the deterministic mock API on `:8000`, not a full staging stack.
5. Chaos and security workflows are mostly validation wrappers unless staging secrets are present; their live execution is conditional and optional.

## 3. What Is Missing or Broken

### High-impact gaps

1. CI/CD does not fully enforce the complete testing plan. The repo’s documented test strategy is broader than what PR CI actually executes.
2. There is no standalone migration gate in PR CI. Migrations run only as a side effect of integration tests.
3. PR E2E is not a real end-to-end environment. The workflow starts compose services, but Playwright uses an in-process mock API on port `18000` and a frontend dev server. That makes the compose `mock-api`, `postgres`, and `nats` effectively unused by the browser tests.
4. PR E2E does not start `keycloak` at all, despite `docker-compose.test.yml` defining it and the broader platform depending on it.
5. Contract tests are not separated or fully explicit. They run implicitly as part of `tests/orchestrator` and some Python unit tests, but there is no dedicated CI gate named for contracts.
6. Staging chaos and security checks can silently degrade to syntax/manifest validation only when secrets are absent. The workflows exist, but live execution is optional.

### Broken or mismatched wiring

1. `ci.yml` `e2e-tests` starts `docker compose ... mock-api mock-k8s mock-dcgm postgres nats`, but `tests/e2e/playwright.config.ts` routes the frontend to `controlURL` on port `18000`. That is a command/config mismatch.
2. `scripts/test/run.sh test-services-up` starts `keycloak`, but `ci.yml` `e2e-tests` does not. The workflow bypasses the shared script’s more complete test stack.
3. `ci.yml` `orchestrator` runs the `tests/orchestrator` suite twice: once through `test-orchestrator` with coverage merging, then again with plain `go test ./... -race -count=1`. This is redundant, slows CI, and makes the job intent less clear.
4. Playwright captures traces, screenshots, and retained videos on failure/retry, but the workflow does not upload `tests/e2e/test-results`, so the raw debugging artifacts are not preserved.
5. There is no artifact upload for Docker Compose logs or service state after failed integration/E2E/load jobs.

### Incomplete coverage against requested infrastructure

1. No PR workflow runs load smoke tests.
2. No PR workflow runs chaos or security live checks.
3. No PR workflow proves a real Keycloak-backed browser auth flow.
4. No PR workflow proves a real API gateway plus frontend plus database plus NATS path in one stack.
5. No repo evidence proves GitHub branch protection marks all PR test jobs as required. Workflow failure creates failed checks, but merge enforcement depends on GitHub settings outside the repository.

### Ignored failures / optional behavior

1. Artifact upload steps all use `if: always()` with `if-no-files-found: ignore`; that is fine for diagnostics, but it means missing artifacts do not fail the workflow.
2. Chaos/security live staging steps are conditional on secrets and may be skipped entirely.
3. Keycloak-specific integration tests use `pytest.mark.skipif(not _docker_available())`; on a normal GitHub-hosted Linux runner Docker should exist, but the tests are still conditionally skippable by environment.

## 4. Pull Request vs Nightly vs Staging Coverage

### Pull request / push coverage

PR CI currently covers:

- frontend lint, typecheck, Vitest, build, and frontend coverage
- Python import smoke
- Python unit tests with coverage
- Python integration tests with Testcontainers-backed infrastructure and migrations
- Go lint plus orchestrator contract/fake-client tests with coverage
- Helm lint/render
- Playwright browser tests against a mock control server
- Docker image build smoke

PR CI does not currently cover:

- load smoke or load scenarios
- chaos live checks
- security live checks
- real Keycloak-backed browser login
- full-stack browser E2E against real API gateway/Postgres/NATS/Keycloak
- explicit migration-only gating

### Nightly / manual / prerelease coverage

`test-platform.yml` adds:

- optional cross-browser Playwright run
- load smoke and full k6 scenarios
- chaos manifest validation and optional live staging chaos
- security script validation and optional live staging security checks

This is useful platform validation, but it is not PR-enforced.

### Staging-only or secret-gated coverage

The only repo-defined staging-dependent checks are:

- `chaos-manifests` live step using `secrets.STAGING_KUBECONFIG`
- `security` live step using `STAGING_BASE_URL`, `STAGING_STUDENT_TOKEN`, `STAGING_ADMIN_TOKEN`, `STAGING_OTHER_STUDENT_POD_ID`, and `STAGING_KUBECONFIG`

If those secrets are absent, the workflows still exist but the live checks do not run.

## 5. Exact Recommended Fixes

1. Make PR E2E honest: either remove the unused compose startup and clearly classify the job as mock-browser acceptance, or rewire Playwright to target a real API gateway/frontend stack backed by Postgres, NATS, and Keycloak.
2. Add a dedicated PR migration gate, for example a job that runs `PYTHONPATH=. poetry run alembic upgrade head` against a fresh Postgres service and fails on migration errors.
3. If full-stack browser E2E is required, start `keycloak` in PR CI and point the frontend/API to real service URLs instead of `E2E_CONTROL_URL`.
4. Upload `tests/e2e/test-results` in addition to `tests/e2e/playwright-report` so traces, screenshots, and retained videos survive failed CI runs.
5. Upload compose/service diagnostics on failure, such as `docker compose -f docker-compose.test.yml logs --no-color`, plus any pytest or k6 result files.
6. Split contract testing into explicit CI jobs or rename existing jobs/steps so the coverage is unambiguous. Right now “contract tests” are scattered across Python unit tests and `tests/orchestrator`.
7. Remove the duplicate second `go test ./... -race -count=1` step from the `orchestrator` job or justify it with a different target.
8. Decide whether load smoke is a PR gate. If yes, add at least `./scripts/test/run.sh test-load-smoke` to PR CI against the deterministic stack.
9. Decide whether Keycloak integration tests are required on every PR. If yes, isolate them with markers and a dedicated job so they are visible rather than incidental inside the broad integration suite.
10. Document branch-protection requirements outside the repo or in repo docs, because merge blocking cannot currently be proven from code alone.

## 6. Final Verdict

The testing infrastructure is **not fully enforced by CI/CD**.

What is real and enforced today:

- Python unit tests
- Python integration tests with migrations
- frontend Vitest coverage
- Go orchestrator tests and coverage
- mock-based Playwright acceptance tests
- nightly/manual load checks

What is not fully enforced:

- real full-stack E2E through frontend + API gateway + Postgres + NATS + Keycloak
- PR-gated load smoke
- PR-gated chaos/security live checks
- explicit contract-test gating
- complete artifact preservation for E2E debugging
- provable merge blocking via branch protection from repo contents alone

Bottom line: the repository has a meaningful CI test platform, but the complete testing infrastructure described in docs is only **partially** wired into CI/CD, and several important jobs are mock-driven or optional rather than fully enforced.
