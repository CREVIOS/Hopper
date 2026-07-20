# Runbook — Longhorn disaster recovery

> Restore procedures for the three failure classes Hopper plans for: a single
> lost workspace, Postgres loss, and full-cluster loss. Anchored on the Azure
> Blob backup target configured in `docs/runbooks/longhorn-install.md`.
> In-cluster snapshots are for fast rollback only — **backups** are what survive
> node/disk/site loss.

## 0. Before you need it

- **System backup before every upgrade** and after settings changes: Longhorn UI
  → *Setting → General* or a `SystemBackup` CR. Captures StorageClasses,
  RecurringJobs, settings, and volume metadata.
- **Quarterly drill** (calendar): do one *workspace* restore and one *Postgres
  scratch* restore (below), and log the result + wall-clock at the bottom of this
  file. A backup you have never restored is a hope, not a backup.

## 1. Single workspace restore

Symptoms: a student's `/workspace` is corrupted or a volume faulted.

1. Stop the user's VM (RWO must be detached).
2. Longhorn UI → **Backup** → pick the workspace's backup → **Restore** into a
   **new** volume name (Longhorn refuses to restore over an existing volume of
   the same name).
3. Create a PV/PVC bound to the restored volume, or restore under the existing
   `ws-user-<id>-lh` name after deleting the faulted one.
4. If you restored under a new name, repoint the DB row (same statement the
   migration script uses):
   `UPDATE user_workspaces SET pvc_name='<restored>' WHERE user_id='<uuid>';`
5. Relaunch the VM; confirm files.

## 2. Postgres restore (decision table)

| Situation | Restore from | How |
|-----------|-------------|-----|
| Logical corruption / bad migration / dropped rows | **pg_dump** (logical) | `06-backup.yaml` header runbook: scale writers to 0, `pg_restore --clean --if-exists -d "$DB_URL" /backups/<file>.dump`. For TimescaleDB, wrap with `SELECT timescaledb_pre_restore();` … `SELECT timescaledb_post_restore();`. |
| Volume/disk loss (PVC gone/faulted) | **Longhorn block backup** of `postgres-pvc` | Restore the volume from backup → new PVC → swap `claimName` in `01-infra.yaml` (`strategy: Recreate` is already set) → scale Postgres up. Crash-consistent: Postgres replays WAL on start. |

Both layers exist on purpose (D5): dumps are selective + human-readable, block
backups are whole-volume + fast. After any restore: smoke `/readyz`, a login, and
a VM launch.

## 3. Full-cluster loss

1. Rebuild the node(s): `docs/runbooks/longhorn-node-setup.md` + k3s.
2. Reinstall Longhorn from the pinned chart + **the same `k8s/longhorn/values.yaml`**
   (`docs/runbooks/longhorn-install.md`) pointed at the **same** Azure Blob target.
3. Longhorn lists every backup from the target automatically. Restore each volume,
   recreating PV/PVCs with their **original names** (`postgres-pvc`, `ws-user-*-lh`).
4. Recreate Secrets from the out-of-band store; `kubectl apply -f k8s/deploy/`.
5. Smoke: `/readyz` (db + nats + orchestrator), login, VM launch + `/workspace`.

RPO = the backup cadence (nightly → ≤24h data loss on total loss; snapshots
narrow in-cluster rollback further). RTO for a workspace is low because the data
is already in Azure — restore is a download, not a rebuild.

## 4. Orphaned-PV sweep (quarterly, until account-deletion cleanup ships)

`Retain` reclaim means deleting a PVC leaves the PV `Released`, not reclaimed.
Periodically reconcile against live users:

```bash
kubectl get pv | grep Released         # candidates
# cross-check each against user_workspaces / deleted accounts before deleting
```

---

## Drill log

| Date | Drill | Result | Wall-clock | Operator |
|------|-------|--------|-----------|----------|
| _(fill in each quarter)_ | | | | |
