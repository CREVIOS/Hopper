# Hopper

A self-hosted VM cloud platform for universities. Slice and share bare-metal compute as isolated containers with SSH access, credit-based billing, and Keycloak SSO.

## Architecture

```
Browser ──► Nginx Ingress ──► Frontend (SvelteKit)
                           ──► API Gateway (FastAPI)  ──► PostgreSQL (TimescaleDB)
                           ──► Keycloak (OIDC SSO)    ──► NATS (JetStream)
                                    │
                                    ▼ gRPC
                              Orchestrator (Go) ──► Kubernetes API
                                    │                    │
                                    ▼                    ▼
                              Billing Ticker        VM Pods + SSH Services
                                    │
                                    ▼
                              NATS Events ──► API Gateway (credit deduction)
```

### Services

| Service | Language | Port | Purpose |
|---------|----------|------|---------|
| **Frontend** | SvelteKit/Node | 3000 | Web UI — dashboard, VM management, credits, admin |
| **API Gateway** | Python/FastAPI | 8000 | REST API — auth, pods, credits, admin endpoints |
| **Orchestrator** | Go/gRPC | 50051 | K8s pod lifecycle, billing ticker, metrics publisher |
| **PostgreSQL** | TimescaleDB | 5432 | Users, pod sessions, double-entry credit ledger |
| **NATS** | JetStream | 4222 | Async events — billing deductions, metrics streaming |
| **Keycloak** | Java | 8080 | OIDC identity provider, university SSO support |

### Key Flows

**VM Creation:** User picks a plan (small/medium/large) → API checks credit balance → inserts PodSession → calls orchestrator via gRPC → orchestrator creates K8s Pod with CPU/RAM limits + NodePort Service for SSH → returns SSH port → billing ticker starts.

**Billing Loop:** Orchestrator ticks every 60s per running VM → publishes `billing.deducted` to NATS → API gateway consumes it, calls `deduct_credits()` on the double-entry ledger → if balance hits 0, publishes `billing.exhausted` → orchestrator auto-terminates the VM.

**Metrics Streaming:** Orchestrator publishes CPU/RAM metrics to NATS every 5s → API gateway SSE endpoint subscribes → browser receives Server-Sent Events in real-time.

## VM Plans

| Plan | CPU | Memory | Disk | Credits/Hour |
|------|-----|--------|------|--------------|
| Small | 1 | 2 GB | 5 GB | 1 |
| Medium | 2 | 4 GB | 10 GB | 2 |
| Large | 4 | 8 GB | 20 GB | 4 |

## Prerequisites

- **Docker** and **Docker Compose** (for local infra)
- **kubectl** with access to a K8s cluster (k3s recommended)
- **Go 1.23+** (orchestrator)
- **Node.js 22+** and **pnpm** (frontend)
- **Python 3.12+** (API gateway — runs in Docker, no local install needed)

## Quick Start

### 1. Start infrastructure

```bash
docker compose up -d   # PostgreSQL, NATS, Keycloak
```

### 2. Build and import images

```bash
# Build all service images (run from repo root)
docker build -f services/api-gateway/Dockerfile -t hopper/api-gateway:latest .
docker build -f services/orchestrator/Dockerfile -t hopper/orchestrator:latest .
docker build -f frontend/Dockerfile -t hopper/frontend:latest frontend/
docker build -f images/hopper-vm/Dockerfile -t hopper/vm-ubuntu:22.04 images/hopper-vm/

# If using k3s, import into containerd
docker save hopper/api-gateway:latest hopper/orchestrator:latest \
  hopper/frontend:latest hopper/vm-ubuntu:22.04 | sudo k3s ctr images import -
```

### 3. Run database migrations

```bash
docker run --rm --network host \
  -e HOPPER_DATABASE_URL="postgresql+asyncpg://hopper:hopper_dev@localhost:5433/hopper" \
  -e PYTHONPATH=/app \
  hopper/api-gateway:latest alembic upgrade head
```

### 4. Deploy to Kubernetes

```bash
kubectl create namespace hopper

# Infrastructure (Postgres, NATS, Keycloak)
kubectl apply -f k8s/deploy/01-infra.yaml

# Applications (API Gateway, Orchestrator, Frontend)
kubectl apply -f k8s/deploy/02-apps.yaml

# Ingress rules
kubectl apply -f k8s/deploy/03-ingress.yaml

# Network policies (Cilium zero-trust)
kubectl apply -f k8s/deploy/04-network-policies.yaml
```

### 5. Configure Keycloak

```bash
# Create the hopper realm
kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  config credentials --server http://localhost:8080 --realm master --user admin --password admin

kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  create realms -s realm=hopper -s enabled=true

# Disable SSL requirement (for POC with self-signed certs)
kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  update realms/hopper -s sslRequired=NONE

# Create app roles
kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  create roles -r hopper -s name=admin
kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  create roles -r hopper -s name=professor
kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  create roles -r hopper -s name=student

# Create a test user
kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  create users -r hopper -s username=admin -s email=admin@hopper.dev \
  -s firstName=Admin -s lastName=User -s enabled=true
kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  set-password -r hopper --username admin --new-password admin123

# Assign admin role (get user ID first)
USER_ID=$(kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  get users -r hopper -q username=admin --fields id --format csv --noquotes | tail -1)
kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  add-roles -r hopper --uid "$USER_ID" --rolename admin

# Update client redirect URIs (replace CLIENT_ID with actual UUID)
CLIENT_ID=$(kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  get clients -r hopper -q clientId=hopper-api --fields id --format csv --noquotes | tail -1)
kubectl exec -n hopper deploy/keycloak -- /opt/keycloak/bin/kcadm.sh \
  update clients/$CLIENT_ID -r hopper \
  -s 'redirectUris=["https://YOUR_IP/*","http://YOUR_IP/*"]' \
  -s 'webOrigins=["https://YOUR_IP","http://YOUR_IP","*"]'
```

### 6. Allocate credits

```bash
# Get a token
TOKEN=$(curl -sk -X POST https://YOUR_IP/realms/hopper/protocol/openid-connect/token \
  -d "grant_type=password" -d "client_id=hopper-api" \
  -d "username=admin" -d "password=admin123" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Give admin 100 credits
curl -sk -X POST --cookie "session_token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"USER_UUID","amount":100}' \
  https://YOUR_IP/api/credits/allocate
```

### 7. Azure NSG (if on Azure)

Open these ports in the Network Security Group:

| Port | Purpose |
|------|---------|
| 80 | HTTP |
| 443 | HTTPS |
| 30000-32767 | K8s NodePorts — SSH into user VMs |

```bash
az network nsg rule create --resource-group <rg> --nsg-name <nsg> \
  --name allow-nodeports --priority 1100 --direction Inbound \
  --access Allow --protocol Tcp --destination-port-ranges 30000-32767
```

## Networking & Security

### Cilium Network Policies

The platform uses Cilium for zero-trust networking. Key policies in `k8s/deploy/04-network-policies.yaml`:

1. **default-deny-all** — Block all traffic by default
2. **allow-dns** — All pods can resolve DNS (port 53 to kube-system)
3. **allow-platform-internal** — Platform services (api-gateway, postgres, nats, keycloak, orchestrator, frontend) can talk to each other
4. **allow-ingress-to-services** — Nginx Ingress can reach frontend, api-gateway, keycloak
5. **user-vm-egress** — User VMs can reach internet but NOT other VMs or platform services (pod CIDR 10.42.0.0/16 and service CIDR 10.43.0.0/16 are blocked)
6. **user-vm-allow-orchestrator** — Orchestrator can manage user VMs
7. **orchestrator-allow-kube-api** — CiliumNetworkPolicy using `toEntities: kube-apiserver` (standard NetworkPolicy `ipBlock` does NOT work for ClusterIPs with Cilium — see [cilium/cilium#20550](https://github.com/cilium/cilium/issues/20550))
8. **platform-egress-internet** — Keycloak and API gateway can reach external endpoints (SAML federation, JWKS)

### NATS JetStream

NATS handles async communication between services:

| Subject | Publisher | Consumer | Purpose |
|---------|-----------|----------|---------|
| `pod.created` | Orchestrator | — | Pod lifecycle event |
| `pod.stopped` | Orchestrator | — | Pod terminated |
| `pod.failed` | Orchestrator | — | Pod creation failed |
| `billing.deducted` | Orchestrator | API Gateway | Deduct credits from user ledger |
| `billing.exhausted` | API Gateway | Orchestrator | Auto-terminate VM (no credits) |
| `metrics.<pod_id>` | Orchestrator | API Gateway (SSE) | Real-time CPU/RAM metrics |

### Keycloak OIDC

- Realm: `hopper`
- Client: `hopper-api` (public client, authorization code flow)
- Roles: `admin`, `professor`, `student`
- Browser login redirects to Keycloak → callback sets `session_token` cookie → JWT validated on each API request
- JWKS fetched server-to-server via internal K8s DNS (`http://keycloak:8080`)
- Browser-facing URLs go through ingress (`https://YOUR_IP/realms/hopper/...`)

## API Endpoints

### Auth
- `GET /auth/login` — Redirect to Keycloak OIDC
- `GET /auth/callback` — Exchange code for token, set cookie
- `GET /auth/me` — Current user profile
- `POST /auth/logout` — Clear session

### Pods (VMs)
- `GET /pods/plans` — List available VM plans
- `GET /pods/` — List user's VMs
- `POST /pods/` — Create a new VM `{"plan": "small"}`
- `GET /pods/{id}` — VM details
- `DELETE /pods/{id}` — Terminate VM
- `GET /pods/{id}/metrics` — SSE stream of CPU/RAM metrics

### Credits
- `GET /credits/balance` — Current balance
- `GET /credits/history` — Transaction history
- `POST /credits/allocate` — Add credits (admin/professor only)

### Admin
- `GET /admin/stats` — Dashboard stats (total users, active VMs)
- `GET /admin/users` — List all users
- `GET /admin/nodes` — K8s node info (CPU/memory capacity)

## Proto Definitions

gRPC contracts between API Gateway and Orchestrator:

- `proto/hopper/pod/v1/pod.proto` — PodOrchestrator service (CreatePod, TerminatePod, GetPodStatus, StreamMetrics, ListNodes)
- `proto/hopper/billing/v1/billing.proto` — BillingService (DeductCredits, GetBalance, StreamUsage)

Python stubs are generated at Docker build time. Go stubs are generated via `protoc` in the orchestrator Dockerfile.

## Database

### Migrations

Three Alembic migrations in `services/api-gateway/alembic/versions/`:

1. `001` — Initial schema: users, accounts, transfers, ledger_entries, pod_sessions
2. `002` — Fix pod_sessions columns, add updated_at
3. `003` — GPU → VM: rename gpu_tier→plan, add cpu/memory/ssh_port columns

### Credit Ledger

Double-entry accounting with immutable ledger entries. PostgreSQL advisory locks prevent race conditions on concurrent deductions. System account (`00000000-0000-0000-0000-000000000000`) is the counterparty for all transfers.

## SSH into VMs

Each VM gets a NodePort service (port 30000-32767). SSH credentials for the default image (`hopper/vm-ubuntu:22.04`):

```bash
ssh root@YOUR_IP -p <ssh_port>
# Password: hopper
```

The SSH port is returned in the API response when creating a VM and displayed in the frontend.

## Default Credentials (POC)

| Service | Username | Password |
|---------|----------|----------|
| Keycloak Admin Console | admin | admin |
| Hopper App | admin | admin123 |
| PostgreSQL | hopper | hopper_dev |
| VM SSH | root | hopper |
