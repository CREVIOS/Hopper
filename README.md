<div align="center">

# 🐇 Hopper

**A self-hosted cloud-VM platform for classrooms and labs.**

Spin up isolated Linux virtual machines in seconds — SSH in, code in a browser-based VS Code,
and pay by the minute from a credit balance. Built for universities that want their own compute
cloud on bare metal, without renting from the hyperscalers.

<br/>

![Backend](https://img.shields.io/badge/API-FastAPI%20·%20Python%203.12-3776AB)
![Orchestrator](https://img.shields.io/badge/Orchestrator-Go%20·%20gRPC-00ADD8)
![Frontend](https://img.shields.io/badge/Frontend-SvelteKit%20·%20TypeScript-FF3E00)
![Platform](https://img.shields.io/badge/Runtime-Kubernetes%20·%20k3s-326CE5)
![Auth](https://img.shields.io/badge/Auth-Keycloak%20OIDC-4D4D4D)

</div>

---

## What it does

Hopper turns a Kubernetes cluster into a multi-tenant VM cloud aimed at teaching environments:

- 🖥️ **Instant VMs** — pick a plan and a base image (Ubuntu, Python/ML, C/C++, Java), launch in seconds.
- 🔌 **Two ways in** — SSH with your own key, or a full **VS Code** workspace right in the browser.
- 💳 **Per-minute billing** — a double-entry credit ledger charges by the minute and stops the instant a VM stops.
- 🎓 **Classroom model** — admins fund teachers, teachers allocate credits to students, everyone sees live usage.
- ⚖️ **Fair-share scheduling** — an admission queue starts VMs in order as cluster capacity frees up.
- 📈 **Live telemetry** — real-time CPU/memory metrics and an in-browser terminal on every VM.
- 🔐 **Zero-trust networking** — per-VM network groups and Keycloak-backed OIDC single sign-on.

## Architecture

```
Browser ──► Nginx Ingress ──► Frontend (SvelteKit)
                           ──► API Gateway (FastAPI) ──► PostgreSQL (TimescaleDB)
                           ──► Keycloak (OIDC SSO)   ──► NATS (JetStream)
                                    │
                                    ▼ gRPC
                              Orchestrator (Go) ──► Kubernetes API
                                    │                    │
                                    ▼                    ▼
                              Billing Ticker        VM Pods + SSH / VS Code
                                    │
                                    ▼
                              NATS Events ──► API Gateway (credit deduction)
```

| Service | Stack | Port | Responsibility |
|---|---|---|---|
| **Frontend** | SvelteKit · Node | 3000 | Dashboard, VM management, credits, admin console |
| **API Gateway** | Python · FastAPI | 8000 | REST + SSE + WebSocket: auth, pods, credits, files, admin |
| **Orchestrator** | Go · gRPC | 50051 | K8s pod lifecycle, billing ticker, metrics publisher |
| **PostgreSQL** | TimescaleDB | 5432 | Users, pod sessions, double-entry credit ledger |
| **NATS** | JetStream | 4222 | Async events — billing deductions, metrics streaming |
| **Keycloak** | Java | 8080 | OIDC identity provider, university SSO |

### How the core flows work

- **Launch** — user picks a plan → the API checks the credit balance, records a `PodSession`, and calls the orchestrator over gRPC → the orchestrator creates a K8s pod with CPU/RAM limits plus a NodePort service for SSH → the billing ticker starts.
- **Billing** — the orchestrator ticks every 60 s per running VM and publishes `billing.deducted` to NATS → the API gateway deducts from the double-entry ledger → at zero balance it emits `billing.exhausted` and the VM is auto-terminated.
- **Metrics** — the orchestrator streams CPU/RAM to NATS every 5 s → the API gateway relays it over Server-Sent Events → the browser renders it live.

## VM plans

| Plan | vCPU | Memory | Disk | Credits / hour |
|---|---|---|---|---|
| Small | 1 | 2 GB | 5 GB | 1 |
| Medium | 2 | 4 GB | 10 GB | 2 |
| Large | 4 | 8 GB | 20 GB | 4 |

> A VM reserves a quarter of its plan's CPU and bursts to the full limit whenever cores are idle; memory and disk are reserved in full.

## Repository layout

```
├── frontend/          SvelteKit web app (TypeScript, Tailwind, shadcn-svelte)
├── services/
│   ├── api-gateway/   FastAPI REST API, auth, billing, SSE/WS proxies
│   └── orchestrator/  Go gRPC service — K8s pod lifecycle + billing ticker
├── images/hopper-vm/  Base VM image (Ubuntu + SSH + code-server)
├── proto/             Protobuf contracts shared by gateway and orchestrator
├── k8s/               Raw manifests (infra, apps, ingress, network policies)
├── charts/hopper/     Helm chart for cluster deployment
├── observability/     Metrics and logging stack
├── tests/             Unit, integration, E2E (Playwright), load, security
└── docs/              Architecture, design (SDD), tech stack, testing plans
```

## Prerequisites

- **Docker** + **Docker Compose** — local infrastructure
- **kubectl** with a cluster (k3s recommended) — to run VMs
- **Go 1.23+** — orchestrator
- **Node.js 22+** + **pnpm** — frontend
- **Python 3.12+** — API gateway (containerized; no host install required)

## Quick start (local)

**1. Start infrastructure** — PostgreSQL, NATS, Keycloak:

```bash
docker compose up -d
```

**2. Run database migrations:**

```bash
docker run --rm --network host \
  -e HOPPER_DATABASE_URL="postgresql+asyncpg://hopper:hopper_dev@localhost:5433/hopper" \
  -e PYTHONPATH=/app \
  hopper/api-gateway:latest alembic upgrade head
```

**3. Run the frontend:**

```bash
cd frontend
pnpm install
pnpm dev            # http://localhost:5173
```

> Local overrides live in gitignored `.env` files (`services/api-gateway/.env`, root `.env`).
> Machines with a host Postgres on 5433 set `POSTGRES_PORT=5434` so compose publishes elsewhere.

## Deploy to Kubernetes

```bash
kubectl create namespace hopper

kubectl apply -f k8s/deploy/01-infra.yaml            # Postgres, NATS, Keycloak
kubectl apply -f k8s/deploy/02-apps.yaml             # gateway, orchestrator, frontend
kubectl apply -f k8s/deploy/03-ingress.yaml          # ingress rules
kubectl apply -f k8s/deploy/04-network-policies.yaml # zero-trust networking
```

A Helm chart (`charts/hopper/`) is provided for parameterized, environment-specific deploys
(`values-dev.yaml`, `values-staging.yaml`, `values-prod.yaml`).

## Testing

```bash
# Frontend type-check + lint
cd frontend && pnpm check && pnpm lint

# API gateway unit + integration
cd services/api-gateway && poetry run pytest

# Orchestrator
cd services/orchestrator && go test ./...

# End-to-end (Playwright)
cd tests/e2e && pnpm test
```

Deeper references live in [`docs/`](docs/): [architecture](docs/ARCHITECTURE.md),
[software design](docs/SDD.md), [tech stack](docs/TECH_STACK.md),
[VM admission queue](docs/VM_QUEUEING.md), and the [testing plan](docs/TESTING_PLAN.md).

---

<div align="center">
Self-hosted on Kubernetes · Secured by Keycloak · Billed by the minute
</div>
