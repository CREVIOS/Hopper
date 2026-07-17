# Adding a PC as a Hopper node — runbook

This is the step-by-step for turning any spare machine into a Hopper worker that
hosts user VMs. It assumes you already have a running single-node cluster (the
k3s server that hosts the app) and want to add capacity.

For the design and the reasoning behind each safeguard, see
[MULTI_NODE.md](./MULTI_NODE.md). This document is the "how".

---

## What makes this safe

Hopper schedules a VM onto a node only if that node carries the label
`hopper.dev/vm-ready=true`, and it counts a node's CPU/RAM toward available
capacity only under the same condition. The orchestrator enforces both
(`services/orchestrator/internal/k8s/pod.go`).

The consequence: **a node you have not finished preparing receives no VMs and
advertises no capacity.** Joining a machine to the cluster is therefore not
enough to expose users to it — you also have to prepare it (lxcfs + VM images)
and then apply the label as the final step. The tooling below does exactly that,
in that order.

Two more safeguards back this up:

- **Billing follows the container, not the request.** A VM is billed only once
  its container is observed Running, so a VM that never schedules is never
  charged (`services/orchestrator/internal/k8s/watcher.go`).
- **A watchdog reaps VMs that can't be placed.** If a VM stays unschedulable past
  `HOPPER_PENDING_REAP_AFTER` (default 120s), the orchestrator deletes it and
  tells the user why, instead of leaving it Pending forever
  (`services/orchestrator/internal/k8s/watchdog.go`).

---

## Before you deploy this change (REQUIRED, do this first)

> **This is a breaking change if skipped.** The orchestrator now schedules VMs
> only onto nodes labelled `hopper.dev/vm-ready=true`, and counts capacity only
> from labelled nodes. An unlabelled cluster reports **0 nodes ready** and every
> VM request **queues forever**. So before (or immediately as) you roll out this
> change, label the node you already have:
> ```bash
> kubectl label node <primary-node> hopper.dev/vm-ready=true --overwrite
> kubectl get nodes -L hopper.dev/vm-ready   # verify it took
> ```
> (The local dev cluster is handled for you — `local-dev/setup-workloads.sh`
> labels the kind workers.)

## Before you add the FIRST extra node (one-time)

On a single node, "cluster-wide free" and "this node's free" are the same
number. Adding a second node makes them diverge, so do these once, before the
join:

1. **The primary node is already labelled** from the required step above — good.
   New nodes get labelled by the join tooling as their final step.

2. **Pin the stateful services to the primary node.** Postgres, NATS, Keycloak,
   and the backup job use RWO `local-path` volumes that live on one machine's
   disk; they must not reschedule onto the new node. Set the chart value and
   redeploy:
   ```yaml
   # values-prod.yaml
   stateful:
     nodeSelector:
       kubernetes.io/hostname: <primary-node>
   ```
   (Empty by default, which is correct for single-node. See
   `charts/hopper/values.yaml`.)

3. **Confirm the CNI enforces NetworkPolicy.** Production runs Cilium; the new
   node must join with the same CNI or the tenant-isolation policies silently
   stop applying to VMs placed there. k3s's default flannel does not enforce
   them.

---

## Networking: decide first

**Same LAN** (the PC is in the same building as the server): open the k3s ports
between the two machines only — `6443/tcp` (API), `10250/tcp` (kubelet), and the
CNI overlay port. Do not expose these to the internet.

**Off-site PC** (home machine joining a VPS): do **not** expose `6443` publicly.
Put both machines on a WireGuard or Tailscale network first, and use the overlay
addresses everywhere below (`K3S_URL`, inventory `ansible_host`). Every VM-to-VM
and VM-to-Postgres hop then rides that overlay, so expect its latency.

---

## Path A — Ansible (recommended for repeatability)

From a machine with Ansible and SSH access to both server and worker:

```bash
cd infrastructure/ansible

# 1. Point the inventory at your real hosts.
$EDITOR inventory/hosts.yml          # server-01 (existing), worker-01 (the PC)

# 2. Provide the join secret from the environment.
export K3S_URL="https://<server-overlay-or-lan-ip>:6443"
export K3S_TOKEN="$(ssh server-01 sudo cat /var/lib/rancher/k3s/server/node-token)"

# 3. (Registry-less) stage the VM images on the worker, or set vm_image_registry.
#    See "VM images" below.

# 4. Join.
ansible-playbook -i inventory/hosts.yml playbooks/site.yml
```

The `k3s-agent` role installs lxcfs, joins the node as a k3s agent, loads the VM
images, waits for the node to register, and only then labels it `vm-ready`. It is
idempotent — re-running it against a healthy node changes nothing.

---

## Path B — one script on the PC (quick, no Ansible)

Run on the PC itself:

```bash
sudo K3S_URL=https://<server-ip>:6443 \
     K3S_TOKEN=<token> \
     ./scripts/node/join-node.sh
```

It installs lxcfs, joins the cluster, and imports the VM images, then prints the
one command to run on the server to finish:

```bash
kubectl label node <the-pc-hostname> hopper.dev/vm-ready=true --overwrite
```

The script deliberately stops short of labelling, because the label is applied
from the server (which holds cluster credentials) and marks the point where the
node is trusted to host VMs.

---

## VM images

VM pods use `imagePullPolicy: IfNotPresent` against bare names like
`hopper/vm-ubuntu:22.04` with **no registry fallback**, so each node needs the
images locally. Two options:

- **Registry (best for more than one node):** push the images to a registry once
  and set `vm_image_registry` (Ansible) or `VM_IMAGE_REGISTRY` (script). The node
  pulls and retags them.
- **Tarballs (offline/one-off):** on a machine that built the images
  (`make vm-images`), run:
  ```bash
  ./scripts/node/stage-vm-images.sh ./vm-image-tarballs
  scp ./vm-image-tarballs/*.tar worker-01:/tmp/
  ssh worker-01 'sudo mkdir -p /opt/hopper/vm-images && sudo mv /tmp/*.tar /opt/hopper/vm-images/'
  ```
  The join tooling imports them from `/opt/hopper/vm-images` by default.

---

## Verify

```bash
# The new node is Ready and labelled.
kubectl get nodes -L hopper.dev/vm-ready

# Its capacity now shows up in the availability readout.
curl -s localhost:8000/pods/availability | jq '{nodes_ready, largest_node_free, nodes}'
```

`nodes_ready` should increase by one, and the new node should appear in `nodes`
with its free CPU/RAM. Create a VM small enough to fit on the new node and
confirm it lands there:

```bash
kubectl get pods -n hopper -o wide   # NODE column should include the new machine
```

---

## Removing a node

Draining terminates the VMs on that node (they are not live-migratable), so warn
users first, then:

```bash
kubectl cordon <node>          # stop new VMs landing here; capacity drops it immediately
kubectl label node <node> hopper.dev/vm-ready-   # belt and braces: also drop it from Hopper's view
kubectl delete pods -n hopper -l app=hopper-vm --field-selector spec.nodeName=<node>
# then, on the node:
sudo /usr/local/bin/k3s-agent-uninstall.sh
```

Cordoning alone already removes the node from capacity accounting (the
orchestrator excludes `Unschedulable` nodes), so no VM will be admitted expecting
room there.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| New VMs never land on the new node | Node not labelled | `kubectl label node <n> hopper.dev/vm-ready=true --overwrite` |
| VM on the new node is `ContainerCreating` → `ErrImagePull` | VM images missing on that node | Stage tarballs or set a registry (see VM images) |
| VM on the new node fails immediately | lxcfs not running | `ssh <n> systemctl status lxcfs`; the join tooling installs it |
| Availability shows capacity but Large VMs still queue | Working as intended — no single node has room (fragmentation); the per-node gate is refusing to admit a VM that couldn't schedule | Add capacity or use a smaller plan |
| VM stuck Pending, then disappears with a "couldn't start" notice | The scheduling watchdog reaped an unplaceable VM | Expected; no credits were charged |
