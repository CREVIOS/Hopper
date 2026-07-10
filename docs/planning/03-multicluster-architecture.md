# Multi-Cluster Architecture & Implementation Plan (Federated Orchestrators)

> **Status:** Design + phased plan. Approved approach: **Federated orchestrators**
> (one orchestrator per member cluster; the gateway fans out).
> **Note:** the SRS lists "Multi-cluster federation or multi-region deployment" as an
> explicit non-goal (`SRS Hopper Combined.tex:294`). This document is a deliberate
> **v2 expansion** beyond the shipped single-node k3s reality — it is a roadmap, not
> part of the current student-side implementation pass.

**Goal:** Let Hopper schedule and operate student VMs across N independent Kubernetes
clusters (e.g. a lab k3s + a GPU bare-metal cluster + a cloud-burst cluster) from a
single control plane, without a distributed-consensus rewrite.

**Architecture (2-3 sentences):** Each member cluster runs its own orchestrator +
VM-plane (RBAC, LXCFS, metrics-server, ingress) and remains the durable store for its
own pods via reconcile-from-cluster — exactly today's model, replicated N times. The
gateway gains a **cluster registry** and a **placement step**: it picks a target cluster
at launch, records `cluster_id` on the session, and routes every subsequent call
(status, terminate, terminal, files, VS Code, metrics) to the owning cluster's
orchestrator. State is **sharded by cluster ownership**, so no cross-orchestrator shared
state or consensus is required.

**Tech Stack:** Go orchestrator (gRPC), FastAPI gateway, Postgres (`pod_sessions` gains
`cluster_id`), NATS (subjects namespaced by cluster), protobuf (`buf`/`protoc`), Cilium
per cluster.

---

## 1. Why this approach

Of the three options considered, federated orchestrators is the pragmatic path because
it **leans on the mechanism that already works**: each orchestrator holds authoritative
runtime state for its own cluster in-memory and rebuilds it on restart from live pods
(`watcher.Reconcile`). We don't fight the fragile in-memory `pod.Manager` (coupling
point #1) — we shard it. The alternatives:

- **Single orchestrator, N clusters** — one process holding every cluster's kubeconfig
  is a larger credential blast radius and still needs the dead leader election wired for
  HA; rejected as a first step.
- **DB-backed fleet + queue workers** — the proper long-term target (stateless workers,
  JetStream work queue, Postgres as source of truth), but it *is* the #1 hardest coupling
  point to break. Federated orchestrators can **evolve into** it later by moving state to
  the DB one subsystem at a time. Deferred.

---

## 2. Single-cluster coupling points this must break

From the coupling audit (evidence in each line), ranked hardest-first:

1. **In-memory `pod.Manager`, no cluster dimension** — `pod/manager.go:9-18`,
   `pod/types.go:24-40` (no `ClusterID`). → shard by cluster; add `ClusterID` to the type.
2. **Gateway→pod I/O bound to one local kube context** — `port_forward.py:38-45`
   (`kubectl port-forward`, no `--context`), `k8s_pod_lookup.py`, `pods.py:333-567`,
   `files.py:52-76`. → per-cluster kube context OR delegate I/O to the owning orchestrator.
3. **Single K8s client + single gRPC endpoint** — `k8s/client.go:15-40`, `main.go:38-42`,
   `orchestrator_client.py:60,149` (`orchestrator_url` singleton). → keyed registry of endpoints.
4. **NodePort + single `node_ip`** — `pod.go:304-330`, `config.py:24`, `02-apps.yaml:113-116,314-315`,
   `pods/[id]/+page.svelte:494`. → per-cluster ingress/LB + per-session endpoint.
5. **Single-replica / dead leader election** — `leader/election.go` (unused),
   `handlers.go:24` (no queue group), `metrics_publisher.go:49`, `02-apps.yaml:233`.
   → per-cluster ownership makes each orchestrator single-writer for its own cluster.
6. **Process-local billing tickers** — `billing/ticker.go:19-97`. → stay local to the
   owning cluster's orchestrator; make `tx_id` globally unique (prefix `cluster_id`).
7. **No cluster-selection layer** — `grpc/pod_service.go:65-159`, `pod.go:78-85`.
   → new placement step in the gateway before `CreatePod`.

---

## 3. Target architecture

```
                              Browser
                                 │  (per-cluster public host for SSH/VS Code)
                     Nginx Ingress (control plane host)
                                 │
                          API Gateway (FastAPI)
        ┌───────────── Cluster Registry {cluster_id → {grpc_endpoint, kubeconfig, public_host, ingress_class}} ─────────────┐
        │                         │  Placement service (capacity-aware, ListNodes per cluster)                              │
        │  routes by session.cluster_id                                                                                      │
        ▼                         ▼                                                        ▼
  Orchestrator A            Orchestrator B                                          Orchestrator N
  (cluster A)               (cluster B)                                             (cluster N)
   in-mem Manager+reconcile  in-mem Manager+reconcile                                ...
   billing tickers (A pods)  billing tickers (B pods)
   metrics.A.<pod>           metrics.B.<pod>
        │                         │
   VM pods (A)               VM pods (B)
```

**Invariant:** a pod lives in exactly one cluster; `session.cluster_id` is the single
source of routing truth. Each orchestrator only ever sees/reconciles/bills its own cluster.

---

## 4. Component changes

### 4.1 Data model
- `pod_sessions` gains **`cluster_id VARCHAR(63) NOT NULL DEFAULT 'default'`** and
  **`access_host VARCHAR(253) NULL`** (the public host/IP for this pod's SSH/VS Code,
  derived from the cluster, replacing the single global `node_ip`). Migration adds both;
  existing rows backfill to `'default'`.
- New config table (or static config): the **cluster registry** —
  `{cluster_id, display_name, grpc_endpoint, public_host, ingress_class, enabled, weight}`.
  Start as static env/ConfigMap (`HOPPER_CLUSTERS` JSON); a DB table + admin UI is a later add.

### 4.2 Proto (`proto/hopper/pod/v1/pod.proto`)
- `PodStatus` gains `string cluster_id = 15;` and `string access_host = 16;`.
- `CreatePodRequest` is **not** given a cluster field — the gateway picks the cluster and
  dials that orchestrator directly, so the target is implicit in *which* orchestrator is called.
- `ListNodesResponse` optionally echoes a `cluster_id` for the placement view.

### 4.3 Orchestrator (Go)
- `config.go`: add `ClusterID string` (env `HOPPER_CLUSTER_ID`, default `"default"`).
- `pod/types.go`: `Pod` gains `ClusterID string`; set on `Create` and on `Reconcile`
  (from a new pod label `hopper.dev/cluster-id`, falling back to the orchestrator's own id).
- `pod.go`: stamp label `hopper.dev/cluster-id` on every VM pod; return `cluster_id` +
  `access_host` in `PodStatus` (access_host from a new `HOPPER_PUBLIC_HOST` env).
- `billing/ticker.go`: `tx_id` becomes `<cluster_id>:<podId>:<seq>` (globally unique).
- No new leader election needed: each orchestrator is the sole writer for its cluster.

### 4.4 Gateway (FastAPI)
- **Cluster registry** (`app/services/clusters.py`): parse `HOPPER_CLUSTERS`, hold a
  `{cluster_id → OrchestratorClient}` map (one gRPC channel per cluster) + metadata.
- **Placement** (`app/services/placement.py`): `select_cluster(plan) → cluster_id` —
  v1 = weighted round-robin filtered by live capacity (`ListNodes` per cluster, cached
  ~30s); pluggable for GPU-tier affinity later.
- `pods.py create`: call placement → dial that cluster's `OrchestratorClient.CreatePod`
  → persist `cluster_id` + `access_host` on the session.
- **All pod-scoped routes** (`GET/DELETE /pods/{id}`, terminal, files, VS Code, SSE
  metrics) resolve `session.cluster_id` and use that cluster's client/context.
- **Pod I/O across clusters** (terminal/files/VS Code): v1 = the gateway holds a
  **per-cluster kubeconfig** and passes `--context <cluster>` to `kubectl port-forward`
  (`port_forward.py` gains a `cluster_id` arg). v2 = delegate I/O to the owning
  orchestrator via a streaming gRPC proxy (removes gateway↔all-clusters network coupling).
- SSE metrics: subscribe `metrics.<cluster_id>.<pod_name>`.

### 4.5 NATS subjects
- Namespace by cluster: `billing.<cluster>.deducted`, `billing.<cluster>.exhausted`,
  `metrics.<cluster>.<pod>`, `pod.<cluster>.{created,stopped,failed}`. Gateway consumers
  subscribe with wildcards (`billing.*.deducted`) + queue groups (unchanged idempotency
  via the now-globally-unique `tx_id`).

### 4.6 Deployment
- Per cluster: orchestrator Deployment + VM RBAC Role/ClusterRole + Cilium policies +
  LXCFS + metrics-server + ingress (a Helm chart or kustomize overlay parameterized by
  `cluster_id`/`public_host`). The gateway + Postgres + Keycloak + NATS stay on **one**
  control-plane cluster; member clusters reach that NATS (or a NATS leaf-node per cluster).
- Gateway holds N kubeconfigs (mounted Secret) + `HOPPER_CLUSTERS` config.

---

## 5. Key request flows

**Launch:** `POST /pods` → credit + concurrency check → `placement.select_cluster` →
`registry[cluster].CreatePod(...)` → persist `cluster_id` + `access_host` → return
connection string built from `access_host` (not global `node_ip`).

**Access (SSH/VS Code/terminal/files):** resolve `session.cluster_id` → use that cluster's
context/orchestrator. SSH string = `ssh root@<session.access_host> -p <ssh_port>`.

**Billing/metrics:** owning orchestrator publishes `billing.<cluster>.deducted` /
`metrics.<cluster>.<pod>`; gateway consumers (wildcard + queue group) deduct/persist;
idempotent on `<cluster>:<pod>:<seq>`.

**Recovery:** each orchestrator reconciles only its own cluster (unchanged), stamping
`cluster_id` from the pod label. A cluster outage isolates to that cluster's pods; the
gateway marks unreachable-cluster sessions `unknown` and retries.

---

## 6. Security considerations (carry over from the security review)

- Per-cluster kubeconfigs on the gateway **amplify** finding H-4 (over-privileged gateway
  SA). Mitigate: least-privilege SA **per cluster** (`pods:get,list` + `pods/portforward:create`
  only); keep create/exec/delete on each orchestrator. Prefer the **delegate-I/O-to-orchestrator**
  design (4.4 v2) so the gateway needs **no** cluster kube credentials at all.
- gRPC across clusters must be **mTLS + caller-authz** (fixes security finding B, now
  mandatory since traffic leaves a single cluster's NetworkPolicy boundary).
- Per-cluster IMDS egress blocking (network policies) must be templated so every cluster
  inherits it (finding: user-vm-egress).

---

## 7. Phased implementation plan

Each phase is independently shippable and leaves the single-cluster deploy working
(`cluster_id='default'` is a no-op degenerate case).

**Phase M0 — Introduce `cluster_id` as a no-op (safe on single cluster).**
- Migration: `pod_sessions.cluster_id` + `access_host`.
- Proto: `PodStatus.cluster_id`, `access_host`; regenerate stubs.
- Orchestrator: `HOPPER_CLUSTER_ID`/`HOPPER_PUBLIC_HOST` env; stamp label; populate in `PodStatus`.
- Gateway: persist both on the session; build SSH string from `access_host` (fallback `node_ip`).
- `tx_id` → `<cluster>:<pod>:<seq>`.
- **Verify:** existing single-cluster e2e still green; new columns populated with `'default'`.

**Phase M1 — Cluster registry + gateway fan-out (still one real cluster).**
- `clusters.py` registry from `HOPPER_CLUSTERS`; `OrchestratorClient` per cluster.
- Route every pod-scoped call by `session.cluster_id`.
- `port_forward.py` accepts `cluster_id` (`--context`); NATS subjects namespaced + wildcard consumers.
- **Verify:** register the one cluster twice under two ids pointing at the same endpoint;
  confirm routing works and billing/metrics still reconcile.

**Phase M2 — Placement + second cluster.**
- `placement.py` capacity-aware weighted selection; wire into create.
- Stand up a second member cluster (orchestrator + VM-plane Helm overlay).
- Admin `/nodes` aggregates across clusters (tag rows with `cluster_id`).
- **Verify:** launch lands on both clusters per weight/capacity; access strings resolve per cluster.

**Phase M3 — Harden.**
- mTLS + authz on gRPC; per-cluster least-privilege SAs; templated Cilium/IMDS policies.
- Optional: delegate pod I/O to orchestrators (drop gateway kube creds).
- Admin cluster-registry UI + enable/disable/drain a cluster.

**Deferred (→ DB-backed fleet):** moving authoritative pod state to Postgres + JetStream
work queue; cross-cluster workspace replication (see workspace plan §Risks); GPU-tier
placement affinity.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Persistent workspace (per-user RWO PVC) is cluster-local — a user's `/workspace` doesn't follow them to another cluster | v1: pin a user to a "home cluster" for workspace-bearing launches; v2: object-storage-backed sync or RWX/replicated storage. Document the constraint. |
| Gateway holding N kubeconfigs widens blast radius | Prefer delegate-I/O-to-orchestrator (no gateway kube creds); else least-privilege per-cluster SA. |
| NATS reachability across clusters | NATS leaf nodes per cluster, or a shared control-plane NATS with TLS. |
| `tx_id` collisions if `cluster_id` reused | Treat `cluster_id` as immutable + unique per member; validate at registry load. |
| Split-brain if two orchestrators claim one cluster | One orchestrator per cluster (Deployment `replicas:1` per cluster); wire leader election only if per-cluster HA is later required. |
