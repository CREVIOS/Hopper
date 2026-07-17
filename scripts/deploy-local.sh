#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- PID tracking for cleanup ---
PIDS=()
INFRA_STARTED=false

cleanup() {
  echo ""
  echo -e "${YELLOW}Shutting down...${NC}"

  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  # Wait briefly for processes to exit
  for pid in "${PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done

  if [ "$INFRA_STARTED" = true ]; then
    echo -e "${CYAN}Stopping infrastructure containers...${NC}"
    docker compose down
  fi

  echo -e "${GREEN}All services stopped.${NC}"
  exit 0
}

trap cleanup SIGINT SIGTERM

# --- Helpers ---
log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[x]${NC} $1"; }
step() { echo -e "\n${BOLD}${CYAN}=== $1 ===${NC}"; }

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    err "$1 is required but not installed."
    echo "    $2"
    return 1
  fi
}

# --- Parse args ---
SKIP_INSTALL=false
SKIP_MIGRATE=false
INFRA_ONLY=false
APP_ONLY=false

usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --skip-install    Skip dependency installation"
  echo "  --skip-migrate    Skip database migrations"
  echo "  --infra-only      Only start infrastructure (Postgres, NATS, Keycloak)"
  echo "  --app-only        Only start app services (assumes infra is running)"
  echo "  -h, --help        Show this help message"
  exit 0
}

for arg in "$@"; do
  case $arg in
    --skip-install)  SKIP_INSTALL=true ;;
    --skip-migrate)  SKIP_MIGRATE=true ;;
    --infra-only)    INFRA_ONLY=true ;;
    --app-only)      APP_ONLY=true ;;
    -h|--help)       usage ;;
    *) err "Unknown option: $arg"; usage ;;
  esac
done

# --- Prereq checks ---
step "Checking prerequisites"
MISSING=false

check_cmd docker    "Install from https://docs.docker.com/get-docker/"   || MISSING=true
check_cmd pnpm     "Install: npm i -g pnpm"                              || MISSING=true
check_cmd poetry   "Install: pip install poetry"                          || MISSING=true
check_cmd go       "Install from https://go.dev/dl/"                      || MISSING=true

if [ "$MISSING" = true ]; then
  err "Missing prerequisites. Install them and try again."
  exit 1
fi

log "All prerequisites found."

# --- Infrastructure ---
if [ "$APP_ONLY" = false ]; then
  step "Starting infrastructure"

  log "Starting Postgres, NATS, Keycloak via Docker Compose..."
  docker compose up -d
  INFRA_STARTED=true

  log "Waiting for PostgreSQL to be ready..."
  RETRIES=30
  until docker compose exec -T postgres pg_isready -U hopper > /dev/null 2>&1; do
    RETRIES=$((RETRIES - 1))
    if [ "$RETRIES" -le 0 ]; then
      err "PostgreSQL did not become ready in time."
      exit 1
    fi
    sleep 1
  done
  log "PostgreSQL is ready."

  log "Waiting for NATS to be ready..."
  RETRIES=20
  until docker compose exec -T nats nats-server --help > /dev/null 2>&1 && nc -z localhost 4222 2>/dev/null; do
    RETRIES=$((RETRIES - 1))
    if [ "$RETRIES" -le 0 ]; then
      err "NATS did not become ready in time."
      exit 1
    fi
    sleep 1
  done
  log "NATS is ready."

  log "Waiting for Keycloak to be ready..."
  RETRIES=60
  until curl -sf http://localhost:9000/health/ready > /dev/null 2>&1; do
    RETRIES=$((RETRIES - 1))
    if [ "$RETRIES" -le 0 ]; then
      warn "Keycloak management health endpoint did not become ready."
      warn "Continuing anyway — Keycloak can take a while on first launch."
      break
    fi
    sleep 2
  done
  if [ "$RETRIES" -gt 0 ]; then
    log "Keycloak is ready."
  fi

  if [ "$INFRA_ONLY" = true ]; then
    echo ""
    echo -e "${GREEN}${BOLD}Infrastructure is running.${NC}"
    echo ""
    echo "  Postgres:  localhost:5433  (user: hopper / pass: hopper_dev / db: hopper)"
    echo "  NATS:      localhost:4222  (monitoring: http://localhost:8222)"
    echo "  Keycloak:  http://localhost:8080  (admin / admin)"
    echo ""
    echo "Press Ctrl+C to stop."
    wait
  fi
fi

# --- Install dependencies ---
if [ "$SKIP_INSTALL" = false ]; then
  step "Installing dependencies"

  log "Frontend (pnpm)..."
  (cd frontend && pnpm install --frozen-lockfile 2>/dev/null || pnpm install)

  log "API Gateway (poetry)..."
  (cd services/api-gateway && poetry install --no-interaction)

  log "Orchestrator (go mod)..."
  (cd services/orchestrator && go mod download)

  log "Dependencies installed."
fi

# --- Database migrations ---
if [ "$SKIP_MIGRATE" = false ]; then
  step "Running database migrations"
  (cd services/api-gateway && PYTHONPATH=. poetry run alembic upgrade head)
  log "Migrations complete."
fi

# --- Start application services ---
step "Starting application services"

# Log directory
LOG_DIR="$ROOT_DIR/.local-logs"
mkdir -p "$LOG_DIR"

# Frontend (SvelteKit)
log "Starting frontend on :5173..."
(cd frontend && pnpm dev) > "$LOG_DIR/frontend.log" 2>&1 &
PIDS+=($!)

# API Gateway (FastAPI)
log "Starting API gateway on :8000..."
(cd services/api-gateway && poetry run uvicorn app.main:app --reload --port 8000 --host 0.0.0.0) > "$LOG_DIR/api-gateway.log" 2>&1 &
PIDS+=($!)

# Orchestrator (Go)
log "Starting orchestrator..."
(cd services/orchestrator && go run ./cmd/orchestrator/) > "$LOG_DIR/orchestrator.log" 2>&1 &
PIDS+=($!)

# --- Wait for app services to start ---
sleep 3

# --- Print status ---
echo ""
echo -e "${BOLD}${GREEN}============================================${NC}"
echo -e "${BOLD}${GREEN}  Hopper is running locally${NC}"
echo -e "${BOLD}${GREEN}============================================${NC}"
echo ""
echo -e "  ${BOLD}Frontend:${NC}      http://localhost:5173"
echo -e "  ${BOLD}API Gateway:${NC}   http://localhost:8000"
echo -e "  ${BOLD}API Docs:${NC}      http://localhost:8000/docs"
echo -e "  ${BOLD}Keycloak:${NC}      http://localhost:8080  (admin / admin)"
echo -e "  ${BOLD}PostgreSQL:${NC}    localhost:5433  (hopper / hopper_dev)"
echo -e "  ${BOLD}NATS:${NC}          localhost:4222"
echo -e "  ${BOLD}NATS Monitor:${NC}  http://localhost:8222"
echo ""
echo -e "  ${CYAN}Logs:${NC}  tail -f $LOG_DIR/*.log"
echo ""
echo -e "  Press ${BOLD}Ctrl+C${NC} to stop all services."
echo ""

# --- Wait for any child to exit ---
while true; do
  for i in "${!PIDS[@]}"; do
    pid="${PIDS[$i]}"
    if ! kill -0 "$pid" 2>/dev/null; then
      SERVICE="unknown"
      case $i in
        0) SERVICE="Frontend" ;;
        1) SERVICE="API Gateway" ;;
        2) SERVICE="Orchestrator" ;;
      esac
      warn "$SERVICE (PID $pid) exited. Check logs: $LOG_DIR/"
      # Remove dead PID
      unset 'PIDS[$i]'
    fi
  done

  # If all processes died, exit
  if [ ${#PIDS[@]} -eq 0 ]; then
    err "All application services have exited."
    cleanup
  fi

  sleep 2
done
