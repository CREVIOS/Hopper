# Hopper Helm chart (HOP-22 25.2)

Parameterized port of the raw manifests in `k8s/deploy/` — verified to
render **identically** (up to added `app.kubernetes.io/*` labels) to those
manifests with `values-prod.yaml`.

## Layout

| file | purpose |
|---|---|
| `values.yaml` | complete defaults (single-node shape) |
| `values-dev.yaml` | local k3d/k3s: `start-dev` Keycloak, dev secrets rendered in-cluster, no ingress/TLS/netpol/backup |
| `values-staging.yaml` | prod topology on a staging host, Let's Encrypt **staging** issuer |
| `values-prod.yaml` | `hopper.farefin.com` — faithful to the live cluster |

## Fresh install

```bash
helm install hopper ./charts/hopper -n hopper --create-namespace \
  -f charts/hopper/values-<env>.yaml
```

Prereqs (cluster-level, not chart-managed): nginx ingress controller,
cert-manager (if `certManager.enabled`), a NetworkPolicy-enforcing CNI
(Cilium — flannel silently ignores policies), and for prod the node-local
pieces documented in `k8s/deploy/node/` (SMTP relay) plus the VM template
images imported into containerd.

## Secrets

`secrets.create=false` (staging/prod): the five Secrets (`hopper-db`,
`keycloak-admin`, `hopper-keycloak-admin`, `hopper-brevo`, `hopper-smtp`)
must already exist — provision them out-of-band with the runbooks in
`k8s/deploy/00-secrets.yaml`. This repo is public; real values never go
through git, and a `helm upgrade` must never overwrite live credentials.

`secrets.create=true` (dev only) renders them with the dev defaults from
`values.yaml`.

## Adopting the EXISTING prod cluster (read before installing over prod!)

Prod was created with `kubectl apply` from `k8s/deploy/`, so the objects
carry no Helm ownership metadata and `helm install` will fail with
"invalid ownership metadata". To adopt without recreating anything:

```bash
# 1. Stamp Helm ownership on every chart-managed object (idempotent):
for r in $(helm template hopper charts/hopper -n hopper -f charts/hopper/values-prod.yaml \
           | kubectl get -n hopper -f - -o name 2>/dev/null); do
  kubectl -n hopper label $r app.kubernetes.io/managed-by=Helm --overwrite
  kubectl -n hopper annotate $r meta.helm.sh/release-name=hopper \
      meta.helm.sh/release-namespace=hopper --overwrite
done
# 2. Then a regular upgrade --install takes over:
helm upgrade --install hopper charts/hopper -n hopper -f charts/hopper/values-prod.yaml
```

Verify with `helm diff` (plugin) or `helm upgrade --dry-run` first. The
`kubectl set image` CD pipeline keeps working after adoption — but every
`helm upgrade` resets images to the values-file tag, so bump
`global.imageTag` to the current deploy SHA before upgrading (check with
`kubectl get deploy -n hopper -o jsonpath='{.items[*].spec.template.spec.containers[0].image}'`).

## What the chart deliberately does NOT manage

- **Databases' data** — PVCs are created but never deleted by helm
  (`helm uninstall` leaves them; delete manually if you really mean it).
- **DB migrations** — still run out-of-band (`alembic upgrade head`; see
  `services/api-gateway/alembic/env.py` for URL resolution).
- **Keycloak realm config** — realm `hopper`, clients, post-logout redirect
  URIs are provisioned via kcadm (see `scratchpad/kc-bootstrap.sh` pattern).
- **VM template images** — node-local containerd imports
  (`images/hopper-vm*`, `make vm-images`).
