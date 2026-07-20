# Hopper — Storage Architecture (Longhorn)

> How Hopper stores durable data: student workspaces, the Postgres/ledger database, and backups. This document is the source of truth for the migration from node-local `local-path` storage to **Longhorn** distributed block storage, and for the phased, industry-grade rollout that gets us there without a throw-away step.

---

## 1. Why this document exists

Today every piece of durable state in Hopper lives on the k3s **`local-path`** provisioner:

| Data | PVC | Reality today |
|------|-----|---------------|
| Student workspace (`/workspace`) | `ws-user-<id>` (RWO, per user) | Node-local, **single copy, no backup**. Disk loss = the student's work is gone. |
| Postgres / TimescaleDB (users, credits ledger, sessions) | `postgres-pvc` (10Gi) | Node-local single copy. Nightly `pg_dump` lands on **another local-path PVC on the same node** — not off-box. |
| NATS JetStream | `emptyDir` | **Ephemeral** — event/metrics state is lost on every pod restart. |
| Backups | `pg-backups` (10Gi) | local-path, same node as the data it protects. |

Three structural problems follow:

1. **No durability for student data.** A single node/disk failure loses every workspace, with nothing to restore from.
2. **`local-path` pins a pod to one node.** An RWO local volume can only be mounted on the node that holds it, so Hopper cannot become multi-node without a distributed storage layer — the current single-VPS deployment is a ceiling, not a choice.
3. **Storage capacity is a guess.** Admission accounting uses a configured constant (`HOPPER_CLUSTER_STORAGE_TOTAL="150Gi"`) because the orchestrator's `ListNodes` reports no storage; it also undercounts (only *live* VMs, at legacy plan-disk sizes, not the real per-user PVC sizes), and raising a plan's `workspace_gb` never grows an existing PVC (FR-HC-30 unimplemented).

[Longhorn](https://longhorn.io/) (CNCF, Apache-2.0, maintained by SUSE; the default storage engine in Rancher/Harvester) is a lightweight distributed block-storage system for Kubernetes that directly closes all three: **synchronous cross-node replication, snapshots, incremental off-cluster backups, online volume expansion, and first-class capacity/health metrics.** Crucially, the storage-class plumbing to adopt it **already exists end-to-end** in Hopper (DB `user_workspaces.storage_class` → gateway → gRPC `CreatePodRequest.storage_class` → orchestrator PVC), currently hardcoded to `""` (cluster default).

### Honest tradeoffs (why this is phased, not a flip of a switch)

Longhorn is not free. Its data path runs in user space, which **costs IOPS/latency** versus a raw local disk — and Hopper's workload (VM root/`/workspace` disk I/O) is exactly the latency-sensitive class most affected. It reserves ~12% CPU + ~1 GiB RAM per node for its instance-manager, needs `open-iscsi` on every node, and its real HA value only appears at ≥2–3 nodes. Community reports also flag replica-rebuild filesystem-corruption risk under node churn. This plan therefore treats a **benchmark as a hard gate** before any student data moves, keeps `local-path` as a supported fallback (mixed fleet), and anchors durability on **off-cluster backups** from day one so a single node buys safety even before replication exists.

---

## 2. Architecture decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Install Longhorn via pinned Helm** (`longhorn/longhorn --version 1.12.0`) into `longhorn-system`, run **manually from a runbook**; settings live in git at `k8s/longhorn/values.yaml`. | Mirrors the repo's existing addon precedent (`k8s/deploy/05-cert-manager.yaml`: addon installed out-of-band from a pinned source, only policy objects in the numbered deploy file). Helm keeps the ~15 non-default settings reviewable in one file and provides the `preUpgradeChecker` job. CD (`publish.yml`, `kubectl set image` only) is untouched. |
| D2 | **`local-path` stays the cluster-default StorageClass.** Workspaces move to Longhorn per-user via the `user_workspaces.storage_class` DB column. | Gives a mixed fleet during migration and a trivially reversible rollout (revert a DB row). Never flip the cluster default — that would silently move unrelated PVCs. |
| D3 | **Two Hopper StorageClasses:** `longhorn-workspace` (student `/workspace`) and `longhorn-platform` (Postgres, NATS, pg-backups). Both `reclaimPolicy: Retain`, `allowVolumeExpansion: true`, `dataLocality: best-effort`, `fsType: ext4`, auto-enrolled into backup RecurringJob groups via `recurringJobSelector`. | Student/ledger data must survive an accidental PVC delete (`Retain`). Separate classes let platform data take a higher replica count and its own backup cadence. `best-effort` locality keeps the hot replica on the VM's node for I/O while still replicating. |
| D4 | **Backups → Azure Blob** (`azblob://longhorn@core.windows.net/`), a dedicated storage account, credentials as an out-of-band secret. | Off-VM durability with zero extra infrastructure to operate; Hopper already runs on Azure. In-cluster snapshots alone do not survive node/site loss. |
| D5 | **Postgres migrates by a cold file copy**, not dump/restore; `pg_dump` stays as the logical safety net (its PVC moves to Longhorn so dumps land off-box too). | A cold copy of `pgdata` between PVCs (Postgres scaled to 0) is bit-identical and avoids the TimescaleDB `pre/post_restore` dance. Both a block-backup layer and a logical-dump layer is defence in depth. |
| D6 | **Longhorn UI is never publicly exposed** — access via `kubectl port-forward`. No metrics stack until Phase 5; interim health is a kubectl CronJob that fails loudly. | Matches the Keycloak-admin-console precedent. A public storage control plane is attack surface with no operational need for a one-operator team. |
| D7 | **V1 data engine only.** | V2/SPDK needs kernel ≥6.7, hugepages, and raw NVMe, and disrupts live volumes on upgrade — wrong fit for this cluster. |
| D8 | **Every application code change is inert when Longhorn is absent.** | Local dev (OrbStack) and any un-migrated environment keep working on `local-path` with byte-identical behaviour; guards skip expansion, capacity falls back to the config pool. |

---

## 3. Phased rollout

Each phase has an **entry criterion**, concrete **artifacts**, a **verification gate**, and a **rollback**. Nothing is throw-away: Phase 1 runs on today's single VPS at `replica=1`; replicas rise to 2–3 as nodes are added in Phase 4.

### Phase 0 — Node & Azure prerequisites *(operator, no cluster change)*
- **Artifacts:** `docs/runbooks/longhorn-node-setup.md`, Azure section of `docs/runbooks/longhorn-install.md`.
- **Steps:** attach + ext4-format + fstab-mount a dedicated managed disk at `/var/lib/longhorn` (~256 GiB Premium SSD — the disk tier is the main benchmark lever); `apt-get install -y open-iscsi && systemctl enable --now iscsid`; blacklist Longhorn devices in `multipathd`; run Longhorn's pinned `environment_check.sh`; create the Azure storage account + **private** `longhorn` container (**never** attach a lifecycle-management rule — it would race Longhorn's own retention and corrupt backup metadata).
- **Gate:** `iscsid` active; `/var/lib/longhorn` mounted on the new disk; environment check all-green; container reachable with the account key.
- **Rollback:** detach disk; remove `open-iscsi`. Nothing in-cluster.

### Phase 1 — Install Longhorn (single node, `replica=1`) + backups + benchmark
- **Artifacts:** `k8s/longhorn/values.yaml`, `k8s/deploy/07-storage.yaml`, `k8s/longhorn/health-check-cronjob.yaml`, `k8s/longhorn/bench/fio-job.yaml`, `docs/runbooks/longhorn-install.md`.
- **Steps:** create the `azblob-backup-credentials` secret; `helm upgrade --install longhorn … --version 1.12.0 -f k8s/longhorn/values.yaml`; `kubectl apply -f k8s/deploy/07-storage.yaml`; run a scratch backup→delete→restore→diff drill in a throwaway `storage-bench` namespace; run the fio benchmark (§6); take a Longhorn system backup.
- **Gate:** all `longhorn-system` pods Ready; `BackupTarget` shows `Available`; scratch backup visible as Azure objects and restore diff clean; **benchmark passes (§6)**; health CronJob green.
- **Rollback:** safe while no app data is on Longhorn — delete `07-storage.yaml` resources, flip `deleting-confirmation-flag`, `helm uninstall`.

### Phase 2 — Workspaces onto Longhorn
- **Entry:** Phase 1 gate + benchmark pass + App-PR-1 shipped (storage-class config).
- **Steps:** set `HOPPER_WORKSPACE_STORAGE_CLASS=longhorn-workspace` so **new** workspaces are born on Longhorn; migrate existing `ws-user-*` per user with `scripts/ops/migrate-workspace-to-longhorn.sh` (patch old PV → `Retain`, copy Job, verify byte counts, immediate backup, DB pointer swap, keep old PVC 14 days); pilot on team accounts first, then batch off-hours (VM must be stopped — RWO).
- **Gate:** pilot workspaces backed up nightly (<26h age), one restored to a scratch PVC and verified, one week with no I/O complaints.
- **Rollback:** per user, revert the `user_workspaces` row to the old PVC (untouched). New-workspace default back to `""`.

### Phase 3 — Platform data (Postgres, NATS, pg-backups) *(maintenance window)*
- **Steps:** on-demand `pg_dump` first; scale writers + Postgres to 0; cold-copy `pgdata` → `longhorn-platform` PVC; swap `claimName` and add `strategy: Recreate` (RWO multi-attach hazard on rollout); give NATS a real 2Gi PVC (fresh — today's JetStream state is already ephemeral); point `pg-backups` at `longhorn-platform`.
- **Gate:** Postgres up with row counts matching the pre-migration dump manifest; login + VM launch work; nightly platform backup in Azure; **Postgres restore drill** into a scratch PVC passes.
- **Rollback:** revert `claimName` to the retained old PV.

### Phase 4 — Multi-node scale-out (2 → 3 nodes)
- **Steps:** join node(s) per `docs/runbooks/node-join.md` (k3s agent + all node prereqs); bump `defaultReplicaCount`; recreate the StorageClasses with the new replica counts (params are immutable — same names, existing PVs unaffected); run `scripts/ops/longhorn-set-replicas.sh` to patch existing volumes in batches off-hours.
- **Gate:** every volume shows N healthy replicas on distinct nodes; **node-kill drill** — cordon+shutdown a node, volumes stay available, pods reschedule (Pod-Deletion-Policy set day 1), replicas rebuild on return; re-run the benchmark (replica>1 changes the write path).
- **Rollback:** cordon the new node; set replica counts back; volumes stay healthy on survivors.

### Phase 5 — Monitoring
- **Artifacts:** `k8s/monitoring/` (deliberately separate from the aspirational GPU-cluster `observability/`): pinned kube-prometheus-stack (single replica, small PV on `longhorn-platform`), Longhorn `ServiceMonitor`, Grafana dashboard 13032, alert rules (volume robustness degraded/faulted, backup age > 26h, node storage > 75%, instance-manager restarts) delivered via the existing SMTP relay.
- **Gate:** alerts fire in a controlled test (cordon a disk; fail a backup with a bad key).

---

## 4. StorageClasses & backups

Both classes are provisioned by `driver.longhorn.io` in `k8s/deploy/07-storage.yaml` (applied out-of-band, like `06-backup.yaml`). Replica counts shown are Phase-1 values; Phase 4 recreates the classes with `2` (workspace) / `3` (platform).

```
longhorn-workspace   numberOfReplicas=1  reclaimPolicy=Retain  allowVolumeExpansion=true
                     dataLocality=best-effort  fsType=ext4  staleReplicaTimeout=2880
                     recurringJobSelector=[{name:workspace,isGroup:true}]
longhorn-platform    numberOfReplicas=1  reclaimPolicy=Retain  allowVolumeExpansion=true
                     dataLocality=best-effort  fsType=ext4
                     recurringJobSelector=[{name:platform,isGroup:true}]
```

**RecurringJobs** (in `07-storage.yaml`, `longhorn-system`; explicit groups only — nothing in Longhorn's `default` group, so no silent enrolment):

| Job | Task | Cron (UTC) | Retain |
|-----|------|------------|--------|
| `workspace-backup-nightly` | backup | `30 21 * * *` | 7 |
| `platform-backup-nightly` | backup | `0 22 * * *` | 7 |
| `snapshot-prune-weekly` | snapshot-delete | `0 19 * * 6` | 5 |
| `snapshot-cleanup-weekly` | snapshot-cleanup | `30 19 * * 6` | 0 |
| `workspace-trim-weekly` | filesystem-trim | `0 20 * * 6` | 0 |

Cadence is staggered after the existing 21:00 `pg_dump` so the 22:00 platform backup captures a filesystem that already holds the fresh dump. Backups are incremental after the first full. **Postgres keeps both layers**: `pg_dump` (logical, selective, Timescale-safe restore) *and* Longhorn block backups (crash-consistent, WAL-replay on restore). Full DR procedures — single-workspace restore, Postgres restore decision table, full-cluster rebuild, quarterly drill schedule — live in `docs/runbooks/longhorn-dr.md`.

---

## 5. Application integration

The code changes ship as independently-shippable PRs, each a no-op when Longhorn is absent (D8):

- **Workspace storage class (App-1):** `HOPPER_WORKSPACE_STORAGE_CLASS` → `workspace_service` stamps it on **new** `user_workspaces` rows; existing rows keep their recorded class (the column is the per-user migration ledger).
- **Expansion + admin resize, FR-HC-30 (App-2):** `get_or_create_workspace` reconciles `capacity_gb` **upward** (never shrink, clamped by quota) on launch/resume; the Go `EnsureWorkspacePVC` patches the PVC's requested size upward **only** when its StorageClass has `allowVolumeExpansion` (skip-and-warn otherwise — `local-path` cannot expand); admin `POST /admin/workspaces/{user}/resize` writes desired state ("applies at next VM start"). This PR also fixes a found bug: **queue-admitted VMs launched with no workspace PVC and no SSH keys** (`vm_scheduler.reconcile_pass` Phase 2 omitted them).
- **Capacity truth (App-3a/3b):** admission counts **all** `user_workspaces` rows at their real `workspace_gb`; when Longhorn is installed, `NodeInfo` gains storage fields fed from the `nodes.longhorn.io` CRD so the admin dashboard shows **measured** capacity, with the config pool as a graceful fallback.
- **Surfacing (App-5):** admin Nodes/Storage tabs show real capacity + per-workspace usage and a resize control; deep volume operations stay in the Longhorn UI.

---

## 6. Benchmark gate (mandatory before any workspace flips)

Run in a scratch `storage-bench` namespace, one PVC per class (`local-path` on the current disk = the real baseline; `longhorn-workspace` on the dedicated disk), using the pinned `kbench`/fio job. Four profiles, 4 GiB file, 60s, `--direct=1 --ioengine=libaio`. **All must hold at `replica=1`:**

- 4k rand-read ≥ 50% of local-path **and** ≥ 800 IOPS
- 4k rand-write ≥ 50% of local-path **and** ≥ 400 IOPS
- fsync p99 ≤ 15 ms **and** ≤ 3× local-path
- seq read/write ≥ 60% of local-path
- UX probe in a real VM pod: `git clone` + `pip install numpy` wall-clock ≤ 1.5× local-path

**Fail → ladder:** `dataLocality: strict-local` (single-replica phase) → bump disk tier (P15→P20) → if still failing, **workspaces stay on `local-path`** (the per-workspace `storage_class` makes a mixed fleet a supported end-state); platform data (modest I/O, durability-driven) may still adopt Longhorn. Re-run the gate at Phase 4 after `replica>1`.

---

## 7. Risks

| Risk | Mitigation |
|------|------------|
| IOPS/latency regression degrades VM UX | Benchmark is a hard gate (§6); mixed-fleet rollback; Premium disk; `best-effort` locality |
| Instance-manager overhead starves the VPS (12% CPU + ~1 GiB/node) | Phase-0 capacity check; resize before install; weekly `kubectl top` |
| `replica=1` adds a failure layer with no redundancy yet | Nightly Azure backups from day 1; `snapshotDataIntegrity: fast-check`; Phase 4 raises replicas |
| Disk-full from over-provisioning + snapshot growth | `minimal-available 25%`, weekly prune/cleanup/trim, health CronJob threshold |
| RWO multi-attach deadlock on Postgres/NATS rollout | `strategy: Recreate` shipped with the claim swap |
| Rebuild-related FS corruption under node churn | Backups-before-migration ordering, `snapshot-data-integrity` checks, drain policy keeps last replica |
| Azure account-key leak (public repo) | Secret out-of-band; dedicated account; rotation runbook |
| Upgrade discipline (sequential minors, no downgrade, ~1yr EOL) | Pinned chart version; `preUpgradeChecker`; system-backup-before-upgrade |
| Accidental Longhorn uninstall wipes volumes | `deleting-confirmation-flag` stays false; `Retain` reclaim on both classes |

---

## 8. Explicitly deferred

FR-HC-30 "delete workspace entirely" and immediate resize of a *running* VM (both need a new orchestrator RPC — ride the next proto regen) · auto-derived replica factor from Longhorn settings · V2/SPDK data engine · RWX shared course/dataset volumes · account-deletion cleanup of `Retain`ed PVs (interim: quarterly orphaned-PV sweep in the DR runbook).
