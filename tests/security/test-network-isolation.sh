#!/usr/bin/env bash
set -euo pipefail

: "${STUDENT_NAMESPACE_A:?Set STUDENT_NAMESPACE_A}"
: "${STUDENT_NAMESPACE_B:?Set STUDENT_NAMESPACE_B}"
: "${STUDENT_POD_A:?Set STUDENT_POD_A}"
: "${STUDENT_POD_B_IP:?Set STUDENT_POD_B_IP}"
: "${NATS_SERVICE_IP:?Set NATS_SERVICE_IP}"
: "${POSTGRES_SERVICE_IP:?Set POSTGRES_SERVICE_IP}"

exec_in_student_pod() {
  kubectl exec -n "$STUDENT_NAMESPACE_A" "$STUDENT_POD_A" -- "$@"
}

expect_blocked() {
  local name=$1
  shift
  if exec_in_student_pod timeout 5 "$@" >/dev/null 2>&1; then
    echo "FAIL: $name was reachable" >&2
    return 1
  fi
  echo "PASS: $name blocked"
}

expect_allowed() {
  local name=$1
  shift
  if ! exec_in_student_pod timeout 10 "$@" >/dev/null 2>&1; then
    echo "FAIL: $name was blocked" >&2
    return 1
  fi
  echo "PASS: $name allowed"
}

expect_blocked "cross-namespace pod" curl -fsS "http://$STUDENT_POD_B_IP"
expect_blocked "Kubernetes control plane" curl -kfsS "https://kubernetes.default.svc"
expect_blocked "NATS internal service" sh -c "nc -z -w 3 '$NATS_SERVICE_IP' 4222"
expect_blocked "PostgreSQL internal service" sh -c "nc -z -w 3 '$POSTGRES_SERVICE_IP' 5432"
expect_allowed "kube-dns resolution" getent hosts kubernetes.default.svc
expect_allowed "HTTPS internet egress" curl -fsS https://pypi.org/

