# Adding Worker Nodes to Hopper

How to turn Hopper from a one-machine deployment into a real multi-node cluster: what
already works, what breaks the moment a second machine joins, and the order to fix it in.

This document covers `docs/TASKS.md` **D1.3 "Join worker nodes"**.

> **Implementation status (2026-07-17).** The core of this plan is now built,
> unit- and integration-tested, and verified live on the 3-node kind cluster.
> Done: the billing-on-Running fix (§4.2), the `hopper.dev/vm-ready` label gate
> (§4.3/§4.4), the Pending watchdog (§1.2), per-node fit in admission (§4.1),
> `NodeName` population plus a reconcile-loop backfill that self-heals a dropped
> `pod.started` event (§4.5), stateful workload pinning (§4.8), and the
> provisioning tooling (a real `k3s-agent` Ansible role + `scripts/node/` + the
> [NODE_JOIN.md](./NODE_JOIN.md) runbook). An adversarial code review found no
> CRITICAL/HIGH issues; its follow-ups (per-node admission integration tests, a
> watchdog reap-ordering test, and the node_name backfill) are done. The
> operator-facing steps live in **[NODE_JOIN.md](./NODE_JOIN.md)**; this document
> keeps the design rationale. Still open: image distribution via a shared registry
> is scripted but a registry is not stood up (§Phase 3), persistent workspaces
> remain deferred (§4.7/§6.3), and drain is manual (§6.2).

---

## 1. The short answer

**Adding a PC is mostly an operations task, not a development task.** Hopper runs on
Kubernetes, and Kubernetes already does the hard part: `kube-scheduler` places VM pods on
whatever node has room. Hopper never asks for a specific node, so a joined node starts
receiving VMs immediately with no code change.

Roughly 40% of the work is already done, and it is the part people expect to be hardest:

- The orchestrator lists **all** nodes and sums their allocatable CPU/RAM
  (`services/orchestrator/internal/k8s/pod.go:393-436`).
- It already excludes cordoned and `NoSchedule`-tainted nodes from capacity
  (`schedulableForVMs`, `pod.go:440-450`), so the control plane never inflates the pool.
- The admission queue's capacity formula is a genuine cluster-wide sum
  (`services/api-gateway/app/services/vm_capacity.py:143-188`).
- The availability readout already reports `nodes_ready` as a count, not a boolean.

So "more machines equals more capacity" works today, and the UI will report it correctly.

**What is missing is everything around that.** Nothing in this repo provisions a cluster or
joins a node — that was done by hand, off-repo. And four assumptions that are invisible on
one node become real defects on two. Three of them are already reproducible in the local
`kind` cluster, which has had three nodes this whole time.

**Do not start by joining the node.** Section 5 Phase 1 lists changes to make *first*, on the
current single node, at zero risk. Joining a node before those land will produce VMs that
fail to start, VMs that are billed but never run, and a capacity readout that lies.

---

## 2. Where we are today

| | Topology | Notes |
|---|---|---|
| **Production** | 1 node, k3s VPS | `hopper.farefin.com`, node `10.0.0.6` (`charts/hopper/values-prod.yaml`) |
| **Local dev** | 3 nodes, kind | 1 control-plane + 2 workers (`local-dev/setup-cluster.sh`) |

The local cluster is already multi-node. It is not a faithful rehearsal — kind "nodes" are
containers sharing one kernel, one disk, and one image store — but it is enough to reproduce
the *scheduling* defects, and it already has.

### What is real versus what is scaffold

This matters, because half the infrastructure directory looks like multi-node support and is
not.

**Real and maintained:** `k8s/deploy/`, `k8s/argocd/`, `charts/hopper/`, `scripts/cd/`.

**Dead scaffold** — every one of these has a single commit from the initial project scaffold
and is referenced by nothing:

- `infrastructure/ansible/` — no roles, no k3s, no join logic. The inventory lists fictional
  hosts (`192.168.1.10`, `gpu-node-01`) that do not match production's `10.0.0.6`. The
  `gpu-setup.yml` playbook references a template file that does not exist in the repo and has
  a `notify:` with no handler, so it would fail if run.
- `infrastructure/pulumi/` — provisions zero resources; the body is a TODO list.
- `infrastructure/argocd/app-of-apps.yaml` — a stale duplicate pointing at
  `github.com/your-org/hopper.git` with `prune: true`. The real one (`k8s/argocd/`)
  deliberately disables prune because pruning would delete running user VMs. **This file is a
  trap and should be deleted.**
- `k8s/kueue/`, `k8s/kai-scheduler/`, `k8s/gpu-operator/` — written for a labeled multi-node
  GPU fleet that has never existed. Kueue is unwired (`docs/VM_QUEUEING.md:316` says so
  outright); Hopper built its own admission queue instead.
- `k8s/network-policies/` — Calico CRDs. Production runs Cilium and has its own policies.
- `k8s/base/` — namespaces `hopper-system`/`hopper-pods`. Production uses `hopper`.

There is no `k3s agent`, `K3S_URL`, `K3S_TOKEN`, or `kubeadm join` anywhere in the tree.

### A documentation contradiction to resolve

`docs/ARCHITECTURE.md:270` says "Full Kubernetes, not K3s. K3s is limited to ~50-100 nodes",
and `docs/TECH_STACK.md` pins `kubeadm / RKE2`. What actually runs is single-node k3s.

k3s is the right call for this project and the docs are wrong, not the deployment. k3s is
conformant Kubernetes; the 50-100 node ceiling is irrelevant at the scale of "a few PCs in a
lab". **Recommendation: update the docs to match reality rather than migrate to kubeadm.**
Switching cluster distributions to satisfy a paragraph would be a large, risky change that
buys nothing.

---

## 3. What already works — do not rebuild this

| Capability | Where | Status on multi-node |
|---|---|---|
| VM placement across nodes | stock `kube-scheduler` | Works. VM pods carry no `nodeSelector`/`nodeName`/affinity, so any node is fair game (`pod.go:198-310`). |
| Cluster-wide capacity | `pod.go:393-436` → `vm_capacity.py:143-188` | Works. Sums every Ready node. |
| Excluding unusable nodes | `schedulableForVMs`, `pod.go:440-450` | Works. Skips cordoned and `NoSchedule`/`NoExecute` nodes. Unit-tested. |
| Node health | `NodeReady` condition, `pod.go:419-423` | Works. A `NotReady` node contributes zero capacity (`vm_capacity.py:163`). |
| SSH reachability | NodePort, `externalTrafficPolicy: Cluster` (verified live) | **Works.** See below. |
| Browser terminal / VS Code | dials the **pod IP** directly (`k8s_pod_lookup.py:78-90`) | Works. Node-agnostic by construction. |
| Billing and metrics | NATS events | Works. Node-agnostic. |
| VM workspaces | none — VMs are ephemeral, no PVC is wired | Works *because* nothing is persisted. See risk in 4.7. |

### Why SSH keeps working (a genuine relief)

The obvious worry is `settings.node_ip` — a single global string used for the SSH host
(`pods.py:776`, `k8s_pod_lookup.py:90`) and the VS Code URL. Every user is handed
`ssh root@hopper.farefin.com -p <port>` regardless of which node their VM runs on
(`frontend/src/routes/pods/+page.svelte:246`).

This survives multi-node because a NodePort service answers on **every** node, and the SSH
services use the default `externalTrafficPolicy: Cluster` (confirmed against the live
cluster). kube-proxy forwards a connection arriving at node 1 to a pod on node 2. One
hostname for the whole cluster is legitimate.

Three caveats, none blocking:

1. It costs an extra network hop and SNATs the client IP.
2. The advertised node becomes a single point of failure for SSH ingress even when the VM's
   own node is healthy.
3. The gateway's `HOPPER_NODE_IP` comes from `fieldRef: status.hostIP`
   (`charts/hopper/templates/api-gateway.yaml:111-114`) — the node the **gateway** landed on,
   not the node the **VM** is on. It works only because of the NodePort property above. The
   value is semantically wrong and will mislead the next person who reads it.

Keep the single-host model for now. Fix the comment; do not fix the architecture.

---

## 4. What breaks — ranked, with evidence

### 4.1 Aggregate fit admits VMs that cannot be scheduled (CONFIRMED LIVE)

`plan_fits` compares a VM against **cluster-wide** free capacity and says so in its own
docstring (`vm_capacity.py:191-205`):

> This is an AGGREGATE fit only: it does not model per-node bin-packing, so a plan can pass
> here yet fail to schedule on any single node due to fragmentation.

On one node, aggregate fit and per-node fit are the same thing, so this is latent. **A second
node activates it.** This is not a prediction. It is already happening in the dev cluster:

```
$ kubectl get pods -n hopper
vm-1783682826716565930   0/1   Pending   0   7d2h

$ kubectl describe pod vm-1783682826716565930 -n hopper
Warning  FailedScheduling  (x42 over 3h51m)  default-scheduler
  0/3 nodes are available: 1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane},
  2 Insufficient memory.
```

A Large VM (8Gi memory request) was admitted and has been Pending for **seven days**. The
arithmetic:

| Node | Allocatable | Requested | Free |
|---|---|---|---|
| `hopper-worker` | 13.5Gi | 10290Mi (74%) | ~3.3Gi |
| `hopper-worker2` | 13.5Gi | 8242Mi (59%) | ~5.5Gi |
| **Aggregate** | **27Gi** | | **~8.8Gi** |

8.8Gi free cluster-wide is greater than the 8Gi requested, so admission passed. Neither node
has 8Gi, so it will never schedule. The queue's head-of-line blocking
(`vm_scheduler.py:352-353`) then means this entry can stall admissions behind it.

### 4.2 Billing charges for VMs that never ran (CONFIRMED, amplified by 4.1)

The billing ticker starts as soon as the K8s pod **object** is created — not when it runs
(`internal/grpc/pod_service.go:139-153`):

```go
_ = s.server.podManager.Transition(p.ID, pod.StateRunning)   // unconditional
...
s.server.ticker.Start(p.ID, plan, func(ev billingpkg.TickEvent) { ... })
```

`CreatePod` returns once the API server accepts the object, which happens long before
scheduling. There is no phase gate on the ticker. The pod is marked `StateRunning` outright,
even while it is `Pending`.

So the seven-day Pending VM in 4.1 has been **billed for seven days without ever running**,
and reported to its user as running. It self-limits only in the sense that credits eventually
hit zero and `billing.exhausted` terminates it — the user simply pays until then.

A watcher already detects the real `Pending` → `Running` transition and publishes
`pod.started` exactly once (`internal/k8s/watcher.go:46-54`). The correct signal exists and
is not wired to billing.

This is a money bug that exists on one node too. Fragmentation makes it routine.

### 4.3 lxcfs is a hard per-node dependency with nothing enforcing it

Every VM pod mounts seven lxcfs files as `hostPath` with `Type: File`
(`pod.go:151-171`):

```go
lxcfsFiles := []string{"meminfo", "cpuinfo", "stat", "uptime", "diskstats", "swaps", "loadavg"}
HostPath: &corev1.HostPathVolumeSource{
    Path: "/var/lib/lxcfs/proc/" + f,
    Type: &hostPathFile,   // must pre-exist or the kubelet fails the pod
}
```

The code comment (`pod.go:119-120`) states the requirement: "The lxcfs daemon must be running
on every node (systemd unit `lxcfs.service`)." Nothing enforces it. There is no DaemonSet, no
`nodeSelector`, and no capacity-side exclusion. Provisioning is a manual loop in
`local-dev/setup-workloads.sh:46-48` that `touch`es empty stand-in files via `docker exec`.

Join an unprepared node and roughly half of new VMs fail — whichever half the scheduler
happens to place there. This is the most placement-fragile thing in the codebase. Without
lxcfs, `free`/`nproc` inside a VM report the **host's** totals rather than the container's,
which is both a UX bug and a tenant-isolation leak.

### 4.4 VM images exist only on the machine that built them

`make vm-images-load` runs `docker save "$tag" | sudo k3s ctr images import -` — on the local
machine only. VM pods use `imagePullPolicy: IfNotPresent` (`pod.go:242`) against image names
with no registry host (`hopper/vm-ubuntu:22.04`). There is no registry to fall back to.

A VM scheduled onto a fresh node gets `ErrImagePull` and stays there. Kind papers over this
locally because `kind load docker-image` pushes to every node at once; `k3s ctr images import`
does not.

### 4.5 The orchestrator cannot report where a VM ran

`pod.Pod.NodeName` (`internal/pod/types.go:32`) is plumbed into the gRPC response
(`pod_service.go:53`) and **never assigned anywhere**. Not in `pod/manager.go`, not in
`k8s/watcher.go`. It always serializes as `""`.

Nothing breaks today, but it blocks every node-aware feature: per-VM SSH hosts, an admin node
view, drain, and debugging "why is this user's VM slow" once nodes are not identical.

### 4.6 Storage capacity is a number typed into a config file

`cluster_storage_total: str = "150Gi"` (`config.py:45-48`) is static because `ListNodes` does
not report `ephemeral-storage`. On one node it is a defensible approximation of one disk. On
several nodes it describes nothing real: disk is per-node and local, so a single pooled figure
is neither a total nor a per-node limit. It will drift further from reality with every machine
added.

### 4.7 Persistent workspaces will collide with node-local storage

Today VMs are ephemeral, which is *why* multi-node placement is safe — there is nothing to
leave behind. The PVC code exists (`pod.go:126-149`, RWO, mounted at `/workspace`) but is
unreachable: `pod_service.go:112-121` never sets `DiskGiB`, so it is always 0.

`docs/SRS_ADDENDUM.md` makes persistent workspace a **Must-Have**. The moment it is wired:

- k3s `local-path` is **node-local and RWO**. A workspace written on node 2 does not exist on
  node 1.
- A VM must then always return to the node holding its disk, which is a real scheduling
  constraint the system has no concept of.

Do not wire persistent workspaces and multi-node in the same change. Multi-node first, then
workspaces with a storage design that accounts for it (see 6.3).

### 4.8 Stateful services have no placement constraints

`charts/hopper` contains **no** `nodeSelector`, `affinity`, `tolerations`, or
`topologySpreadConstraints` anywhere — `values.yaml:3` calls itself "a complete, working
single-node shape". Postgres is `replicas: 1` on an RWO `local-path` PVC; NATS and Keycloak
are single instances.

The likely fear — "Postgres reschedules onto the new node and comes up empty" — should not
happen: k3s's local-path provisioner stamps node affinity onto the PV it creates, so the pod
is pinned to the node holding the data and would go `Pending` rather than start on an empty
disk. That is a loud failure, not silent data loss. **Verify this on production before
joining a node** (`kubectl get pv <postgres-pv> -o jsonpath='{.spec.nodeAffinity}'`) — the
guarantee is worth confirming rather than assuming.

Either way, pin them explicitly. A `Pending` Postgres takes the whole platform down, and an
explicit `nodeSelector` states the intent instead of relying on a provisioner side effect.

### 4.9 Other node-local artifacts

- **SMTP relay** — a hand-installed systemd unit on node `10.0.0.6`
  (`k8s/deploy/node/hopper-smtp-relay.service`), reached via a hardcoded
  `hostAliases: [{ip: "10.0.0.6"}]` (`k8s/deploy/02-apps.yaml:39`). Works from any node as
  long as `10.0.0.6` is up, but it is an undocumented per-node dependency in a directory
  named `node/`.
- **CNI** — production runs Cilium. The chart warns that "flannel does NOT enforce" network
  policies, so they are inert on stock k3s. A new node must join with the same CNI or the
  tenant-isolation policies silently stop applying to VMs placed there. This is a security
  regression that produces no error.

---

## 5. The plan

### Phase 1 — Harden the single node first (no new hardware, no risk)

Every item is a correctness fix that stands on its own merit today and is a prerequisite for
sanity tomorrow. **Land all of Phase 1 before joining anything.**

**1.1 Gate billing on actually running.** Move `ticker.Start` off `CreatePod` and onto the
`pod.started` event the watcher already publishes (`watcher.go:46-54`). Stop transitioning to
`StateRunning` unconditionally in `pod_service.go:139` — let the watcher own that state.
*Acceptance:* a VM that never schedules is never billed and never displays as running.
*This is the highest value-per-line change in the document and fixes a live money bug.*

**1.2 Add a Pending watchdog.** If a VM stays `Pending` beyond a threshold (90s is a
reasonable start) with a `FailedScheduling` reason, stop waiting: delete the pod, release the
reservation, and surface an honest reason to the user rather than a permanent spinner.
*Acceptance:* the 7-day Pending pod scenario resolves itself within two minutes.
*This is the safety net that makes fragmentation recoverable instead of permanent.*

**1.3 Introduce a `hopper.io/vm-ready=true` node label.** Three coordinated edits:

- `pod.go` — add `NodeSelector: {"hopper.io/vm-ready": "true"}` to the VM pod spec.
- `pod.go:440-450` — extend `schedulableForVMs` to require the label, so unprepared nodes
  contribute zero capacity.
- Ansible (Phase 2) — apply the label only *after* lxcfs and the images are in place.

This is the structural fix, and it generalizes the control-plane exclusion that already
exists. It converts "join a node and hope it was prepared" into a fail-closed gate: an
unprepared node receives no VMs and advertises no capacity. It makes 4.3 and 4.4 impossible
to get wrong rather than merely documented.

Note the invariant the existing code already respects: **whatever the pod spec refuses to
schedule on, the capacity math must also refuse to count.** Breaking that pairing is exactly
the bug the control-plane taint fix corrected (capacity over-counted by ~13.5Gi). Adding a
`nodeSelector` without the matching `ListNodes` filter reintroduces it in a new form.

**1.4 Pin stateful workloads.** Add `nodeSelector`/`affinity` values to `charts/hopper` and
pin Postgres, Keycloak, and NATS to the current node. Verify the local-path PV node affinity
claim in 4.8 while doing it.
*Acceptance:* `helm template` shows an explicit node constraint on all three.

**1.5 Fix the `HOPPER_NODE_IP` lie.** It is the gateway's own node, not the VM's. Either
rename it to something honest (`HOPPER_SSH_ADVERTISE_HOST`) and set it from config rather
than `fieldRef`, or document why `externalTrafficPolicy: Cluster` makes the wrong value work.
Do not leave it as-is; the next reader will assume it means the VM's node.

**1.6 Delete `infrastructure/argocd/app-of-apps.yaml`.** A stale duplicate with `prune: true`
pointed at a placeholder repo, in a tree whose real ArgoCD config disables prune specifically
to avoid deleting running user VMs. It is a loaded gun.

### Phase 2 — Provision the node (ops)

**2.1 Decide the network shape first.** This determines everything else:

- **Same LAN** (both machines in the same lab): straightforward. Open k3s ports between them
  — 6443/TCP (API server), 10250/TCP (kubelet), and the CNI's overlay port (8472/UDP for
  VXLAN, 4240/TCP for Cilium health). Do **not** expose these to the internet.
- **Across the internet** (a home PC joining the VPS): do not expose 6443 publicly. Put both
  machines on a WireGuard or Tailscale network and join over that, with
  `--node-ip`/`--node-external-ip` set to the overlay addresses. Expect the overlay's latency
  to sit on every pod-to-pod hop, including VM to Postgres.

The second shape is what "add another PC" usually means in practice, and it is the one that
quietly degrades performance if treated like the first. Decide explicitly.

**2.2 Write a real Ansible role** (`infrastructure/ansible/roles/k3s-agent/`) that:
installs prerequisites; installs and enables `lxcfs.service`; creates `/var/lib/lxcfs/proc/*`;
joins with `K3S_URL` + `K3S_TOKEN`; waits for `Ready`; and **only then** applies
`hopper.io/vm-ready=true`.

The existing `infrastructure/ansible` tree cannot be the starting point — it is a broken stub
with a fictional inventory and a missing template. Replace its inventory with the real hosts
and delete `gpu-setup.yml`, which references hardware that does not exist.

*Acceptance:* `ansible-playbook` against a blank machine yields a node that is `Ready`,
labeled, and running lxcfs — and re-running it changes nothing.

**2.3 Keep the k3s token out of the repo.** It is a cluster-admin credential; joining a node
with it grants kubelet rights. Treat it exactly like the other secrets in `k8s/deploy/00-secrets.yaml`.

### Phase 3 — Image distribution

**3.1 Stand up a registry** and push `hopper/vm-*:22.04` to it, so image availability stops
depending on which machine ran `docker build`. The service images already have this solved —
CI pushes to GHCR (`scripts/ci/docker-build.sh`) — so the VM images are the only gap, and the
pattern to copy already exists in the repo.

The registry can be GHCR (private, matching the CD path) or a registry running in-cluster. If
in-cluster, note the bootstrap ordering problem: the registry must not live on a node that
needs the registry to start.

**3.2 Replace `make vm-images-load`** with a push, keeping the `k3s ctr images import` path
documented as the offline fallback. Per the project memory, buf remote plugins already fail
offline here, so an air-gapped path is worth preserving rather than deleting.

*Acceptance:* a VM scheduled to a node that has never built an image starts normally.

### Phase 4 — Per-node fit (fixes 4.1 at the source)

Phase 1.2's watchdog makes fragmentation *recoverable*. This makes it *rare*, and lets the UI
explain itself instead of admitting VMs that quietly fail.

**4.1 Extend `NodeInfo`** with `cpu_allocated` and `memory_allocated`. The orchestrator
already walks every pod and counts them per node (`pod.go:400-408`) — sum requests in the
same loop instead of just counting. Additive proto change, no breaking field renumbering.

Per-node free from K8s is strictly better than the current model: it counts kube-system pods
the gateway cannot see, which is exactly what the hand-tuned `reserve` was approximating.

**4.2 Make `plan_fits` require a home.** A plan fits only if **some single node** can hold it
— first-fit over the node list — in addition to the existing aggregate check.

*Known approximation, and it must be documented in the code the way the current limitation
already is:* reservations that exist as `pending` PodSession rows are not yet on any node, so
the gateway cannot attribute them per-node. Subtract them pessimistically. The window is
short — the admission loop materializes reservations within seconds (`vm_scheduler.py:391-424`)
— and Phase 1.2's watchdog catches whatever slips through. This is a heuristic gate backed by
a reconciler, not a second scheduler. **Do not try to write a real scheduler here.**
`kube-scheduler` already exists and is better at it; the gate only needs to stop obvious
misfits from being admitted and billed.

**4.3 Say so in the UI.** "No single machine currently has room for a Large VM" is a true and
actionable message. "Queued" while 8.8Gi sits free is neither. The availability panel already
shows free CPU/memory/storage and `nodes_ready`; per-node fit is what makes those numbers
*mean* what a user reads them to mean.

*This matters beyond correctness.* The availability readout currently invites a reasonable
person to conclude a Large VM will start, because 8.8Gi > 8Gi. That is the same class of
problem as the quarter-core CPU reservation: the arithmetic is right and the presentation
misleads. It cost a round of investigation once already.

### Phase 5 — Node observability

**5.1 Populate `NodeName`** from `p.Spec.NodeName` in the watcher — the field already exists
and is already wired to the proto (4.5). Store it on `PodSession`.

**5.2 Add an admin node view**: per node, show name, Ready, `vm-ready`, allocatable, free, VM
count. Every input already exists in `ListNodes` once 4.1 lands. This is the first point at
which an operator can answer "is the new PC actually being used?" — which is the whole point
of the exercise, and the first thing an evaluator will ask.

### Phase 6 — Node lifecycle

**6.1 Handle a node going away.** Today, if a node dies, its VMs die with it and the DB keeps
their sessions `running` — and with billing fixed in Phase 1.1, correctly stops charging.
Verify that. Reconcile orphaned sessions against the watcher.

**6.2 Drain.** Not implemented anywhere (only aspirational in `docs/TASKS.md:568`). Cordon
already works end-to-end for capacity (`n.Spec.Unschedulable` is respected), so the
capacity-side half is done. Draining means terminating users' VMs, so it needs a notification
path and, ideally, a warning window — not a `kubectl drain`.

**6.3 Then, and only then, revisit persistent workspaces** (4.7) with a storage design that
accounts for more than one disk: an NFS/Longhorn RWX class, or accepting node affinity per
workspace and scheduling VMs back to their disk.

### Phase 7 — Verification

**7.1 Reproduce the fixes on kind.** The dev cluster is already 3 nodes and already exhibits
4.1 and 4.2. Fixes can be proven locally with no new hardware — start there, before the PC
exists.

**7.2 Add regression tests** mirroring the existing `TestSchedulableForVMs` precedent: label
filtering in `schedulableForVMs`, per-node `plan_fits` (fragmentation case: 2 nodes with
3.3Gi and 5.5Gi free must reject an 8Gi plan while aggregate says yes), the billing gate, and
the Pending watchdog. The fragmentation case should use the exact numbers from 4.1 — they are
a real incident, not a hypothetical.

**7.3 Update the docs** (`ARCHITECTURE.md`, `TECH_STACK.md`, `SDD.md` Appendix H.1) to
describe k3s and the actual topology, and check off `TASKS.md` D1.3.

---

## 6. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Node joins unprepared; half of new VMs fail | High | Phase 1.3 `vm-ready` label makes it fail-closed |
| Users billed for VMs that never ran | High | Phase 1.1. Live today, worse with fragmentation |
| Postgres `Pending` after a restart → platform down | High | Phase 1.4 pinning + verify PV node affinity |
| New node joins with a non-enforcing CNI → tenant isolation silently off | High | Match the CNI at join; assert policies apply |
| Exposing 6443 to the internet to join a remote PC | High | Phase 2.1 — WireGuard/Tailscale, never public |
| Fragmentation stalls the queue head | Medium | Phase 1.2 watchdog, then Phase 4 |
| Cross-internet overlay latency on every pod hop | Medium | Decide in Phase 2.1 with eyes open |
| Storage figure drifts further from reality | Medium | Phase 4/6.3 |
| Persistent workspaces wired before multi-node settles | Medium | Sequence: 4.7 explicitly deferred to 6.3 |

## 7. Effort

| Phase | Work | Depends on |
|---|---|---|
| 1 — Harden | ~1-2 days, code only, no hardware | nothing |
| 2 — Provision | ~1 day ops + Ansible role | network decision (2.1) |
| 3 — Registry | ~half day | Phase 2 |
| 4 — Per-node fit | ~1-2 days, includes proto change | Phase 1 |
| 5 — Observability | ~1 day | Phase 4.1 |
| 6 — Lifecycle | ~2+ days | Phase 5 |
| 7 — Verification | continuous | all |

Phase 1 is the whole safety story and needs no second machine. Phases 1, 4, and 7 are provable
today on the existing 3-node kind cluster.

---

## 8. If you only do three things

1. **Phase 1.1** — stop billing VMs that never ran. Live money bug, small diff.
2. **Phase 1.3** — the `vm-ready` label, with the matching capacity filter. Turns node
   preparation from a tribal-knowledge checklist into an enforced invariant.
3. **Phase 1.2** — the Pending watchdog. Turns "stuck forever, still charging" into
   "requeued in 90 seconds with a reason".

Those three make a second node safe to join. Everything after makes it good.
