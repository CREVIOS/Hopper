#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTEST_BIN_DEFAULT="$ROOT/services/api-gateway/.venv/bin/pytest"
MOCK_COMPOSE_FILE="$ROOT/docker-compose.test.yml"
REAL_COMPOSE_FILE="$ROOT/docker-compose.yml"
GO_TEST_CACHE_DEFAULT="$ROOT/.cache/go-test"
REPORT_ROOT="$ROOT/test-results"
TESTS_COVERAGE_ROOT="$ROOT/tests/coverage"
SERVICE_LOG_DIR="$REPORT_ROOT/services"
REAL_STACK_DIR="$REPORT_ROOT/real-stack"
REAL_STACK_PID_DIR="$REAL_STACK_DIR/pids"
REAL_STACK_LOG_DIR="$REAL_STACK_DIR/logs"
PLAYWRIGHT_OUTPUT_DIR="$ROOT/tests/e2e/test-results"
PLAYWRIGHT_REPORT_DIR="$ROOT/tests/e2e/playwright-report"

mkdir -p \
  "$ROOT/coverage/python" \
  "$ROOT/coverage/frontend" \
  "$ROOT/coverage/orchestrator" \
  "$TESTS_COVERAGE_ROOT" \
  "$REPORT_ROOT/unit" \
  "$REPORT_ROOT/integration" \
  "$REPORT_ROOT/frontend" \
  "$REPORT_ROOT/contracts" \
  "$REPORT_ROOT/orchestrator" \
  "$REPORT_ROOT/e2e" \
  "$REPORT_ROOT/load" \
  "$REPORT_ROOT/security" \
  "$REPORT_ROOT/chaos" \
  "$SERVICE_LOG_DIR" \
  "$REAL_STACK_PID_DIR" \
  "$REAL_STACK_LOG_DIR" \
  "$ROOT/.cache/go-test"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

sync_html_coverage_dir() {
  local src=$1
  local dest=$2

  [[ -d "$src" ]] || die "Coverage HTML directory missing: $src"
  rm -rf "$dest"
  mkdir -p "$(dirname "$dest")"
  cp -R "$src" "$dest"
}

render_go_html() {
  local profile=$1
  local dest_dir=$2
  local module_dir=${3:-$ROOT/services/orchestrator}

  [[ -f "$profile" ]] || die "Go coverage profile missing: $profile"
  mkdir -p "$dest_dir"
  (
    cd "$module_dir"
    GOCACHE="${GOCACHE:-$GO_TEST_CACHE_DEFAULT}" \
      go tool cover -html="$profile" -o "$dest_dir/index.html"
  )
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

compose_cmd() {
  local compose_file=$1
  shift
  docker compose -f "$compose_file" "$@"
}

container_has_healthcheck() {
  local container_id=$1
  docker inspect --format '{{if .State.Health}}yes{{else}}no{{end}}' "$container_id" 2>/dev/null
}

dump_container_diagnostics() {
  local container_id=$1
  local service=$2

  echo "Container diagnostics for $service ($container_id):" >&2
  docker inspect --format 'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} exit_code={{.State.ExitCode}} error={{.State.Error}} started_at={{.State.StartedAt}}' "$container_id" >&2 || true
  docker inspect --format '{{if .State.Health}}{{range .State.Health.Log}}{{println .Start "exit=" .ExitCode}}{{println .Output}}{{end}}{{end}}' "$container_id" >&2 || true
  docker logs --tail 200 "$container_id" >&2 || true
}

wait_for_http() {
  local url=$1
  local label=$2
  local attempts=${3:-60}
  local sleep_seconds=${4:-2}

  require_cmd curl
  for ((i = 1; i <= attempts; i += 1)); do
    if curl --fail --silent --show-error "$url" >/dev/null 2>&1; then
      echo "Ready: $label ($url)"
      return 0
    fi
    sleep "$sleep_seconds"
  done

  die "Timed out waiting for $label at $url"
}

http_ready() {
  local url=$1
  local attempts=${2:-60}
  local sleep_seconds=${3:-2}

  require_cmd curl
  for ((i = 1; i <= attempts; i += 1)); do
    if curl --fail --silent --show-error "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$sleep_seconds"
  done

  return 1
}

wait_for_port() {
  local host=$1
  local port=$2
  local label=$3
  local attempts=${4:-60}
  local sleep_seconds=${5:-1}

  require_cmd python3
  for ((i = 1; i <= attempts; i += 1)); do
    if python3 - "$host" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
sock = socket.socket()
sock.settimeout(1.0)
try:
    sock.connect((host, port))
except OSError:
    sys.exit(1)
finally:
    sock.close()
PY
    then
      echo "Ready: $label ($host:$port)"
      return 0
    fi
    sleep "$sleep_seconds"
  done

  die "Timed out waiting for $label on $host:$port"
}

wait_for_container_health() {
  local compose_file=$1
  local service=$2
  local attempts=${3:-60}
  local sleep_seconds=${4:-2}
  local container_id
  local has_healthcheck

  container_id=$(compose_cmd "$compose_file" ps -q "$service")
  [[ -n "$container_id" ]] || die "Could not resolve container for service: $service"
  has_healthcheck=$(container_has_healthcheck "$container_id")

  for ((i = 1; i <= attempts; i += 1)); do
    local status
    status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)
    if [[ "$status" == "healthy" ]]; then
      echo "Ready: $service container status=$status"
      return 0
    fi
    if [[ "$has_healthcheck" != "yes" && "$status" == "running" ]]; then
      echo "Ready: $service container status=$status"
      return 0
    fi
    if [[ "$status" == "unhealthy" || "$status" == "exited" || "$status" == "dead" ]]; then
      dump_container_diagnostics "$container_id" "$service"
      die "Container failed before becoming ready: $service (status=$status)"
    fi
    sleep "$sleep_seconds"
  done

  dump_container_diagnostics "$container_id" "$service"
  die "Timed out waiting for healthy container: $service"
}

mock_services_wait() {
  wait_for_container_health "$MOCK_COMPOSE_FILE" postgres
  wait_for_container_health "$MOCK_COMPOSE_FILE" nats
  wait_for_container_health "$MOCK_COMPOSE_FILE" keycloak 120 2
  wait_for_http "http://127.0.0.1:9000/health/ready" "Keycloak management readiness" 30 2
  wait_for_http "http://127.0.0.1:8000/healthz" "mock API"
  wait_for_port "127.0.0.1" "6443" "mock K8s API"
  wait_for_port "127.0.0.1" "9400" "mock DCGM exporter"
}

real_services_wait() {
  wait_for_container_health "$REAL_COMPOSE_FILE" postgres
  wait_for_container_health "$REAL_COMPOSE_FILE" nats
  wait_for_container_health "$REAL_COMPOSE_FILE" keycloak 120 2
  wait_for_http "http://127.0.0.1:9000/health/ready" "Keycloak management readiness" 30 2
}

collect_compose_logs() {
  local compose_file=$1
  local name=$2
  mkdir -p "$SERVICE_LOG_DIR"
  compose_cmd "$compose_file" logs --no-color >"$SERVICE_LOG_DIR/$name.log" 2>&1 || true
}

kill_pid_file() {
  local pid_file=$1
  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(cat "$pid_file" 2>/dev/null || true)
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      wait "$pid" >/dev/null 2>&1 || true
    fi
    rm -f "$pid_file"
  fi
}

frontend_validate() {
  require_cmd node
  require_cmd npx
  frontend_exec npx eslint .
  frontend_exec npx svelte-kit sync
  frontend_exec npx svelte-check --tsconfig ./tsconfig.json
  frontend_exec npx vite build
}

frontend_tests() {
  require_cmd node
  require_cmd npx
  frontend_exec npx vitest run \
    --coverage \
    --reporter=default \
    --reporter=junit \
    --outputFile.junit="$REPORT_ROOT/frontend/vitest-junit.xml"
  sync_html_coverage_dir "$ROOT/coverage/frontend" "$TESTS_COVERAGE_ROOT/frontend"
}

python_unit() {
  python_pytest \
    "$ROOT/tests/unit" \
    -v \
    --tb=short \
    --junitxml="$REPORT_ROOT/unit/pytest-junit.xml" \
    --cov=app \
    --cov-config="$ROOT/services/api-gateway/.coveragerc" \
    --cov-report=term-missing \
    --cov-report="xml:$ROOT/coverage/python/unit.xml" \
    --cov-report="html:$ROOT/coverage/python/unit-html"
  sync_html_coverage_dir "$ROOT/coverage/python/unit-html" "$TESTS_COVERAGE_ROOT/python/unit"
}

python_integration() {
  require_docker_daemon
  python_pytest \
    "$ROOT/tests/integration" \
    -v \
    --tb=short \
    --junitxml="$REPORT_ROOT/integration/pytest-junit.xml" \
    --cov=app \
    --cov-config="$ROOT/services/api-gateway/.coveragerc" \
    --cov-report=term-missing \
    --cov-report="xml:$ROOT/coverage/python/integration.xml" \
    --cov-report="html:$ROOT/coverage/python/integration-html"
  sync_html_coverage_dir "$ROOT/coverage/python/integration-html" "$TESTS_COVERAGE_ROOT/python/integration"
}

python_integration_keycloak() {
  require_docker_daemon
  python_pytest \
    "$ROOT/tests/integration/test_keycloak_integration.py" \
    "$ROOT/tests/integration/test_keycloak_password_policy.py" \
    -v \
    --tb=short \
    --junitxml="$REPORT_ROOT/integration/keycloak-junit.xml"
}

python_integration_nats() {
  require_docker_daemon
  python_pytest \
    "$ROOT/tests/integration/test_nats_event_flow.py" \
    -v \
    --tb=short \
    --junitxml="$REPORT_ROOT/integration/nats-junit.xml"
}

python_contracts() {
  python_pytest \
    "$ROOT/tests/unit/services/test_session_reaper_contract.py" \
    -v \
    --tb=short \
    --junitxml="$REPORT_ROOT/contracts/python-contracts-junit.xml"
}

go_internal_tests() {
  require_cmd go
  local internal_profile="$ROOT/coverage/orchestrator/orchestrator-internal-k8s.out"
  (
    cd "$ROOT/services/orchestrator"
    GOCACHE="${GOCACHE:-$GO_TEST_CACHE_DEFAULT}" \
      go test ./internal/k8s -count=1 \
      -coverpkg=github.com/hopper/orchestrator/... \
      -coverprofile="$internal_profile" \
      -json | tee "$REPORT_ROOT/orchestrator/go-test.json"
  )
  render_go_html "$internal_profile" "$ROOT/coverage/orchestrator/internal-html" "$ROOT/services/orchestrator"
  sync_html_coverage_dir "$ROOT/coverage/orchestrator/internal-html" "$TESTS_COVERAGE_ROOT/orchestrator/internal"
}

go_contract_tests() {
  require_cmd go
  local contract_profile="$ROOT/coverage/orchestrator/orchestrator-contract.out"
  (
    cd "$ROOT/tests/orchestrator"
    GOCACHE="${GOCACHE:-$GO_TEST_CACHE_DEFAULT}" \
      go test ./... -race -count=1 \
      -coverpkg=github.com/hopper/orchestrator/... \
      -coverprofile="$contract_profile" \
      -json | tee "$REPORT_ROOT/contracts/go-contracts.json"
  )
  render_go_html "$contract_profile" "$ROOT/coverage/orchestrator/contract-html" "$ROOT/services/orchestrator"
  sync_html_coverage_dir "$ROOT/coverage/orchestrator/contract-html" "$TESTS_COVERAGE_ROOT/orchestrator/contract"
}

merge_go_coverage() {
  require_cmd python3
  local out="$ROOT/coverage/orchestrator/orchestrator.out"
  local internal_profile="$ROOT/coverage/orchestrator/orchestrator-internal-k8s.out"
  local contract_profile="$ROOT/coverage/orchestrator/orchestrator-contract.out"

  if [[ -f "$internal_profile" && -f "$contract_profile" ]]; then
    python3 "$ROOT/scripts/test/merge_go_coverprofiles.py" "$out" "$contract_profile" "$internal_profile"
    return 0
  fi

  if [[ -f "$contract_profile" ]]; then
    cp "$contract_profile" "$out"
    return 0
  fi

  if [[ -f "$internal_profile" ]]; then
    cp "$internal_profile" "$out"
    return 0
  fi

  die "No Go coverage profiles available to merge."
}

orchestrator_tests() {
  go_internal_tests
  merge_go_coverage
}

contract_tests() {
  python_contracts
  go_contract_tests
  merge_go_coverage
}

api_migrate() {
  require_cmd poetry
  (
    cd "$ROOT/services/api-gateway"
    # `test-migrate` is paired with docker-compose.test.yml, whose Postgres
    # service uses hopper_test/test. Real-stack callers export
    # HOPPER_DATABASE_URL explicitly before invoking this helper.
    PYTHONPATH="." \
      HOPPER_DATABASE_URL="${HOPPER_DATABASE_URL:-postgresql+asyncpg://hopper_test:test@127.0.0.1:5433/hopper_test}" \
      poetry run alembic -c alembic.ini upgrade head
  )
}

test_services_up() {
  require_docker_daemon
  compose_cmd "$MOCK_COMPOSE_FILE" up -d --build mock-api mock-k8s mock-dcgm postgres nats keycloak
  mock_services_wait
}

test_services_down() {
  require_cmd docker
  collect_compose_logs "$MOCK_COMPOSE_FILE" "mock-services"
  compose_cmd "$MOCK_COMPOSE_FILE" down -v
}

bootstrap_keycloak() {
  require_cmd python3
  local bootstrap_script="$ROOT/scripts/test/bootstrap_keycloak.py"
  [[ -f "$bootstrap_script" ]] || die "Missing bootstrap script: $bootstrap_script"
  python3 "$bootstrap_script"
}

start_background_process() {
  local name=$1
  shift
  mkdir -p "$REAL_STACK_PID_DIR" "$REAL_STACK_LOG_DIR"
  "$@" >"$REAL_STACK_LOG_DIR/$name.log" 2>&1 &
  local pid=$!
  echo "$pid" >"$REAL_STACK_PID_DIR/$name.pid"
}

test_real_stack_up() {
  require_docker_daemon
  require_cmd poetry
  require_cmd pnpm

  local hopper_database_url="postgresql+asyncpg://hopper:hopper_dev@127.0.0.1:5433/hopper"
  local hopper_nats_url="nats://127.0.0.1:4222"
  local hopper_keycloak_url="http://127.0.0.1:8080"
  local hopper_keycloak_external_url="http://127.0.0.1:8080"
  local hopper_keycloak_realm="hopper"
  local hopper_keycloak_client_id="hopper-api"
  local hopper_keycloak_admin_client_id="hopper-admin"
  local hopper_keycloak_admin_client_secret="${HOPPER_KEYCLOAK_ADMIN_CLIENT_SECRET:-hopper-admin-secret}"
  local hopper_frontend_url="http://127.0.0.1:4173"
  local hopper_callback_url="http://127.0.0.1:4173/api/auth/callback"
  local hopper_cors_origins='["http://127.0.0.1:4173"]'

  compose_cmd "$REAL_COMPOSE_FILE" up -d postgres nats keycloak
  real_services_wait
  bootstrap_keycloak
  HOPPER_DATABASE_URL="$hopper_database_url" api_migrate

  start_background_process api-gateway \
    env \
      HOPPER_DATABASE_URL="$hopper_database_url" \
      HOPPER_NATS_URL="$hopper_nats_url" \
      HOPPER_KEYCLOAK_URL="$hopper_keycloak_url" \
      HOPPER_KEYCLOAK_EXTERNAL_URL="$hopper_keycloak_external_url" \
      HOPPER_KEYCLOAK_REALM="$hopper_keycloak_realm" \
      HOPPER_KEYCLOAK_CLIENT_ID="$hopper_keycloak_client_id" \
      HOPPER_KEYCLOAK_ADMIN_CLIENT_ID="$hopper_keycloak_admin_client_id" \
      HOPPER_KEYCLOAK_ADMIN_CLIENT_SECRET="$hopper_keycloak_admin_client_secret" \
      HOPPER_FRONTEND_URL="$hopper_frontend_url" \
      HOPPER_CALLBACK_URL="$hopper_callback_url" \
      HOPPER_CORS_ORIGINS="$hopper_cors_origins" \
      PYTHONPATH="$ROOT/services/api-gateway" \
      poetry --directory "$ROOT/services/api-gateway" run uvicorn app.main:app --host 127.0.0.1 --port 8000

  start_background_process frontend \
    env \
      API_PROXY_TARGET="http://127.0.0.1:8000" \
      API_PROXY_STRIP_PREFIX="true" \
      API_PROXY_SECURE="false" \
      API_INTERNAL_URL="http://127.0.0.1:8000" \
      KEYCLOAK_EXTERNAL_URL="http://127.0.0.1:8080" \
      KEYCLOAK_REALM="hopper" \
      KEYCLOAK_CLIENT_ID="hopper-api" \
      DEV_LOGIN_PASS="" \
      DEV_LOGIN_PASS_ALT="" \
      pnpm --dir "$ROOT/frontend" exec vite dev --host 127.0.0.1 --port 4173

  if http_ready "http://127.0.0.1:8000/readyz" 30 2; then
    echo "Ready: API readiness (http://127.0.0.1:8000/readyz)"
  else
    local api_log="$REAL_STACK_LOG_DIR/api-gateway.log"
    if [[ -f "$api_log" ]]; then
      echo "API gateway startup log:" >&2
      tail -n 200 "$api_log" >&2 || true
    fi
    die "Timed out waiting for API readiness at http://127.0.0.1:8000/readyz"
  fi
  wait_for_http "http://127.0.0.1:4173/login" "frontend login page"
}

test_real_stack_down() {
  collect_real_stack_logs
  kill_pid_file "$REAL_STACK_PID_DIR/frontend.pid"
  kill_pid_file "$REAL_STACK_PID_DIR/api-gateway.pid"
  compose_cmd "$REAL_COMPOSE_FILE" down -v
}

collect_real_stack_logs() {
  mkdir -p "$SERVICE_LOG_DIR" "$REAL_STACK_LOG_DIR"
  collect_compose_logs "$REAL_COMPOSE_FILE" "real-stack-services"
}

e2e_tests() {
  require_cmd node
  require_cmd npx
  E2E_USE_MOCK_SERVER="true" \
  E2E_MANAGE_MOCK_SERVER="${E2E_MANAGE_MOCK_SERVER:-false}" \
  E2E_MANAGE_FRONTEND="true" \
  E2E_TEST_DIR="./specs" \
  PLAYWRIGHT_JUNIT_PATH="$REPORT_ROOT/e2e/playwright-junit.xml" \
    e2e_exec npx playwright test
}

e2e_real_tests() {
  require_cmd node
  require_cmd npx
  [[ -n "${BASE_URL:-}" ]] || die "BASE_URL must point at the stack under test."
  E2E_USE_MOCK_SERVER="${E2E_USE_MOCK_SERVER:-false}" \
  E2E_MANAGE_FRONTEND="${E2E_MANAGE_FRONTEND:-false}" \
  E2E_TEST_DIR="${E2E_TEST_DIR:-./real-stack}" \
  PLAYWRIGHT_JUNIT_PATH="$REPORT_ROOT/e2e/playwright-junit.xml" \
    e2e_exec npx playwright test
}

e2e_real_stack_tests() {
  BASE_URL="${BASE_URL:-http://127.0.0.1:4173}" \
  E2E_USE_MOCK_SERVER="false" \
  E2E_MANAGE_FRONTEND="false" \
  E2E_TEST_DIR="./real-stack" \
  E2E_ADMIN_EMAIL="${E2E_ADMIN_EMAIL:-admin@test.edu}" \
  E2E_ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-e2e-admin}" \
  E2E_PROFESSOR_EMAIL="${E2E_PROFESSOR_EMAIL:-professor@test.edu}" \
  E2E_PROFESSOR_PASSWORD="${E2E_PROFESSOR_PASSWORD:-e2e-professor}" \
  E2E_STUDENT_EMAIL="${E2E_STUDENT_EMAIL:-student-1@test.edu}" \
  E2E_STUDENT_PASSWORD="${E2E_STUDENT_PASSWORD:-e2e-student}" \
    e2e_real_tests
}

load_smoke() {
  require_cmd k6
  BASE_URL="${BASE_URL:-http://127.0.0.1:8000}" \
  ACCESS_TOKEN="${ACCESS_TOKEN:-e2e-student-1}" \
    k6 run \
      --summary-export "$REPORT_ROOT/load/class-start-summary.json" \
      "$ROOT/tests/load/class-start.js"
}

load_full() {
  require_cmd k6
  BASE_URL="${BASE_URL:-http://127.0.0.1:8000}" \
  ACCESS_TOKEN="${ACCESS_TOKEN:-e2e-student-1}" \
    k6 run \
      --summary-export "$REPORT_ROOT/load/scenarios-summary.json" \
      "$ROOT/tests/load/scenarios.js"
}

load_stress() {
  K6_CLASS_START_VUS="${K6_CLASS_START_VUS:-20}" \
  K6_CLASS_START_ITERATIONS="${K6_CLASS_START_ITERATIONS:-20}" \
  K6_SPIKE_PEAK_VUS="${K6_SPIKE_PEAK_VUS:-60}" \
  K6_SPIKE_UP_DURATION="${K6_SPIKE_UP_DURATION:-30s}" \
  K6_SPIKE_HOLD_DURATION="${K6_SPIKE_HOLD_DURATION:-60s}" \
  K6_SPIKE_DOWN_DURATION="${K6_SPIKE_DOWN_DURATION:-30s}" \
    load_full
}

load_spike() {
  K6_CLASS_START_VUS="${K6_CLASS_START_VUS:-8}" \
  K6_CLASS_START_ITERATIONS="${K6_CLASS_START_ITERATIONS:-8}" \
  K6_SPIKE_PEAK_VUS="${K6_SPIKE_PEAK_VUS:-80}" \
  K6_SPIKE_UP_DURATION="${K6_SPIKE_UP_DURATION:-15s}" \
  K6_SPIKE_HOLD_DURATION="${K6_SPIKE_HOLD_DURATION:-20s}" \
  K6_SPIKE_DOWN_DURATION="${K6_SPIKE_DOWN_DURATION:-15s}" \
    load_full
}

load_soak() {
  K6_CLASS_START_VUS="${K6_CLASS_START_VUS:-4}" \
  K6_CLASS_START_ITERATIONS="${K6_CLASS_START_ITERATIONS:-4}" \
  K6_METRICS_VUS="${K6_METRICS_VUS:-10}" \
  K6_METRICS_DURATION="${K6_METRICS_DURATION:-3m}" \
  K6_BILLING_VUS="${K6_BILLING_VUS:-8}" \
  K6_BILLING_DURATION="${K6_BILLING_DURATION:-3m}" \
  K6_SPIKE_PEAK_VUS="${K6_SPIKE_PEAK_VUS:-12}" \
  K6_SPIKE_UP_DURATION="${K6_SPIKE_UP_DURATION:-20s}" \
  K6_SPIKE_HOLD_DURATION="${K6_SPIKE_HOLD_DURATION:-40s}" \
  K6_SPIKE_DOWN_DURATION="${K6_SPIKE_DOWN_DURATION:-20s}" \
    load_full
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

render_coverage_report() {
  require_cmd python3
  merge_go_coverage
  require_cmd go
  render_go_html "$ROOT/coverage/orchestrator/orchestrator.out" "$ROOT/coverage/orchestrator/merged-html" "$ROOT/services/orchestrator"
  sync_html_coverage_dir "$ROOT/coverage/orchestrator/merged-html" "$TESTS_COVERAGE_ROOT/orchestrator/merged"
  python3 "$ROOT/scripts/test/generate_coverage_report.py"
}

coverage_all() {
  frontend_tests
  python_unit
  python_integration
  contract_tests
  orchestrator_tests
  render_coverage_report
}

test_all() {
  frontend_validate
  frontend_tests
  python_unit
  contract_tests
  orchestrator_tests
}

test_ci() {
  frontend_validate
  frontend_tests
  python_unit
  contract_tests
  orchestrator_tests
  python_integration
}

clean_outputs() {
  rm -rf \
    "$ROOT/coverage" \
    "$ROOT/test-results" \
    "$ROOT/.cache/go-test" \
    "$PLAYWRIGHT_OUTPUT_DIR" \
    "$PLAYWRIGHT_REPORT_DIR"
}

show_help() {
  cat <<'EOF'
Usage: scripts/test/run.sh <command>

Public commands:
  test-unit              Run Python unit tests with coverage + JUnit output
  test-integration       Run Python integration tests with coverage + JUnit output
  test-integration-keycloak Run real Keycloak-focused integration tests
  test-integration-nats  Run real NATS event-flow integration tests
  test-frontend          Run frontend Vitest with coverage + JUnit output
  test-orchestrator      Run Go orchestrator internal tests with coverage
  test-contract          Run Python and Go contract suites
  test-migrate           Run Alembic migrations against the configured database
  test-e2e               Run mock-backed Playwright E2E
  test-e2e-real          Run Playwright against an already running real stack
  test-e2e-real-stack    Run the dedicated real-stack Playwright suite
  test-load-smoke        Run the bounded k6 smoke scenario
  test-load              Run the bounded multi-scenario k6 suite
  test-load-stress       Run the higher-intensity bounded stress profile
  test-load-spike        Run the spike-oriented bounded load profile
  test-load-soak         Run the bounded soak profile
  test-security          Validate security scripts and optionally execute live checks
  test-chaos             Validate chaos scripts and optionally execute live invariants
  test-coverage          Run coverage-producing suites and rebuild REPORT.md
  test-coverage-report   Rebuild tests/coverage/REPORT.md from existing artifacts
  test-services-up       Start deterministic mock-backed services and wait for readiness
  test-services-down     Stop deterministic mock-backed services and capture logs
  test-service-logs      Capture mock-stack compose logs
  test-real-stack-up     Start real infra, bootstrap Keycloak, migrate DB, and run API/frontend
  test-real-stack-down   Stop real-stack processes, capture logs, and tear down infra
  test-real-stack-logs   Capture real-stack service logs
  test-all               Run the local fast-path validation
  test-ci                Run the CI-oriented validation path
  test-clean             Remove generated coverage, reports, logs, and caches
  help                   Show this help output

Internal commands used by CI:
  frontend-validate      Run frontend lint, typecheck, and production build
EOF
}

command_name="${1:-help}"

case "$command_name" in
  test-unit) python_unit ;;
  test-integration) python_integration ;;
  test-integration-keycloak) python_integration_keycloak ;;
  test-integration-nats) python_integration_nats ;;
  test-frontend) frontend_tests ;;
  test-orchestrator) orchestrator_tests ;;
  test-contract) contract_tests ;;
  test-migrate) api_migrate ;;
  test-e2e) e2e_tests ;;
  test-e2e-real) e2e_real_tests ;;
  test-e2e-real-stack) e2e_real_stack_tests ;;
  test-load-smoke) load_smoke ;;
  test-load) load_full ;;
  test-load-stress) load_stress ;;
  test-load-spike) load_spike ;;
  test-load-soak) load_soak ;;
  test-security) security_checks ;;
  test-chaos) chaos_checks ;;
  test-coverage) coverage_all ;;
  test-coverage-report) render_coverage_report ;;
  test-services-up) test_services_up ;;
  test-services-down) test_services_down ;;
  test-service-logs) collect_compose_logs "$MOCK_COMPOSE_FILE" "mock-services" ;;
  test-real-stack-up) test_real_stack_up ;;
  test-real-stack-down) test_real_stack_down ;;
  test-real-stack-logs) collect_real_stack_logs ;;
  test-all) test_all ;;
  test-ci) test_ci ;;
  test-clean) clean_outputs ;;
  frontend-validate) frontend_validate ;;
  help|--help|-h) show_help ;;
  *) die "Unknown command: $command_name (run 'scripts/test/run.sh help')" ;;
esac
