#!/usr/bin/env bash
set -euo pipefail

: "${GPU_TEST_NAMESPACE:?Set GPU_TEST_NAMESPACE}"
: "${GPU_TEST_POD:?Set GPU_TEST_POD}"

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

kubectl cp "$ROOT/gpu_memory_isolation.py" \
  "$GPU_TEST_NAMESPACE/$GPU_TEST_POD:/tmp/gpu_memory_isolation.py"
kubectl exec -n "$GPU_TEST_NAMESPACE" "$GPU_TEST_POD" -- \
  python /tmp/gpu_memory_isolation.py

kubectl exec -n "$GPU_TEST_NAMESPACE" "$GPU_TEST_POD" -- \
  sh -c 'test "${CUDA_DEVICE_MEMORY_CLEANUP:-}" = "1"'

runtime_class=$(kubectl get pod -n "$GPU_TEST_NAMESPACE" "$GPU_TEST_POD" \
  -o jsonpath='{.spec.runtimeClassName}')
test "$runtime_class" = "gvisor"

# MIG-capable staging nodes must expose exactly the assigned device to the pod.
visible_devices=$(kubectl exec -n "$GPU_TEST_NAMESPACE" "$GPU_TEST_POD" -- \
  nvidia-smi --query-gpu=uuid --format=csv,noheader | wc -l | tr -d ' ')
test "$visible_devices" = "1"

kubectl cp "$ROOT/vram_overallocation.py" \
  "$GPU_TEST_NAMESPACE/$GPU_TEST_POD:/tmp/vram_overallocation.py"
if kubectl exec -n "$GPU_TEST_NAMESPACE" "$GPU_TEST_POD" -- \
  python /tmp/vram_overallocation.py; then
  echo "FAIL: VRAM overallocation succeeded" >&2
  exit 1
fi
echo "PASS: VRAM overallocation was blocked"
