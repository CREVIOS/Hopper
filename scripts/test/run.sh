#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTEST_BIN_DEFAULT="$ROOT/services/api-gateway/.venv/bin/pytest"
COMPOSE_FILE="$ROOT/docker-compose.test.yml"
GO_TEST_CACHE_DEFAULT="$ROOT/.cache/go-test"

mkdir -p \
  "$ROOT/coverage/python" \
  "$ROOT/coverage/frontend" \
  "$ROOT/coverage/orchestrator" \
  "$ROOT/tests/coverage" \
  "$ROOT/test-results/unit" \
  "$ROOT/test-results/integration" \
  "$ROOT/test-results/e2e" \
  "$ROOT/test-results/load" \
  "$ROOT/test-results/security" \
  "$ROOT/test-results/chaos" \
  "$ROOT/.cache/go-test"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

require_cmd() {
  have_cmd "$1" || die "Missing required command: $1"
}

require_docker_daemon() {
  require_cmd docker
  docker info >/dev/null 2>&1 || die "Docker is installed but the daemon is unavailable."
}

frontend_exec() {
  (
    cd "$ROOT/frontend"
    "$@"
  )
}

e2e_exec() {
  (
    cd "$ROOT/tests/e2e"
    "$@"
  )
}

python_pytest() {
  if [[ -x "$PYTEST_BIN_DEFAULT" ]]; then
    PYTHONPATH="$ROOT/services/api-gateway" "$PYTEST_BIN_DEFAULT" "$@"
    return
  fi

  require_cmd poetry
  PYTHONPATH="$ROOT/services/api-gateway" poetry --directory "$ROOT/services/api-gateway" run pytest "$@"
}

frontend_validate() {
  require_cmd node
  require_cmd npx
  frontend_exec npx eslint .
  frontend_exec npx svelte-kit sync
  frontend_exec npx svelte-check --tsconfig ./tsconfig.json
  frontend_exec npx vitest run
  frontend_exec npx vite build
}

python_unit() {
  python_pytest \
    "$ROOT/tests/unit" \
    -v \
    --tb=short \
    --cov=app \
    --cov-config="$ROOT/services/api-gateway/.coveragerc" \
    --cov-report=term-missing \
    --cov-report="xml:$ROOT/coverage/python/unit.xml"
}

python_integration() {
  require_docker_daemon
  python_pytest \
    "$ROOT/tests/integration" \
    -v \
    --tb=short \
    --cov=app \
    --cov-config="$ROOT/services/api-gateway/.coveragerc" \
    --cov-report=term-missing \
    --cov-report="xml:$ROOT/coverage/python/integration.xml"
}

frontend_tests() {
  frontend_exec npx vitest run
}

frontend_coverage() {
  frontend_exec npx vitest run --coverage
}

render_coverage_report() {
  require_cmd python3
  python3 "$ROOT/scripts/test/generate_coverage_report.py"
}

orchestrator_tests() {
  require_cmd go
  require_cmd python3
  local external_profile="$ROOT/coverage/orchestrator/orchestrator-external.out"
  local internal_k8s_profile="$ROOT/coverage/orchestrator/orchestrator-internal-k8s.out"

  (
    cd "$ROOT/tests/orchestrator"
    GOCACHE="${GOCACHE:-$GO_TEST_CACHE_DEFAULT}" go test ./... -race -count=1 \
      -coverpkg=github.com/hopper/orchestrator/... \
      -coverprofile="$external_profile"
  )
  (
    cd "$ROOT/services/orchestrator"
    GOCACHE="${GOCACHE:-$GO_TEST_CACHE_DEFAULT}" go test ./internal/k8s -count=1 \
      -coverpkg=github.com/hopper/orchestrator/... \
      -coverprofile="$internal_k8s_profile"
  )
  python3 "$ROOT/scripts/test/merge_go_coverprofiles.py" \
    "$ROOT/coverage/orchestrator/orchestrator.out" \
    "$external_profile" \
    "$internal_k8s_profile"
}

test_services_up() {
  require_docker_daemon
  docker compose -f "$COMPOSE_FILE" up -d --build mock-api mock-k8s mock-dcgm postgres nats keycloak
}

test_services_down() {
  require_cmd docker
  docker compose -f "$COMPOSE_FILE" down -v
}

e2e_tests() {
  e2e_exec npx playwright test
}

e2e_real_tests() {
  require_cmd node
  require_cmd npx
  [[ -n "${BASE_URL:-}" ]] || die "BASE_URL must point at the real stack under test."
  e2e_exec npx playwright test
}

load_smoke() {
  require_cmd k6
  BASE_URL="${BASE_URL:-http://127.0.0.1:8000}" ACCESS_TOKEN="${ACCESS_TOKEN:-e2e-student}" \
    k6 run --summary-export "$ROOT/test-results/load/class-start-summary.json" "$ROOT/tests/load/class-start.js"
}

load_full() {
  require_cmd k6
  BASE_URL="${BASE_URL:-http://127.0.0.1:8000}" ACCESS_TOKEN="${ACCESS_TOKEN:-e2e-student}" \
    k6 run --summary-export "$ROOT/test-results/load/scenarios-summary.json" "$ROOT/tests/load/scenarios.js"
}

security_checks() {
  require_cmd bash
  require_cmd python3
  bash -n "$ROOT/tests/security/"*.sh
  python3 -m py_compile "$ROOT/tests/security/"*.py

  if [[ -n "${BASE_URL:-}" && -n "${STUDENT_TOKEN:-}" && -n "${ADMIN_TOKEN:-}" && -n "${OTHER_STUDENT_POD_ID:-}" ]]; then
    "$ROOT/tests/security/run-security.sh"
  else
    echo "Security scripts validated. Live security execution skipped because required env vars are not set."
  fi
}

chaos_checks() {
  require_cmd bash
  bash -n "$ROOT/tests/chaos/verify-invariants.sh"

  if [[ -n "${DATABASE_URL:-}" ]] && have_cmd kubectl && have_cmd psql && have_cmd nats; then
    "$ROOT/tests/chaos/verify-invariants.sh"
  else
    echo "Chaos helpers validated. Live chaos invariant execution skipped because staging tools/env are not set."
  fi
}

coverage_all() {
  python_unit
  orchestrator_tests
  frontend_coverage
  render_coverage_report
}

test_all() {
  frontend_validate
  python_unit
  orchestrator_tests
}

test_ci() {
  frontend_validate
  python_unit
  orchestrator_tests
  python_integration
}

clean_outputs() {
  rm -rf \
    "$ROOT/coverage" \
    "$ROOT/test-results" \
    "$ROOT/.cache/go-test"
}

show_help() {
  cat <<'EOF'
Usage: scripts/test/run.sh <command>

Public commands:
  test-unit           Run Python unit tests with coverage output
  test-integration    Run Python integration tests with coverage output
  test-frontend       Run frontend Vitest suites
  test-orchestrator   Run standalone Go orchestrator tests with coverage output
  test-e2e            Start deterministic mock services and run Playwright
  test-e2e-real       Run Playwright against BASE_URL without mock-stack bootstrap
  test-load-smoke     Run the k6 smoke scenario
  test-load           Run the k6 multi-scenario suite
  test-security       Validate security scripts and optionally execute live checks
  test-chaos          Validate chaos scripts and optionally execute live invariants
  test-coverage       Run Python unit, frontend, and Go coverage-producing suites
  test-coverage-report Render tests/coverage/REPORT.md from existing artifacts
  test-all            Run local fast-path validation
  test-ci             Run the CI-oriented validation path
  test-services-up    Start deterministic test services from docker-compose.test.yml
  test-services-down  Stop deterministic test services
  test-clean          Remove generated coverage, test-results, and local Go cache
  help                Show this help output

Internal commands used by CI:
  frontend-validate   Run frontend lint, typecheck, test, and build
EOF
}

command_name="${1:-help}"

case "$command_name" in
  test-unit) python_unit ;;
  test-integration) python_integration ;;
  test-frontend) frontend_tests ;;
  test-orchestrator) orchestrator_tests ;;
  test-e2e) e2e_tests ;;
  test-e2e-real) e2e_real_tests ;;
  test-load-smoke) load_smoke ;;
  test-load) load_full ;;
  test-security) security_checks ;;
  test-chaos) chaos_checks ;;
  test-coverage) coverage_all ;;
  test-coverage-report) render_coverage_report ;;
  test-all) test_all ;;
  test-ci) test_ci ;;
  test-services-up) test_services_up ;;
  test-services-down) test_services_down ;;
  test-clean) clean_outputs ;;
  frontend-validate) frontend_validate ;;
  help|--help|-h) show_help ;;
  *) die "Unknown command: $command_name (run 'scripts/test/run.sh help')" ;;
esac
