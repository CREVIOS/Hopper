#!/usr/bin/env bash
# Local / CI parity wrapper around scripts/test/run.sh.
# Usage: ./scripts/ci/run-all.sh [--integration]
#   --integration  Include container-backed Python integration tests
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

"$ROOT/scripts/test/run.sh" frontend-validate
"$ROOT/scripts/test/run.sh" test-frontend
"$ROOT/scripts/test/run.sh" test-unit
"$ROOT/scripts/test/run.sh" test-contract
"$ROOT/scripts/test/run.sh" test-orchestrator

if [[ "$RUN_INTEGRATION" == true ]]; then
  "$ROOT/scripts/test/run.sh" test-integration
fi

echo "==> CI checks finished OK"
