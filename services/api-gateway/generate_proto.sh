#!/usr/bin/env bash
# Generate Python gRPC stubs from proto files.
# Run from the api-gateway directory: bash generate_proto.sh
set -euo pipefail

PROTO_ROOT="$(cd "$(dirname "$0")/../../proto" && pwd)"
OUT_DIR="$(cd "$(dirname "$0")/app/proto" && pwd)"

python -m grpc_tools.protoc \
  --proto_path="$PROTO_ROOT" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  hopper/pod/v1/pod.proto \
  hopper/billing/v1/billing.proto

# Fix relative imports in generated files
find "$OUT_DIR" -name '*_pb2_grpc.py' -exec sed -i 's/^from hopper\./from app.proto.hopper./g' {} +
find "$OUT_DIR" -name '*_pb2.py' -exec sed -i 's/^from hopper\./from app.proto.hopper./g' {} +

echo "Proto stubs generated in $OUT_DIR"
