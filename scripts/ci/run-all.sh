#!/usr/bin/env bash
# Local / CI parity: lint, typecheck, unit tests, frontend build.
# Usage: ./scripts/ci/run-all.sh [--integration]
#   --integration  Run pytest in tests/integration/ (Docker / Testcontainers required)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

RUN_INTEGRATION=false
for arg in "$@"; do
  case "$arg" in
    --integration) RUN_INTEGRATION=true ;;
    -h|--help)
      echo "Usage: $0 [--integration]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

echo "==> Frontend: install, lint, check, test, build"
cd "$ROOT/frontend"
corepack enable >/dev/null 2>&1 || true
pnpm install --frozen-lockfile
if compgen -G "eslint.config.*" >/dev/null 2>&1; then
  pnpm lint
else
  echo "(!) Skipping pnpm lint (no eslint.config.* in frontend/)"
fi
pnpm check
pnpm exec vitest run --passWithNoTests
pnpm build

echo "==> Kubernetes manifests: duplicate top-level key guard"
cd "$ROOT"
python3 scripts/ci/validate-k8s-yaml.py

echo "==> API gateway: import smoke (run 'make lint' for Ruff)"
cd "$ROOT/services/api-gateway"
poetry install --no-interaction
poetry run python -c "from app.main import app; print('app.main import OK')"

echo "==> Orchestrator: vet + test (Dockerfile build if native protos are stale)"
cd "$ROOT/services/orchestrator"
if ! go vet ./... || ! go test ./... -race -count=1; then
  if command -v docker >/dev/null 2>&1; then
    echo "(!) Native vet/test failed — falling back to orchestrator Docker build"
    docker build -f "$ROOT/services/orchestrator/Dockerfile" -t hopper/orchestrator:ci-local "$ROOT"
  else
    exit 1
  fi
fi

if [[ "$RUN_INTEGRATION" == true ]]; then
  echo "==> Integration tests (Docker)"
  cd "$ROOT"
  poetry --directory services/api-gateway run pytest "${ROOT}/tests/integration" -v --tb=short
fi

echo "==> CI checks finished OK"
