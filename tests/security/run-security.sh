#!/usr/bin/env bash
set -euo pipefail

: "${BASE_URL:?Set BASE_URL to the staging API URL}"
: "${STUDENT_TOKEN:?Set STUDENT_TOKEN to a staging student JWT}"
: "${ADMIN_TOKEN:?Set ADMIN_TOKEN to a staging admin JWT}"
: "${OTHER_STUDENT_POD_ID:?Set OTHER_STUDENT_POD_ID to a pod owned by another student}"

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
failures=0

expect_status() {
  local name=$1 expected=$2
  shift 2
  local actual
  actual=$(curl --silent --output /dev/null --write-out '%{http_code}' "$@")
  if [[ "$actual" != "$expected" ]]; then
    echo "FAIL: $name expected=$expected actual=$actual" >&2
    failures=$((failures + 1))
  else
    echo "PASS: $name"
  fi
}

expect_rejected_manifest() {
  local manifest=$1
  if kubectl apply --dry-run=server -f "$manifest" >/dev/null 2>&1; then
    echo "FAIL: admission accepted $(basename "$manifest")" >&2
    failures=$((failures + 1))
  else
    echo "PASS: admission rejected $(basename "$manifest")"
  fi
}

expect_rejected_manifest "$ROOT/manifests/hostpath-pod.yaml"
expect_rejected_manifest "$ROOT/manifests/privileged-pod.yaml"
expect_rejected_manifest "$ROOT/manifests/hostnetwork-pod.yaml"

expect_status "API without token" 401 -X GET "$BASE_URL/pods/"
expect_status "student blocked from admin" 403 \
  -H "Authorization: Bearer $STUDENT_TOKEN" "$BASE_URL/admin/users"
expect_status "cross-tenant pod access" 403 \
  -H "Authorization: Bearer $STUDENT_TOKEN" "$BASE_URL/pods/$OTHER_STUDENT_POD_ID"
expect_status "invalid token" 401 \
  -H "Authorization: Bearer invalid.jwt.value" "$BASE_URL/pods/"
expect_status "admin endpoint accepts admin" 200 \
  -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE_URL/admin/users"

"$ROOT/test-network-isolation.sh"

if [[ "${RUN_GPU_SECURITY_TESTS:-false}" == "true" ]]; then
  "$ROOT/test-gpu-isolation.sh"
else
  echo "SKIP: GPU security checks (set RUN_GPU_SECURITY_TESTS=true)"
fi

if (( failures > 0 )); then
  echo "$failures security checks failed" >&2
  exit 1
fi

