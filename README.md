# Hopper

A self-hosted GPU cloud platform for universities, providing Modal-like fluidity with bare-metal control and enterprise-grade security.

## Quick Start

```bash
# Setup dev environment (requires Docker, pnpm, Poetry, Go)
./scripts/dev-setup.sh

# Or manually:
docker compose up -d                    # Postgres, NATS, Keycloak
cd frontend && pnpm install && pnpm dev # SvelteKit on :5173
cd services/api-gateway && poetry install && poetry run uvicorn app.main:app --reload  # FastAPI on :8000
cd services/orchestrator && go run ./cmd/orchestrator/  # gRPC on :50051
```

## Architecture

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | SvelteKit 2 + Svelte 5 | Dashboard, pod management, metrics |
| API Gateway | FastAPI (Python) | REST API, SSE metrics, auth |
| Orchestrator | Go + client-go | Pod lifecycle, K8s operations, billing |
| Event Bus | NATS JetStream | Async events between services |
| Database | PostgreSQL 16 + TimescaleDB | Credit ledger, sessions, GPU metrics |
| Auth | Keycloak | SAML/OIDC SSO with university IdPs |

## Project Structure

```
frontend/           SvelteKit dashboard
services/
  api-gateway/      FastAPI REST API
  orchestrator/     Go gRPC service
proto/              Protobuf definitions
k8s/                Kubernetes manifests
infrastructure/     Pulumi, Ansible, ArgoCD
observability/      Prometheus, Grafana, Loki
tests/              Unit, integration, E2E, load, chaos
```

See `docs/` for detailed architecture, tech stack, and testing documentation.
