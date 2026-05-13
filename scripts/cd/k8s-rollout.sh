#!/usr/bin/env bash
# Roll out new images to an existing Hopper namespace (k3s / kubectl).
# Requires kubectl configured (KUBECONFIG or ~/.kube/config).
#
# If you see discovery errors ("could not find the requested resource" on /api),
# your PATH kubectl may not match the cluster (common on k3s). Use the cluster binary:
#   export KUBECTL="k3s kubectl"
# or set repo variable VPS_KUBECTL=k3s kubectl when deploying from GitHub Actions.
#
# Usage:
#   export NAMESPACE=hopper
#   export API_IMAGE=ghcr.io/org/hopper-api-gateway:abc123
#   export ORCHESTRATOR_IMAGE=ghcr.io/org/hopper-orchestrator:abc123
#   export FRONTEND_IMAGE=ghcr.io/org/hopper-frontend:abc123
#   ./scripts/cd/k8s-rollout.sh
#
# For registry-backed clusters, imagePullPolicy is set to IfNotPresent.
# Local k3s with imported images often uses imagePullPolicy: Never in manifests;
# this script patches deployments to IfNotPresent when USE_REGISTRY=1 (auto if the
# image hostname looks like a registry, e.g. ghcr.io/...).
set -euo pipefail

# Optional: multi-word OK, e.g. KUBECTL="k3s kubectl"
kube() {
  if [[ -n "${KUBECTL:-}" ]]; then
    # shellcheck disable=SC2086
    $KUBECTL "$@"
  else
    kubectl "$@"
  fi
}

NAMESPACE="${NAMESPACE:-hopper}"
ROLL_TIMEOUT="${ROLL_TIMEOUT:-300s}"

if [[ -z "${API_IMAGE:-}" || -z "${ORCHESTRATOR_IMAGE:-}" || -z "${FRONTEND_IMAGE:-}" ]]; then
  echo "Set API_IMAGE, ORCHESTRATOR_IMAGE, and FRONTEND_IMAGE to full image references (with tag)." >&2
  exit 1
fi

USE_REGISTRY="${USE_REGISTRY:-}"
if [[ -z "$USE_REGISTRY" ]]; then
  reg_host="${API_IMAGE%%/*}"
  if [[ "$reg_host" == *.* ]]; then
    USE_REGISTRY=1
  fi
fi

patch_pull_policy() {
  local dep="$1"
  kube patch deployment "$dep" -n "$NAMESPACE" --type='json' \
    -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/imagePullPolicy", "value": "IfNotPresent"}]'
}

echo "Namespace: $NAMESPACE"
echo "API:           $API_IMAGE"
echo "Orchestrator: $ORCHESTRATOR_IMAGE"
echo "Frontend:     $FRONTEND_IMAGE"
if [[ -n "${KUBECTL:-}" ]]; then
  echo "KUBECTL:       $KUBECTL"
else
  echo "KUBECTL:       kubectl (set KUBECTL='k3s kubectl' if discovery fails)"
fi

if ! kube get namespace "$NAMESPACE" &>/dev/null; then
  echo "error: cannot list/get namespace '$NAMESPACE' — wrong kubeconfig, wrong kubectl, or API not Kubernetes." >&2
  echo "  Try: kubectl version; which kubectl; (on k3s) sudo k3s kubectl version" >&2
  kube get namespace "$NAMESPACE" || true
  exit 1
fi

if [[ "$USE_REGISTRY" == "1" ]]; then
  echo "Patching imagePullPolicy -> IfNotPresent (registry deploy)"
  patch_pull_policy api-gateway
  patch_pull_policy orchestrator
  patch_pull_policy frontend
fi

kube set image deployment/api-gateway api-gateway="$API_IMAGE" -n "$NAMESPACE"
kube set image deployment/orchestrator orchestrator="$ORCHESTRATOR_IMAGE" -n "$NAMESPACE"
kube set image deployment/frontend frontend="$FRONTEND_IMAGE" -n "$NAMESPACE"

kube rollout status deployment/api-gateway -n "$NAMESPACE" --timeout="$ROLL_TIMEOUT"
kube rollout status deployment/orchestrator -n "$NAMESPACE" --timeout="$ROLL_TIMEOUT"
kube rollout status deployment/frontend -n "$NAMESPACE" --timeout="$ROLL_TIMEOUT"

echo "Rollout complete."
