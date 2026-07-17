#!/usr/bin/env bash
# Stage the VM template images as tarballs for a registry-less node join.
#
# Run this on a machine that HAS the images built locally (e.g. after
# `make vm-images`). It writes one <name>.tar per image into OUT_DIR, ready to
# copy to a new node's VM_IMAGE_DIR (default /opt/hopper/vm-images) where
# join-node.sh / the k3s-agent role import them.
#
# Usage:
#   ./stage-vm-images.sh [OUT_DIR]
#   OUT_DIR defaults to ./vm-image-tarballs
#
# Then copy to the new node, e.g.:
#   ssh worker-01 sudo mkdir -p /opt/hopper/vm-images
#   scp <OUT_DIR>/*.tar worker-01:/tmp/ && ssh worker-01 sudo mv /tmp/*.tar /opt/hopper/vm-images/
#
# A registry (VM_IMAGE_REGISTRY) is the better path for more than one node; this
# is the offline/one-off fallback and mirrors how `make vm-images-load` imports
# locally.
set -euo pipefail

OUT_DIR="${1:-./vm-image-tarballs}"
VM_IMAGES=(hopper/vm-ubuntu:22.04 hopper/vm-python-ml:22.04 hopper/vm-cpp:22.04 hopper/vm-java:22.04)

mkdir -p "$OUT_DIR"
for img in "${VM_IMAGES[@]}"; do
  out="$OUT_DIR/$(echo "$img" | tr '/:' '__').tar"
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    echo "image $img not found locally — build it first (make vm-images)"; exit 1
  fi
  docker save "$img" -o "$out"
  echo "[stage] wrote $out"
done
echo "[stage] DONE — copy $OUT_DIR/*.tar to each new node's /opt/hopper/vm-images/"
