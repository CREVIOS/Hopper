# Runbook — Migrate workspaces to Longhorn (Phase 2)

> Moves existing student workspaces from `local-path` to the `longhorn-workspace`
> StorageClass, per user, reversibly. Prereqs: Phase 1 done + benchmark passed
> (`docs/STORAGE.md` §6); the app change that defaults **new** workspaces to
> Longhorn (`HOPPER_WORKSPACE_STORAGE_CLASS`) is deployed. Design: `docs/STORAGE.md`.

## How the flip works

A workspace's storage lives in the `user_workspaces` DB row (`pvc_name`,
`storage_class`) — the orchestrator provisions/attaches whatever `pvc_name`
points at. So migration = copy data to a new Longhorn PVC, then repoint the row.
The column doubles as the migration ledger: `""` = local-path (unmigrated),
`longhorn-workspace` = migrated.

## Order of operations

1. **New workspaces first (no migration).** Set `HOPPER_WORKSPACE_STORAGE_CLASS=longhorn-workspace`.
   From now on every *new* user is born on Longhorn. Only pre-existing `ws-user-*`
   PVCs need the copy below.
2. **Pilot** on team/staff accounts. Migrate 2–3, run for a week, watch for I/O
   complaints and confirm nightly backups appear in Azure.
3. **Batch the rest** off-hours, a handful at a time.

## Migrate one user

The VM **must be stopped** (RWO — the copy Job can't attach an in-use volume).
The idle-shutdown feature or an admin stop handles this.

```bash
# Dry run first (prints the plan, mutates nothing):
USER_ID=<uuid> NAMESPACE=hopper KUBECTL="k3s kubectl" \
  ./scripts/ops/migrate-workspace-to-longhorn.sh

# Apply:
USER_ID=<uuid> NAMESPACE=hopper KUBECTL="k3s kubectl" CONFIRM=1 \
  ./scripts/ops/migrate-workspace-to-longhorn.sh
```

The script: patches the old PV to `Retain` → creates `ws-user-<id>-lh` on
`longhorn-workspace` → runs the copy Job (`k8s/longhorn/jobs/pvc-copy-job.yaml`,
verifies file count + bytes) → prompts you to confirm a backup reached Azure →
swaps the DB pointer. It prints the rollback and cleanup commands at the end.

## Verify (Phase 2 gate)

- `kubectl -n longhorn-system get volumes.longhorn.io` — the new volume is `healthy`.
- The workspace's next VM launch mounts `/workspace` with the data intact.
- Nightly `workspace` RecurringJob backs it up (`lastBackupAt` < 26h; the health
  CronJob checks this).
- **Restore drill:** restore one migrated workspace's backup into a scratch PVC
  and verify file counts (see `longhorn-dr.md`).

## Rollback

Per user, before the old PVC is deleted (kept 14 days): revert the DB row to the
old `pvc_name` + `storage_class=''` (the script prints the exact statement). The
old local-path PVC is untouched, so the next launch reattaches it. No data moves.

## Cleanup (after ~14 quiet days per user)

```bash
kubectl -n hopper delete pvc ws-user-<id>          # old local-path PVC
kubectl delete pv <old-bound-pv>                   # it was patched to Retain, so delete explicitly
```
Track any leftover `Released` PVs in the quarterly sweep (see `longhorn-dr.md`).
