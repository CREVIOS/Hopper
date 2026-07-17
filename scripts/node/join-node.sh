#!/usr/bin/env bash
# Enroll THIS machine as a Hopper VM-hosting worker, without Ansible.
#
# Run this ON the PC you want to add. It installs lxcfs, joins the existing k3s
# cluster as an agent, and imports the VM template images. It deliberately does
# NOT label the node vm-ready — that is done from the server once the node shows
# Ready (see the printed next step, or scripts/node/label-node.sh). Gating the
# label on the server keeps a half-prepared node from receiving VMs.
#
# Prereqs on this machine: Debian/Ubuntu, sudo, network reachability to the k3s
# server's API (6443) over a LAN or a WireGuard/Tailscale overlay — never the
# public internet.
#
# Usage:
#   sudo K3S_URL=https://10.0.0.6:6443 K3S_TOKEN=<token> ./join-node.sh
# Optional:
#   VM_IMAGE_REGISTRY=ghcr.io/your-org   pull images from a registry
#   VM_IMAGE_DIR=/opt/hopper/vm-images   import tarballs from here (default)
set -euo pipefail

: "${K3S_URL:?set K3S_URL, e.g. https://10.0.0.6:6443}"
: "${K3S_TOKEN:?set K3S_TOKEN (server: sudo cat /var/lib/rancher/k3s/server/node-token)}"
VM_IMAGE_REGISTRY="${VM_IMAGE_REGISTRY:-}"
VM_IMAGE_DIR="${VM_IMAGE_DIR:-/opt/hopper/vm-images}"
VM_IMAGES=(hopper/vm-ubuntu:22.04 hopper/vm-python-ml:22.04 hopper/vm-cpp:22.04 hopper/vm-java:22.04)

log() { echo "[join-node] $*"; }

log "installing lxcfs"
sudo apt-get update -qq
sudo apt-get install -y -qq curl ca-certificates lxcfs
sudo systemctl enable --now lxcfs

log "waiting for lxcfs proc files"
for f in meminfo cpuinfo stat uptime diskstats swaps loadavg; do
  for _ in $(seq 1 30); do [ -e "/var/lib/lxcfs/proc/$f" ] && break; sleep 1; done
  [ -e "/var/lib/lxcfs/proc/$f" ] || { echo "lxcfs file $f never appeared"; exit 1; }
done

if [ ! -x /usr/local/bin/k3s ]; then
  log "joining k3s cluster as agent"
  curl -sfL https://get.k3s.io | K3S_URL="$K3S_URL" K3S_TOKEN="$K3S_TOKEN" INSTALL_K3S_EXEC=agent sh -
else
  log "k3s already installed — skipping install"
fi
sudo systemctl enable --now k3s-agent

log "loading VM template images"
if [ -n "$VM_IMAGE_REGISTRY" ]; then
  for img in "${VM_IMAGES[@]}"; do
    sudo k3s ctr images pull "$VM_IMAGE_REGISTRY/$img"
    sudo k3s ctr images tag --force "$VM_IMAGE_REGISTRY/$img" "$img"
    log "  $img (from registry)"
  done
else
  for img in "${VM_IMAGES[@]}"; do
    tar="$VM_IMAGE_DIR/$(echo "$img" | tr '/:' '__').tar"
    [ -f "$tar" ] || { echo "missing tarball $tar — see docs/NODE_JOIN.md (stage-vm-images.sh)"; exit 1; }
    sudo k3s ctr images import "$tar"
    log "  $img (from $tar)"
  done
fi

HOST="$(hostname)"
log "DONE. This node ('$HOST') has joined and is prepared, but NOT yet vm-ready."
cat <<EOF

Next step (run on the SERVER / control-plane):
  kubectl label node $HOST hopper.dev/vm-ready=true --overwrite

Until it carries that label, the orchestrator will not schedule VMs onto it and
will not count its capacity. Verify afterwards with:
  kubectl get nodes -L hopper.dev/vm-ready
EOF
