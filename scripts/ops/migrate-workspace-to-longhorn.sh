#!/usr/bin/env bash
# =============================================================================
# Migrate ONE user's workspace PVC from local-path to Longhorn.
#
# Per-user, reversible, and safe to run one at a time (Phase 2 of the Longhorn
# rollout — docs/STORAGE.md, docs/runbooks/workspace-migration.md). It copies
# the old PVC's data into a new Longhorn-backed PVC, verifies the copy, takes a
# backup, then swaps the DB pointer so the next VM launch uses the new volume.
#
# PRECONDITION: the user's VM must be STOPPED (RWO volume can only attach once).
#
# Usage:
#   USER_ID=<uuid> ./scripts/ops/migrate-workspace-to-longhorn.sh
# Optional env:
#   NAMESPACE=hopper  KUBECTL="k3s kubectl"  COPY_IMAGE=busybox:1.36
#   CONFIRM=1   # actually mutate (create PVC, run copy, swap DB). Default = dry plan.
#
# Rollback (until the old PVC is deleted after 14 days): re-run the DB swap with
# the OLD pvc_name/storage_class — the script prints the exact statement.
# =============================================================================
set -euo pipefail

USER_ID="${USER_ID:?set USER_ID to the user's UUID}"
NAMESPACE="${NAMESPACE:-hopper}"
COPY_IMAGE="${COPY_IMAGE:-busybox:1.36}"
CONFIRM="${CONFIRM:-0}"
SC="longhorn-workspace"
HERE="$(cd "$(dirname "$0")/../.." && pwd)"   # repo root

kube() { if [ -n "${KUBECTL:-}" ]; then $KUBECTL "$@"; else kubectl "$@"; fi; }
say()  { printf '\n=== %s ===\n' "$*"; }

SRC_PVC="ws-user-${USER_ID}"
SRC_PVC="$(printf '%s' "$SRC_PVC" | tr '[:upper:]' '[:lower:]')"
DST_PVC="${SRC_PVC}-lh"
JOB_NAME="ws-migrate-$(printf '%s' "$USER_ID" | tr -cd 'a-z0-9' | cut -c1-12)"

say "target"
echo "user_id:   $USER_ID"
echo "namespace: $NAMESPACE"
echo "src PVC:   $SRC_PVC (local-path)"
echo "dst PVC:   $DST_PVC ($SC)"

say "preflight"
if ! kube -n "$NAMESPACE" get pvc "$SRC_PVC" >/dev/null 2>&1; then
  echo "ERROR: source PVC $SRC_PVC not found"; exit 1
fi
CAP="$(kube -n "$NAMESPACE" get pvc "$SRC_PVC" -o jsonpath='{.spec.resources.requests.storage}')"
BOUND_PV="$(kube -n "$NAMESPACE" get pvc "$SRC_PVC" -o jsonpath='{.spec.volumeName}')"
echo "capacity:  $CAP    bound PV: $BOUND_PV"
# The VM must be stopped — the RWO source can't attach to the copy Job otherwise.
if kube -n "$NAMESPACE" get volumeattachment -o jsonpath="{range .items[?(@.spec.source.persistentVolumeName=='$BOUND_PV')]}{.metadata.name}{end}" 2>/dev/null | grep -q .; then
  echo "ERROR: $SRC_PVC is still attached — stop the user's VM first."; exit 1
fi

if [ "$CONFIRM" != "1" ]; then
  say "DRY RUN (set CONFIRM=1 to apply)"
  echo "would: 1) patch PV $BOUND_PV reclaimPolicy=Retain"
  echo "       2) create PVC $DST_PVC ($CAP, $SC)"
  echo "       3) run copy Job $JOB_NAME ($SRC_PVC -> $DST_PVC)"
  echo "       4) back up the new volume, then swap the DB pointer"
  exit 0
fi

say "1. protect the old PV (reclaimPolicy=Retain)"
[ -n "$BOUND_PV" ] && kube patch pv "$BOUND_PV" -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'

say "2. create the Longhorn destination PVC"
kube -n "$NAMESPACE" apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${DST_PVC}
spec:
  accessModes: ["ReadWriteOnce"]
  storageClassName: ${SC}
  resources: { requests: { storage: ${CAP} } }
EOF

say "3. run + wait for the copy Job"
kube -n "$NAMESPACE" delete job "$JOB_NAME" --ignore-not-found
NAMESPACE="$NAMESPACE" JOB_NAME="$JOB_NAME" SRC_PVC="$SRC_PVC" DST_PVC="$DST_PVC" COPY_IMAGE="$COPY_IMAGE" \
  envsubst < "$HERE/k8s/longhorn/jobs/pvc-copy-job.yaml" | kube apply -f -
if ! kube -n "$NAMESPACE" wait --for=condition=complete "job/$JOB_NAME" --timeout=1h; then
  echo "ERROR: copy Job did not complete — logs:"; kube -n "$NAMESPACE" logs "job/$JOB_NAME" --tail=30; exit 1
fi
kube -n "$NAMESPACE" logs "job/$JOB_NAME" --tail=5

say "4. back up the new Longhorn volume (offsite copy BEFORE the pointer swap)"
echo "Trigger a backup of the volume behind $DST_PVC now (Longhorn UI or a Backup CR),"
echo "or rely on the nightly 'workspace' RecurringJob. Wait for it to reach Azure before deleting the old PVC."

say "5. swap the DB pointer"
DB_URL="$(kube -n "$NAMESPACE" get secret hopper-db -o jsonpath='{.data.database-url}' | base64 -d | sed 's/+asyncpg//')"
SQL="UPDATE user_workspaces SET pvc_name='${DST_PVC}', storage_class='${SC}' WHERE user_id='${USER_ID}';"
echo "running: $SQL"
kube -n "$NAMESPACE" exec deploy/postgres -- psql "$DB_URL" -c "$SQL"

say "done"
echo "Rollback (old PVC kept until you delete it): "
echo "  kube -n $NAMESPACE exec deploy/postgres -- psql \"\$DB_URL\" -c \"UPDATE user_workspaces SET pvc_name='${SRC_PVC}', storage_class='' WHERE user_id='${USER_ID}';\""
echo "After ~14 quiet days: kube -n $NAMESPACE delete pvc $SRC_PVC ; kube delete pv $BOUND_PV"
