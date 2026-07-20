# Runbook — Install & operate Longhorn v1.12.0

> Installs Longhorn into `longhorn-system` and wires the Azure Blob backup
> target. Prereq: every node prepared per `docs/runbooks/longhorn-node-setup.md`.
> Design context: `docs/STORAGE.md`.

## Azure prerequisites (out-of-band, one time)

Create a **dedicated** storage account + private container for Longhorn backups.
Do NOT reuse an account that has lifecycle-management rules — they would race
Longhorn's own retention and corrupt backup metadata.

```bash
az storage account create -n hopperlonghornbackup -g <rg> -l <region> \
  --sku Standard_LRS --kind StorageV2            # GRS is the DR upgrade path
az storage container create --account-name hopperlonghornbackup -n longhorn \
  --auth-mode key
az storage account keys list -n hopperlonghornbackup -g <rg> \
  --query '[0].value' -o tsv                     # -> AZBLOB_ACCOUNT_KEY
```

## Install

```bash
helm repo add longhorn https://charts.longhorn.io && helm repo update

# 1. Namespace + backup-target secret FIRST (values.yaml references the secret).
kubectl create namespace longhorn-system
kubectl -n longhorn-system create secret generic azblob-backup-credentials \
  --from-literal=AZBLOB_ACCOUNT_NAME=hopperlonghornbackup \
  --from-literal=AZBLOB_ACCOUNT_KEY='<key-from-above>'

# 2. Install, pinned, with our settings.
helm upgrade --install longhorn longhorn/longhorn \
  -n longhorn-system --version 1.12.0 \
  -f k8s/longhorn/values.yaml

# 3. Storage policy (StorageClasses + RecurringJobs). Applied out-of-band, like 06-backup.yaml.
kubectl apply -f k8s/deploy/07-storage.yaml
```

## Verify (Phase 1 gate)

```bash
kubectl -n longhorn-system get pods                    # all Ready
kubectl -n longhorn-system get backuptarget            # STATUS Available
kubectl get storageclass                               # longhorn-workspace, longhorn-platform present; local-path still (default)
kubectl -n longhorn-system get recurringjobs           # 5 jobs
```

Scratch backup→restore drill (proves the Azure target round-trips before any real data):

```bash
kubectl create namespace storage-bench
kubectl -n storage-bench apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: bench }
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn-workspace
  resources: { requests: { storage: 1Gi } }
EOF
# write data, take a backup via the UI or a Backup CR, delete the volume,
# restore from backup, and diff. Steps detailed in longhorn-dr.md.
kubectl delete namespace storage-bench
```

Then run the benchmark gate (`k8s/longhorn/bench/fio-job.yaml`, criteria in
`docs/STORAGE.md` §6) and the health check (`k8s/longhorn/health-check-cronjob.yaml`).
Finally take a **system backup** (Settings → General, or a `SystemBackup` CR).

## Access the UI (port-forward only — never exposed publicly)

```bash
kubectl -n longhorn-system port-forward svc/longhorn-frontend 8081:80
# browse http://localhost:8081
```

## Upgrade (strict rules)

- Sequential minors only (1.12 → 1.13 → 1.14; a skip is rejected by the chart).
- **No downgrade.** Take a Longhorn system backup first. Never upgrade with a
  Faulted volume.
```bash
helm repo update
helm upgrade longhorn longhorn/longhorn -n longhorn-system --version 1.13.x -f k8s/longhorn/values.yaml
```

## Uninstall (guarded)

Longhorn refuses to uninstall by default to prevent data loss. Both Hopper
StorageClasses are `reclaimPolicy: Retain`, so PVs survive even then.
```bash
kubectl -n longhorn-system patch settings.longhorn.io deleting-confirmation-flag \
  --type=merge -p '{"value":"true"}'
helm uninstall longhorn -n longhorn-system
```

## Azure key rotation

Rotate one key at a time (Azure keeps two): regenerate `key2`, update the secret,
confirm the `BackupTarget` re-validates, then regenerate `key1` next cycle.
```bash
kubectl -n longhorn-system delete secret azblob-backup-credentials
kubectl -n longhorn-system create secret generic azblob-backup-credentials \
  --from-literal=AZBLOB_ACCOUNT_NAME=hopperlonghornbackup --from-literal=AZBLOB_ACCOUNT_KEY='<new-key>'
# Longhorn re-reads within backupstorePollInterval (300s); verify BackupTarget stays Available.
```
