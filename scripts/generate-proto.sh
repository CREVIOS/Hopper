#!/usr/bin/env bash
set -euo pipefail

echo "=== Generating Protobuf Stubs ==="

PROTO_DIR="proto"
GEN_DIR="proto/gen"
GO_OUT="services/orchestrator/api/proto"

# Clean generated directories
rm -rf "$GEN_DIR" "$GO_OUT"
mkdir -p "$GEN_DIR/python" "$GEN_DIR/go" "$GO_OUT"

# Check for buf or protoc
if command -v buf >/dev/null 2>&1; then
  echo "Using buf for code generation..."
  cd "$PROTO_DIR"
  buf generate
  cd ..
else
  echo "Using protoc for code generation..."
  command -v protoc >/dev/null 2>&1 || { echo "protoc is required. Install from https://grpc.io/docs/protoc-installation/"; exit 1; }

  # Generate Python stubs
  python -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$GEN_DIR/python" \
    --grpc_python_out="$GEN_DIR/python" \
    --pyi_out="$GEN_DIR/python" \
    "$PROTO_DIR"/hopper/pod/v1/pod.proto \
    "$PROTO_DIR"/hopper/billing/v1/billing.proto

  # Generate Go stubs
  protoc \
    -I"$PROTO_DIR" \
    --go_out="$GO_OUT" --go_opt=paths=source_relative \
    --go-grpc_out="$GO_OUT" --go-grpc_opt=paths=source_relative \
    "$PROTO_DIR"/hopper/pod/v1/pod.proto \
    "$PROTO_DIR"/hopper/billing/v1/billing.proto
fi

echo "Proto stubs generated successfully."
