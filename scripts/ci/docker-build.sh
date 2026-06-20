#!/usr/bin/env bash
# Build Hopper service images. Run from repository root.
# Usage:
#   TAG=latest ./scripts/ci/docker-build.sh
#   TAG=$(git rev-parse --short HEAD) REGISTRY=ghcr.io/myorg ./scripts/ci/docker-build.sh
#
# When REGISTRY is set, images are tagged as:
#   ${REGISTRY}/hopper-api-gateway:${TAG}
#   ${REGISTRY}/hopper-orchestrator:${TAG}
#   ${REGISTRY}/hopper-frontend:${TAG}
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

TAG="${TAG:-latest}"
REGISTRY="${REGISTRY:-}"

if [[ -n "$REGISTRY" ]]; then
  REGISTRY="${REGISTRY%/}"
  API_IMG="${REGISTRY}/hopper-api-gateway:${TAG}"
  ORCH_IMG="${REGISTRY}/hopper-orchestrator:${TAG}"
  FE_IMG="${REGISTRY}/hopper-frontend:${TAG}"
else
  API_IMG="hopper/api-gateway:${TAG}"
  ORCH_IMG="hopper/orchestrator:${TAG}"
  FE_IMG="hopper/frontend:${TAG}"
fi

echo "Building API gateway -> $API_IMG"
docker build -f services/api-gateway/Dockerfile -t "$API_IMG" .

echo "Building orchestrator -> $ORCH_IMG"
docker build -f services/orchestrator/Dockerfile -t "$ORCH_IMG" .

echo "Building frontend -> $FE_IMG"
docker build -f frontend/Dockerfile -t "$FE_IMG" frontend/

echo "Done. Images:"
echo "  $API_IMG"
echo "  $ORCH_IMG"
echo "  $FE_IMG"

if [[ "${DOCKER_PUSH:-}" == "1" ]]; then
  docker push "$API_IMG"
  docker push "$ORCH_IMG"
  docker push "$FE_IMG"
fi
