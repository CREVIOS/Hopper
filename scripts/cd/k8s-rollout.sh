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
#   export ROLL_TIMEOUT=900s   # optional; default 900s (GHCR pulls on small nodes can exceed 5m)
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
ROLL_TIMEOUT="${ROLL_TIMEOUT:-900s}"

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
echo "Rollout timeout per deployment: $ROLL_TIMEOUT"
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

# --------------------------------------------------------------------------- #
# Pre-rollout migrations
#
# Run `alembic upgrade head` with the NEW api-gateway image BEFORE swapping any
# deployment image. Migrations are additive (expand-first), so the currently
# running old pods keep serving against the new schema during the window; only
# once the schema is in place do we roll the code that depends on it. If the
# migration fails we exit here WITHOUT touching images — the old app keeps
# running, unmigrated but intact.
#
# Set SKIP_MIGRATIONS=1 to bypass (e.g. a code-only hotfix on a busy DB).
# --------------------------------------------------------------------------- #
if [[ "${SKIP_MIGRATIONS:-0}" != "1" ]]; then
  echo "Running database migrations (alembic upgrade head) with $API_IMAGE"

  # NetworkPolicies so the Job pod can reach Postgres through the default-deny
  # mesh — identical to k8s/deploy/07-migrate.yaml, embedded so a CD run piped
  # over SSH doesn't need the repo checked out on the host.
  kube apply -n "$NAMESPACE" -f - <<'NETPOL'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-db-migrate-egress
spec:
  podSelector: { matchLabels: { app: db-migrate } }
  policyTypes: ["Egress"]
  egress:
    - to: [{ podSelector: { matchLabels: { app: postgres } } }]
      ports: [{ protocol: TCP, port: 5432 }]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-postgres-from-db-migrate
spec:
  podSelector: { matchLabels: { app: postgres } }
  policyTypes: ["Ingress"]
  ingress:
    - from: [{ podSelector: { matchLabels: { app: db-migrate } } }]
      ports: [{ protocol: TCP, port: 5432 }]
NETPOL

  # Fresh Job each deploy (a completed Job with the same name blocks re-create).
  kube delete job db-migrate -n "$NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true
  kube apply -n "$NAMESPACE" -f - <<JOB
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migrate
spec:
  backoffLimit: 1
  activeDeadlineSeconds: 600
  ttlSecondsAfterFinished: 600
  template:
    metadata:
      labels: { app: db-migrate }
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: ${API_IMAGE}
          imagePullPolicy: IfNotPresent
          workingDir: /app
          command: ["sh", "-ec", "PYTHONPATH=/app alembic upgrade head"]
          env:
            - name: HOPPER_DATABASE_URL
              valueFrom:
                secretKeyRef: { name: hopper-db, key: database-url }
          resources:
            requests: { cpu: "50m", memory: "128Mi" }
            limits: { cpu: "500m", memory: "512Mi" }
JOB

  # Poll for complete OR failed (kube wait handles only one condition and would
  # otherwise hang the full timeout on a failed migration).
  migrate_ok=""
  for _ in $(seq 1 120); do
    if [[ "$(kube get job db-migrate -n "$NAMESPACE" -o jsonpath='{.status.succeeded}' 2>/dev/null)" == "1" ]]; then
      migrate_ok=1; break
    fi
    if [[ "$(kube get job db-migrate -n "$NAMESPACE" -o jsonpath='{.status.failed}' 2>/dev/null)" =~ ^[1-9] ]]; then
      break
    fi
    sleep 5
  done
  if [[ "$migrate_ok" != "1" ]]; then
    echo "error: database migration failed/timed out — NOT rolling images (old app stays up)." >&2
    kube logs job/db-migrate -n "$NAMESPACE" --tail=60 2>/dev/null || true
    exit 1
  fi
  echo "Migrations applied. Logs:"
  kube logs job/db-migrate -n "$NAMESPACE" --tail=20 2>/dev/null || true
fi

kube set image deployment/api-gateway api-gateway="$API_IMAGE" -n "$NAMESPACE"
kube set image deployment/orchestrator orchestrator="$ORCHESTRATOR_IMAGE" -n "$NAMESPACE"
kube set image deployment/frontend frontend="$FRONTEND_IMAGE" -n "$NAMESPACE"

kube rollout status deployment/api-gateway -n "$NAMESPACE" --timeout="$ROLL_TIMEOUT"
kube rollout status deployment/orchestrator -n "$NAMESPACE" --timeout="$ROLL_TIMEOUT"
kube rollout status deployment/frontend -n "$NAMESPACE" --timeout="$ROLL_TIMEOUT"

echo "Rollout complete."
