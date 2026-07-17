# ArgoCD GitOps (HOP-22 25.3)

`app-of-apps.yaml` is the root Application; every child Application lives in
`apps/`. Today there is one child: `hopper-platform` → `charts/hopper` with
`values-prod.yaml`.

## Install

```bash
# 1. ArgoCD itself (single-node k3s: the core install is enough)
kubectl create namespace argocd
kubectl apply -n argocd -f \
  https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.3/manifests/install.yaml

# 2. The app-of-apps root
kubectl apply -n argocd -f k8s/argocd/app-of-apps.yaml

# 3. UI access (no ingress exposed on purpose):
kubectl port-forward svc/argocd-server -n argocd 8081:443
# admin password: kubectl -n argocd get secret argocd-initial-admin-secret \
#   -o jsonpath='{.data.password}' | base64 -d
```

## Why sync is manual (for now)

The repo's working CD pipeline is `publish.yml`: merge to main → build →
GHCR → SSH → `kubectl set image`. Two ArgoCD features conflict with the
platform as it runs today:

1. **Self-heal** would revert every CI image rollout minutes after it lands
   (git pins a bootstrap tag; CI moves the live tag). Mitigated by the
   `ignoreDifferences` on the image field, but still not worth automating
   until the pipeline itself is GitOps-native.
2. **Prune** would try to delete everything in the `hopper` namespace that
   isn't in the chart: the out-of-band Secrets, the dynamically-created
   `vm-net-group-*` NetworkPolicies, and — catastrophically — **running
   user VM pods and their workspace PVCs**, which are created by the
   orchestrator, not by git.

## Cutover plan (when the team is ready)

1. Change `publish.yml`'s deploy job: instead of SSH + `kubectl set image`,
   commit the new SHA tag to `charts/hopper/values-prod.yaml`
   (`global.imageTag`) on main.
2. Remove the `ignoreDifferences` block and enable
   `syncPolicy.automated: {selfHeal: true}` (still **no prune** — user VM
   pods live in the same namespace).
3. Adopt the live resources into Helm ownership first — see
   `charts/hopper/README.md` ("Adopting the EXISTING prod cluster").
4. Retire the `VPS_*` SSH secrets from the repo settings.

Until then: pushes to main still deploy via the SSH pipeline; ArgoCD gives
drift *visibility* (diff between git and cluster) and one-click manual syncs.
