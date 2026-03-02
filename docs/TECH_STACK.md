# Hopper - Technology Stack

> Every technology choice is justified with research, version pinned, and includes best practices.

---

## Stack Overview

| Layer | Technology | Version | License |
|-------|-----------|---------|---------|
| **Frontend** | SvelteKit (Svelte 5) | 2.x | MIT |
| **API Gateway** | FastAPI (Python) | 0.115+ | MIT |
| **Orchestration Service** | Go + client-go | Go 1.23+ | BSD-3 |
| **Internal RPC** | gRPC + Protobuf | gRPC 1.65+ | Apache 2.0 |
| **Event Bus** | NATS JetStream | 2.10+ | Apache 2.0 |
| **Database** | PostgreSQL + TimescaleDB | PG 16 + TS 2.17+ | PostgreSQL + Apache 2.0 |
| **Auth/IAM** | Keycloak | 25.0+ | Apache 2.0 |
| **SSH Gateway** | Teleport | 15+ | Apache 2.0 (CE) |
| **Kubernetes** | kubeadm / RKE2 | 1.30+ | Apache 2.0 |
| **GPU Management** | NVIDIA GPU Operator | 25.3.1+ | Apache 2.0 |
| **GPU Scheduling** | KAI Scheduler (ex-Run:ai) | Latest | Apache 2.0 |
| **Job Admission** | Kueue | 0.9+ | Apache 2.0 |
| **Container Runtime** | gVisor (runsc) | Latest | Apache 2.0 |
| **Network Policy** | Calico | 3.28+ | Apache 2.0 |
| **GitOps** | ArgoCD | 2.13+ | Apache 2.0 |
| **IaC (Provisioning)** | Pulumi (Python SDK) | 3.140+ | Apache 2.0 |
| **IaC (Configuration)** | Ansible | 2.16+ | GPL-3.0 |
| **Monitoring** | Prometheus + Grafana | Prom 2.54+ / Grafana 11+ | Apache 2.0 |
| **GPU Metrics** | NVIDIA DCGM Exporter | 4.5.2+ (DCGM 4.8.1+) | Apache 2.0 |
| **Logging** | Grafana Loki + Promtail | 3.3+ | AGPL-3.0 |
| **Chaos Testing** | Chaos Mesh | 2.7+ | Apache 2.0 |
| **Load Testing** | Grafana k6 | 0.55+ | AGPL-3.0 |
| **E2E Testing** | Playwright | 1.50+ | Apache 2.0 |

---

## Frontend: SvelteKit 2

### Why SvelteKit over Next.js

| Metric | SvelteKit 2 | Next.js 15 |
|--------|-------------|------------|
| Server RPS | ~1,200 | ~850 |
| JS bundle size | 50%+ smaller | Larger (React runtime) |
| WebSocket support | Native (March 2025) | Route Handlers only |
| Dashboard suitability | Excellent (minimal JS, fast interactivity) | Good |
| Learning curve | Low | Moderate |

SvelteKit compiles to vanilla JS with no runtime overhead, which is critical for real-time metric updates on the dashboard. Native WebSocket support (added March 2025) enables direct web terminal integration.

### Best Practices

- **SSE for metrics**: Use Server-Sent Events for unidirectional GPU metrics streaming (auto-reconnection, standard HTTP)
- **WebSocket for terminals**: Use xterm.js + WebSocket for bidirectional shell access
- **Component library**: Use shadcn-svelte for consistent UI primitives
- **State management**: Svelte stores for global state (credit balance, active sessions)
- **Data fetching**: SvelteKit load functions for server-side data, SSE for real-time updates
- **Bundle analysis**: Use `@sveltejs/adapter-node` for self-hosted deployment

### Key Libraries

```json
{
  "dependencies": {
    "@sveltejs/kit": "^2.0.0",
    "svelte": "^5.0.0",
    "@xterm/xterm": "^5.5.0",
    "@xterm/addon-fit": "^0.10.0",
    "@xterm/addon-web-links": "^0.11.0",
    "chart.js": "^4.4.0",
    "bits-ui": "latest",
    "tailwindcss": "^4.0.0"
  }
}
```

---

## API Gateway: FastAPI

### Why FastAPI

- **Auto-generated OpenAPI docs**: Students and TAs can explore the API via Swagger UI
- **Python ecosystem**: Direct integration with ML tooling if needed
- **Async-native**: `asyncio` handles concurrent SSE connections efficiently
- **Pydantic v2**: 5-50x faster validation than v1

### Best Practices

- **Multi-worker deployment**: Use Uvicorn with `--workers 4` (or Gunicorn with Uvicorn workers)
- **Structured logging**: Use `structlog` with JSON output for Loki ingestion
- **Request validation**: Pydantic v2 models for all request/response schemas
- **Rate limiting**: Use `slowapi` with per-user rate limits
- **Health checks**: `/healthz` (liveness) and `/readyz` (readiness) endpoints
- **Middleware**: CORS, request ID injection, timing middleware
- **Error handling**: Consistent error response format with error codes

### Key Dependencies

```toml
[project]
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.9.0",
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.30.0",
    "nats-py>=2.9.0",
    "grpcio>=1.65.0",
    "structlog>=24.0.0",
    "slowapi>=0.1.9",
    "python-jose[cryptography]>=3.3.0",
    "httpx>=0.27.0",
]
```

---

## Orchestration Service: Go

### Why Go for Orchestration

- **`client-go` is the official Kubernetes SDK** - written in Go, best-maintained, zero translation overhead
- **Goroutines**: Handle thousands of concurrent pod watch streams
- **No GC pauses at typical load**: Orchestration service handles hundreds, not millions, of requests
- **Single binary deployment**: No runtime dependencies

### Best Practices

- **Kubernetes informers**: Use shared informers (not individual watches) for pod state tracking
- **Controller pattern**: Implement a reconciliation loop for pod lifecycle management
- **Context propagation**: Use `context.Context` for all K8s API calls (timeouts, cancellation)
- **Error handling**: Wrap K8s API errors with context (`fmt.Errorf("creating pod %s: %w", name, err)`)
- **Graceful shutdown**: Handle SIGTERM with informer cache draining
- **Metrics**: Expose Prometheus metrics on `/metrics` (pod creation latency, queue depth, error rates)

### Key Dependencies

```go
module github.com/hopper/orchestrator

go 1.23

require (
    k8s.io/client-go v0.31.0
    k8s.io/apimachinery v0.31.0
    google.golang.org/grpc v1.65.0
    google.golang.org/protobuf v1.34.0
    github.com/nats-io/nats.go v1.37.0
    github.com/prometheus/client_golang v1.20.0
    go.uber.org/zap v1.27.0
)
```

---

## Internal Communication: gRPC

### Why gRPC for Service-to-Service

- **Protobuf**: ~10x smaller than JSON, ~7x faster deserialization
- **Server streaming**: Native support for metrics and pod status streams
- **Enforced contracts**: `.proto` files define the API contract between services
- **Code generation**: Automatic client/server stubs in Python (FastAPI) and Go (orchestrator)

### Communication Map

```
External (user-facing):    REST/JSON via FastAPI (OpenAPI documented)
Internal (service-to-service):
  FastAPI API GW ←→ Go Orchestrator:     gRPC
  Go Orchestrator ←→ Billing Service:    gRPC
  Go Orchestrator → NATS JetStream:      NATS protocol
  NATS → FastAPI (SSE endpoints):        NATS subscription → SSE push
  Prometheus → DCGM Exporter:            HTTP /metrics scrape
  Prometheus → TimescaleDB:              remote_write
```

### Key Proto Definitions

```protobuf
service PodOrchestrator {
  rpc CreatePod(CreatePodRequest) returns (PodStatus);
  rpc TerminatePod(PodId) returns (TerminateResponse);
  rpc StreamMetrics(PodId) returns (stream GpuMetrics);
  rpc WatchPodStatus(PodId) returns (stream PodStatus);
}

service BillingService {
  rpc DeductCredits(DeductRequest) returns (DeductResponse);
  rpc GetBalance(AccountId) returns (BalanceResponse);
  rpc StreamUsage(AccountId) returns (stream UsageEvent);
}
```

---

## Event Bus: NATS JetStream

### Why NATS over Kafka/Redis Streams

| Criteria | NATS JetStream | Kafka | Redis Streams |
|----------|---------------|-------|---------------|
| Footprint | ~20MB | 500MB+ | Varies |
| Latency | Microseconds | Tens of ms | Sub-ms |
| Ops complexity | Single binary | ZooKeeper/KRaft | Low |
| Persistence | JetStream | Log-based | In-memory + disk |

At university scale (tens to hundreds of GPUs), NATS is the optimal choice. Kafka is designed for millions of events/second across hundreds of brokers.

### Best Practices

- **JetStream streams**: Create durable streams for billing events (must not lose)
- **Work queues**: Use queue groups for load-balanced consumers
- **Dead letter queues**: Route failed messages for manual inspection
- **Retention**: Time-based for metrics (24h), limits-based for billing (until consumed)
- **Monitoring**: NATS Server exporter for Prometheus

---

## Database: PostgreSQL 16 + TimescaleDB

### Why Single Database

Running credit ledger, session state, and GPU metrics in one PostgreSQL instance:
- **Transactional consistency**: Credit deduction and session creation in one transaction
- **JOINs across domains**: Query "show GPU utilization for sessions that cost > 50 credits"
- **Operational simplicity**: One backup strategy, one failover, one monitoring target

### Best Practices

**Credit Ledger:**
- **Append-only**: Use PostgreSQL RULEs to prevent UPDATE/DELETE on ledger tables
- **Advisory locks**: Use `pg_advisory_xact_lock()` for credit deduction (prevents TOCTOU races)
- **Double-entry**: Every transfer creates exactly two entries (debit + credit)
- **Compensating entries**: Never modify existing entries; create reversal entries for corrections
- **Prefixed ULIDs**: Sortable, unique IDs with type prefix (`txfr_`, `entr_`, `acct_`)

**TimescaleDB:**
- **Hypertables**: 1-hour chunks for GPU metrics
- **Compression**: Enable after 1 day (95%+ compression ratio)
- **Retention**: 30 days raw, 1 year aggregated
- **Continuous aggregates**: Pre-compute hourly and daily rollups

**General:**
- **Connection pooling**: Use PgBouncer in transaction mode
- **Migrations**: Use Alembic (Python) with numbered migration files
- **Backups**: pg_dump daily + WAL archiving for point-in-time recovery
- **Monitoring**: pg_stat_statements for query performance

---

## Auth: Keycloak

### Why Keycloak over Supabase Auth / Auth0

| Feature | Keycloak | Supabase Auth | Auth0 |
|---------|----------|---------------|-------|
| Cost | Free (open source) | $25/mo+ | Free 25k MAU, then $$$ |
| SAML/Shibboleth | Native brokering | Via integration | Enterprise only |
| LDAP federation | Built-in | No | Enterprise only |
| Multi-university | Realms | Projects | Tenants |
| Self-hosted | Primary model | With Supabase | Cloud only |

### Best Practices

- **Realm per university**: Isolated configuration, user pools, and IdP connections
- **Identity brokering**: Configure each university's Shibboleth IdP as an external identity provider
- **Attribute mapping**: Map `eduPersonAffiliation` to Keycloak roles:
  - `student` → `user:student`
  - `faculty` → `course:professor`
  - `staff` → `department:admin`
- **Token configuration**: Short-lived access tokens (5 min), longer refresh tokens (1 hour)
- **Client scopes**: Define scopes for GPU operations (`gpu:create`, `gpu:terminate`, `billing:read`)

---

## SSH Gateway: Teleport

### Why Teleport over HashiCorp Boundary

| Feature | Teleport | Boundary |
|---------|----------|----------|
| K8s RBAC integration | Native | TCP forwarding only |
| Session recording | Built-in | No |
| SSH replacement | Yes (replaces sshd) | No |
| Audit logging | Full command trail | Basic |
| Web terminal | Built-in proxy | No |

### Best Practices

- **Ephemeral certificates**: Short-lived SSH certs per session (no static SSH keys)
- **Role mapping**: Keycloak roles → Teleport roles → K8s RBAC
- **Session recording**: Enable for academic integrity compliance
- **MFA**: Require for admin access, optional for student access
- **Node labels**: Label GPU pods with `gpu_type`, `session_id`, `course_id` for access control

---

## Kubernetes Components

### GPU Operator (v25.3.1+)

**CRITICAL: Must patch CVE-2025-23266.** This is a CVSS 9.0 container escape via NVIDIA Container Toolkit.

```bash
helm install gpu-operator nvidia/gpu-operator \
  --set driver.version="550.127.08" \
  --set toolkit.version="1.17.8" \
  --set dcgmExporter.enabled=true \
  --set migManager.enabled=true \
  --set driver.enabled=true
```

### KAI Scheduler (ex-Run:ai, Open Source)

Open-sourced April 2025 under Apache 2.0. The single most important tool for university GPU platforms.

Best practices:
- **Hierarchical queues**: University → Department → Course → Student
- **Fractional GPU**: Allocate 0.25-1.0 GPU per student based on workload
- **Fairshare decay**: 7-day half-life (matches Slurm's proven approach)
- **Scavenger queue**: Zero-credit students can run on idle GPUs (preemptible)

### Kueue (Job Admission)

Best practices:
- **ClusterQueues per GPU tier**: Premium (MIG), Standard (consumer), Budget (small)
- **ResourceFlavors**: Distinguish `nvidia.com/mig-2g.24gb` from `nvidia.com/gpu`
- **Admission checks**: Integrate credit balance check as a custom admission webhook

### gVisor (Container Runtime)

Best practices:
- **Platform**: Use KVM platform for best performance (avoid ptrace platform)
- **Compatibility**: Test all student container images against gVisor syscall support
- **Fallback**: If specific workloads need direct hardware access, create a separate node pool with standard runc

### Calico (Network)

Best practices:
- **GlobalNetworkPolicy**: Platform-wide defaults that namespace-level policies cannot override
- **Tiered policies**: Platform tier (highest priority) → Department tier → Course tier
- **Deny logging**: Log all denied connections for security auditing
- **DNS policy**: Allow only kube-dns, deny external DNS to prevent data exfiltration

---

## DevOps & GitOps

### Pulumi (Infrastructure Provisioning)

Best practices:
- **Python SDK**: Matches team expertise, type-safe with IDE support
- **State**: Use Pulumi Cloud free tier or self-hosted S3 backend
- **Stacks**: `dev`, `staging`, `production` stacks with shared configuration
- **Secrets**: Use Pulumi's built-in secret encryption for sensitive values

### Ansible (Configuration Management)

Best practices:
- **Role structure**: `gpu-node`, `k8s-master`, `k8s-worker`, `monitoring`
- **Idempotency**: All tasks must be safely re-runnable
- **Tags**: `nvidia`, `kubernetes`, `security` for selective execution
- **Vault**: Use Ansible Vault for secrets (driver download tokens, etc.)

### ArgoCD (GitOps)

Best practices:
- **App of Apps pattern**: Single root Application that deploys all other Applications
- **Sync waves**: Deploy infrastructure (NATS, PostgreSQL) before application services
- **Auto-sync**: Enable for dev/staging, manual sync for production
- **SSO integration**: Connect ArgoCD to Keycloak for consistent auth

---

## Observability

### Monitoring Stack

```
NVIDIA GPU → DCGM Exporter (DaemonSet, :9400)
  → Prometheus (scrape, 15-day retention, alerting rules)
    → Grafana (dashboards: NVIDIA DCGM #12239, custom Hopper dashboards)
    → AlertManager (PagerDuty/Slack/email for critical alerts)
    → TimescaleDB (remote_write for 1-year historical data)
```

### Logging Stack

```
Student Pod stdout/stderr → Promtail (auto-labels: namespace, user_id, session_id)
  → Grafana Loki (30-day retention, label-indexed)
  → Grafana (unified view: logs + metrics correlated by pod_id)
```

### Key Alerts

| Alert | Condition | Severity |
|-------|-----------|----------|
| GPU Temperature Critical | > 90C for 5 min | Critical |
| GPU OOM | memory_used > 95% memory_total | Warning |
| Pod Stuck Pending | Pending > 10 min | Warning |
| Credit Balance Zero | balance = 0 with running pods | Critical |
| Node Unreachable | kube_node_status_condition{condition="Ready"} = 0 | Critical |
| DCGM Exporter Down | up{job="dcgm-exporter"} = 0 | Critical |
| NATS JetStream Lag | consumer_pending > 1000 | Warning |

---

## Version Pinning Policy

- **NVIDIA drivers**: Pin to specific version (e.g., `550.127.08`), update quarterly after testing
- **Kubernetes**: Stay on latest stable minor (e.g., 1.31.x), skip no more than 1 minor version
- **Application dependencies**: Use lock files (Poetry for Python, go.sum for Go, pnpm-lock.yaml for SvelteKit)
- **Container images**: Always use digest-pinned images in production (not `:latest`)
- **Helm charts**: Pin chart versions in ArgoCD Application specs
