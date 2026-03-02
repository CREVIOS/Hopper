# Hopper - System Architecture

> A self-hosted GPU cloud platform for universities, providing Modal-like fluidity with bare-metal control and enterprise-grade security.

---

## Design Philosophy

Hopper is designed around three principles:

1. **Security-first multi-tenancy** - Students run untrusted code on shared GPUs. Every layer must enforce isolation.
2. **Academic-native** - Integrates with university SSO (Shibboleth/SAML), fairshare scheduling, and per-course resource allocation.
3. **Operational simplicity** - University IT teams are small. Every component must justify its operational cost.

---

## High-Level Architecture

```
                         ┌─────────────────────────────────┐
                         │         STUDENT / RESEARCHER      │
                         │   Browser  |  SSH (tsh)  |  IDE   │
                         └──────────────┬──────────────────┘
                                        │
                         ┌──────────────▼──────────────────┐
                         │       ACCESS LAYER               │
                         │  Teleport (SSH + Web + K8s)      │
                         │  + Keycloak (SAML/OIDC SSO)      │
                         └──────────────┬──────────────────┘
                                        │
              ┌─────────────────────────▼──────────────────────────┐
              │                  APPLICATION LAYER                   │
              │                                                      │
              │  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
              │  │  SvelteKit   │  │   FastAPI     │  │    Go      │ │
              │  │  Dashboard   │  │   API GW      │  │ Orchestr.  │ │
              │  │  (Frontend)  │  │  (REST/SSE)   │  │  (gRPC)    │ │
              │  └──────┬───────┘  └──────┬────────┘  └─────┬─────┘ │
              │         │                 │                  │        │
              │         │          ┌──────▼────────┐        │        │
              │         │          │  NATS JetStream│◄───────┘        │
              │         │          │  (Event Bus)   │                 │
              │         │          └──────┬─────────┘                 │
              │         │                 │                           │
              │  ┌──────▼─────────────────▼───────────────────────┐  │
              │  │      PostgreSQL 16 + TimescaleDB               │  │
              │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐  │  │
              │  │  │  Ledger    │ │  Sessions  │ │ GPU Metrics │  │  │
              │  │  │ (Credits)  │ │  (Pods)    │ │ (Timeseries)│  │  │
              │  │  └────────────┘ └────────────┘ └────────────┘  │  │
              │  └────────────────────────────────────────────────┘  │
              └──────────────────────┬──────────────────────────────┘
                                     │
              ┌──────────────────────▼──────────────────────────────┐
              │               PLATFORM LAYER                         │
              │                                                      │
              │  ┌──────────────────────────────────────────────────┐│
              │  │           Kubernetes (kubeadm / RKE2)            ││
              │  │                                                  ││
              │  │  ┌────────────┐  ┌────────────┐ ┌─────────────┐ ││
              │  │  │ KAI Sched. │  │   Kueue    │ │ GPU Operator│ ││
              │  │  │ (Fractional│  │  (Quota +  │ │ (Driver +   │ ││
              │  │  │  GPU)      │  │  Fairshare)│ │  Toolkit)   │ ││
              │  │  └────────────┘  └────────────┘ └─────────────┘ ││
              │  │                                                  ││
              │  │  ┌────────────┐  ┌────────────┐ ┌─────────────┐ ││
              │  │  │  Calico    │  │   gVisor   │ │   ArgoCD    │ ││
              │  │  │ (Network)  │  │  (Runtime) │ │  (GitOps)   │ ││
              │  │  └────────────┘  └────────────┘ └─────────────┘ ││
              │  └──────────────────────────────────────────────────┘│
              └──────────────────────┬──────────────────────────────┘
                                     │
              ┌──────────────────────▼──────────────────────────────┐
              │              GPU HARDWARE LAYER                      │
              │                                                      │
              │  ┌─────────────────────────────────────────────────┐ │
              │  │  Node Pool A: RTX PRO 6000 Blackwell (96GB)    │ │
              │  │  → MIG: 4x 24GB hardware-isolated instances    │ │
              │  └─────────────────────────────────────────────────┘ │
              │  ┌─────────────────────────────────────────────────┐ │
              │  │  Node Pool B: RTX 5090/4090/3090               │ │
              │  │  → Time-Slicing (4x) + MPS for inference       │ │
              │  └─────────────────────────────────────────────────┘ │
              │  ┌─────────────────────────────────────────────────┐ │
              │  │  Node Pool C: RTX 4070/3060 (Budget Tier)      │ │
              │  │  → Time-Slicing (2x)                           │ │
              │  └─────────────────────────────────────────────────┘ │
              │                                                      │
              │  ┌─────────────────────────────────────────────────┐ │
              │  │  MONITORING: Prometheus + DCGM Exporter         │ │
              │  │  + Grafana + Loki + AlertManager                │ │
              │  └─────────────────────────────────────────────────┘ │
              └────────────────────────────────────────────────────┘
```

---

## Component Architecture

### 1. Access Layer

#### Teleport (SSH Gateway + Web Access)

Teleport replaces traditional SSH bastion hosts with identity-aware access:

- **SSH access**: Students use `tsh ssh` or standard `ssh` through Teleport proxy
- **Web terminal**: xterm.js embedded in the dashboard, connecting through Teleport's web proxy
- **Session recording**: Full command audit trails for academic integrity
- **Kubernetes RBAC integration**: Teleport maps Keycloak roles to K8s RBAC
- **Certificate rotation**: Ephemeral SSH certificates per session (no static keys)

**Connection flow:**
```
Student → tsh login (gets short-lived cert)
       → tsh ssh root@pod-{session_id}
       → Teleport Proxy (authenticates, logs)
       → Kubernetes Service → Student Pod :22
```

#### Keycloak (Identity & Access Management)

Keycloak handles all authentication, integrating natively with university identity systems:

- **SAML identity brokering**: Direct integration with university Shibboleth IdPs
- **OIDC support**: For universities with modern IdPs (Azure AD, Okta)
- **Realms**: Each university gets its own realm for isolated configuration
- **Attribute mapping**: `eduPersonAffiliation` → platform roles automatically
- **RBAC enforcement**: Fine-grained role hierarchy (Platform Admin → University Admin → Department Admin → Professor → TA → Student)

**Auth flow:**
```
Student → Hopper Login → Keycloak → WAYF (Where Are You From?)
  → University Shibboleth IdP → SAML Assertion → Keycloak
  → Map attributes (email, affiliation, department)
  → Issue JWT → Hopper Application
```

---

### 2. Application Layer

#### SvelteKit Dashboard (Frontend)

The student-facing web interface, chosen for performance and real-time capabilities:

- **Pod management**: One-click GPU pod deployment with GPU tier selector
- **Real-time metrics**: SSE-based GPU utilization, VRAM, temperature streaming
- **Web terminal**: xterm.js for in-browser SSH access (WebSocket)
- **Credit dashboard**: Real-time balance, usage history, spending projections
- **Pod template library**: Pre-configured environments (PyTorch, TensorFlow, JAX, RAPIDS)

**Real-time data transport:**
```
SSE (Server-Sent Events):  Metrics, notifications, pod status updates
WebSocket:                  Web terminal, JupyterLab proxy
```

SSE is preferred for metrics because:
- GPU metrics are unidirectional (server → client)
- Automatic reconnection built into the protocol
- Works with standard HTTP infrastructure (no special proxy config)
- 3ms latency difference from WebSocket is imperceptible at 2-5s refresh intervals

#### FastAPI API Gateway

The external-facing REST API, chosen for Python ecosystem and auto-generated OpenAPI docs:

- **User management**: Profile, sessions, credit balance
- **Pod lifecycle API**: Create, monitor, terminate GPU pods
- **SSE endpoints**: Real-time metrics streaming
- **Rate limiting**: Per-student API rate limits
- **Admission control**: Credit balance check before pod creation

#### Go Orchestration Service

The internal service handling Kubernetes operations, chosen because `client-go` is the native K8s SDK:

- **Pod lifecycle management**: State machine (REQUESTED → PROVISIONING → RUNNING → TERMINATED)
- **Kubernetes Watch API**: Real-time pod state monitoring via informers
- **Billing ticker**: Per-minute credit deduction for running pods
- **Finalizers**: Ensure billing settlement before pod deletion
- **gRPC interface**: Communicates with FastAPI gateway and billing service

**Pod lifecycle state machine:**
```
REQUESTED → PROVISIONING → PULLING → STARTING → RUNNING → STOPPING → TERMINATED
               |                        |           |
               v                        v           v
            FAILED                   FAILED      FAILED
```

#### NATS JetStream (Event Bus)

Lightweight message broker for decoupled event processing:

- **Single binary, ~20MB footprint** - minimal ops burden
- **Microsecond-level latency** for GPU event processing
- **JetStream persistence** for reliable event delivery
- **Kubernetes-native** deployment via Helm

**Event topics:**
```
gpu.pod.created          Pod provisioning started
gpu.pod.running          Pod is ready for SSH
gpu.pod.terminated       Pod shutdown completed
gpu.pod.failed           Pod failure detected
gpu.metrics.{node_id}    Real-time GPU metrics stream
billing.credit.deducted  Credit usage event
billing.credit.added     Credit allocation event
billing.alert.low        Low balance warning (< 10%)
session.started          Session tracking
session.ended            Session cleanup trigger
```

---

### 3. Data Layer

#### PostgreSQL 16 + TimescaleDB

A single PostgreSQL instance serves three purposes:

**a) Credit Ledger (Double-Entry Bookkeeping)**

All financial operations use append-only, immutable double-entry accounting:

```sql
-- Transfers record business events
transfers (id, type, metadata, event_at, created_at)

-- Ledger entries are immutable debit/credit pairs
ledger_entries (id, transfer_id, account_id, direction, amount,
               previous_balance, current_balance, event_at, created_at)

-- Race condition prevention: PostgreSQL advisory locks
-- per account during deduction (not SELECT FOR UPDATE)
```

Key design principles:
- Entries record `previous_balance` and `current_balance` for point-in-time queries
- Mistakes corrected with compensating entries, never mutations
- Advisory locks prevent TOCTOU race conditions on concurrent deductions

**b) Session & Pod State**

```sql
sessions (id, user_id, gpu_type, namespace, pod_name,
          started_at, expires_at, status, credits_charged)
```

**c) GPU Metrics (TimescaleDB Hypertables)**

TimescaleDB extends PostgreSQL for time-series data in the same database:

```sql
gpu_metrics (time, node_id, gpu_index, gpu_model, pod_id, user_id,
             gpu_utilization, memory_used, memory_total, temperature,
             power_usage, sm_clock, mem_clock, pcie_errors)

-- Hypertable with 1-hour chunks, 95%+ compression, 30-day raw retention
-- Continuous aggregates for hourly/daily rollups (1-year retention)
```

---

### 4. Platform Layer

#### Kubernetes (kubeadm or RKE2)

Full Kubernetes, not K3s. K3s is limited to ~50-100 nodes and excludes advanced networking plugins. For 50-500 students with 10-50+ GPU nodes, full K8s is appropriate.

**Why not K3s**: Missing horizontal pod autoscaler, limited cluster autoscaler, constrained networking plugin support.

**Why not Nomad**: GPU ecosystem is far smaller than Kubernetes (no GPU Operator equivalent, no KAI Scheduler, no Kueue).

#### NVIDIA GPU Operator (v25.3.1+)

Manages the full GPU software stack on Kubernetes:
- Driver installation and lifecycle
- Container toolkit configuration
- Device plugin for GPU scheduling
- DCGM exporter for metrics
- MIG manager for supported hardware
- Time-slicing configuration

**CRITICAL**: Must be v25.3.1+ to patch CVE-2025-23266 (NVIDIAScape container escape vulnerability).

#### KAI Scheduler (Open-Source, from Run:ai)

The most important new tool for university GPU platforms (open-sourced April 2025, Apache 2.0):
- **Fractional GPU allocation**: Allocate 0.25 GPU, 0.5 GPU, etc.
- **Gang scheduling**: All-or-nothing pod group scheduling for distributed training
- **Hierarchical queuing**: Per-department and per-course quotas with fairshare
- **Time-based fairshare**: Recent heavy users get lower priority (7-day half-life, like Slurm)

#### Kueue (Job Admission Control)

Works WITH the default K8s scheduler (doesn't replace it):
- **ClusterQueues**: Define GPU resource pools with ResourceGroups
- **Flavors**: Distinguish GPU tiers (MIG slices vs time-sliced consumer GPUs)
- **Admission control**: Jobs queue until resources are available
- **Per-course quotas**: Each course gets a ResourceQuota within a ClusterQueue

#### Container Runtime: gVisor

gVisor intercepts syscalls in userspace for security isolation:

- **Modal.com uses gVisor in production** for 20,000+ GPU workloads
- Lower overhead than Kata Containers (no VM boot time)
- Does NOT provide hardware-level isolation (shares host kernel)
- Sufficient for student workloads where container images are curated

**When to use Kata Containers instead**: External collaborators running fully untrusted code. Kata provides hardware VM isolation but is limited to single GPU passthrough (no fractional sharing).

#### Calico (Network Isolation)

Calico over Cilium for one key reason: **GlobalNetworkPolicy guardrails**.

GlobalNetworkPolicy lets platform admins set baseline security that namespace-level policies (which TAs might manage) cannot weaken. This is ideal for a university setting.

```
Default policy: Deny all inter-namespace traffic
Allow: DNS resolution (kube-dns)
Allow: Internet egress on ports 80/443 (for pip install, dataset downloads)
Allow: SSH gateway → student pod on port 22
Deny:  Student pod → student pod (cross-namespace)
Deny:  Student pod → control plane
```

---

### 5. GPU Hardware Strategy

#### GPU Partitioning by Hardware Type

| GPU | MIG | Time-Slicing | MPS | vGPU | Recommendation |
|-----|-----|-------------|-----|------|----------------|
| RTX PRO 6000 Blackwell (96GB) | 4x 24GB | Yes | Yes | Coming | MIG for isolation |
| RTX 6000 Ada (48GB) | No | Yes | Yes | Yes (Server Ed.) | Time-slice (4x) |
| RTX 5090 (32GB) | No | Yes | Yes | No | Time-slice (4x) |
| RTX 4090 (24GB) | No | Yes | Yes | No | Time-slice (4x) |
| RTX 3090 (24GB) | No | Yes | Yes | No | Time-slice (4x) |
| RTX 4070 (12GB) | No | Yes | Yes | No | Time-slice (2x) |

#### GPU Tiers

| Tier | GPUs | Use Case | Credits/Hr |
|------|------|----------|------------|
| Premium | RTX PRO 6000 Blackwell MIG (24GB slices) | Large model training, multi-GPU | 15 |
| Standard | RTX 5090/4090 time-sliced | Most coursework, medium training | 10 |
| Budget | RTX 4070/3060 time-sliced | Small experiments, debugging | 5 |
| Scavenger | Any idle GPU (preemptible) | Free tier, evicted when needed | 0 |

#### Memory Isolation Warning

**Time-slicing provides NO memory isolation.** Students on shared consumer GPUs can:
- OOM each other's workloads
- Potentially read residual GPU memory (LeftoverLocals vulnerability)

Mitigations:
1. MIG on RTX PRO 6000 Blackwell (hardware isolation)
2. `CUDA_DEVICE_MEMORY_CLEANUP=1` environment variable on all pods
3. VRAM monitoring sidecar that kills pods exceeding allocation
4. Curated container images (students cannot build arbitrary Dockerfiles)

---

### 6. Observability Stack

```
NVIDIA GPU → DCGM → dcgm-exporter (DaemonSet, port 9400)
  → Prometheus (scrape /metrics, 15-day retention)
    → Grafana (Dashboard ID: 12239 + custom dashboards)
    → AlertManager (GPU temp > 85C, stuck utilization, OOM events)
    → TimescaleDB (remote_write for long-term storage, 1-year retention)

Student Pod Logs → Promtail (label: namespace, user_id, session_id, course_id)
  → Grafana Loki (30-day retention)
  → Grafana (unified log + metrics view)
```

---

## Security Architecture

### Defense-in-Depth Layers

| Layer | Control | Implementation |
|-------|---------|---------------|
| Identity | SSO + MFA | Keycloak with university Shibboleth IdP |
| Access | Zero-trust SSH | Teleport with ephemeral certificates |
| Network | Micro-segmentation | Calico GlobalNetworkPolicy (default deny) |
| Runtime | Syscall filtering | gVisor container runtime |
| GPU | Memory isolation | MIG (Blackwell), CUDA cleanup (consumer) |
| Images | Supply chain | Curated registry, no student-built images |
| NVIDIA Stack | CVE patching | Container Toolkit v1.17.8+, GPU Operator v25.3.1+ |
| Data | Append-only ledger | Double-entry bookkeeping with PostgreSQL rules |
| Audit | Full trail | Teleport session recording + Loki logs |

### Critical CVEs to Patch

- **CVE-2025-23266 (NVIDIAScape)**: CVSS 9.0 container escape via NVIDIA Container Toolkit. A 3-line Dockerfile can gain root on the host. Requires Container Toolkit v1.17.8+ and GPU Operator v25.3.1+.
- **LeftoverLocals**: GPU local memory retains computation residues across containers. Affects all shared GPU configurations without MIG.

---

## Scaling Considerations

| Scale | Hardware | Architecture Complexity |
|-------|----------|----------------------|
| 50 students | 4-8 consumer GPUs | K8s + time-slicing + basic dashboard |
| 100 students | 8-16 mixed GPUs | + Kueue + Keycloak + credit system |
| 200 students | 16-32 GPUs (include MIG) | + KAI Scheduler + Teleport + full monitoring |
| 500 students | 32-64+ GPUs + cloud bursting | + SkyPilot for overflow to cloud providers |

---

## Alternatives Considered

| Alternative | Why Not |
|-------------|---------|
| JupyterHub + KubeSpawner | Only Jupyter notebooks, not full dev environments |
| Open OnDemand + Slurm | Traditional HPC, poor for container-native workflows |
| Coder (coder.com) | Strong alternative for workspace management; consider as future integration |
| Determined AI | ML-specific, not general-purpose compute |
| K3s | Limited to ~50-100 nodes, missing advanced networking |
| Nomad | GPU ecosystem far smaller than Kubernetes |
| Kata Containers (default) | Limited to single GPU passthrough, no fractional sharing |
| Cilium (over Calico) | No GlobalNetworkPolicy guardrails for academic multi-tenancy |
| Kafka (over NATS) | Massive overkill for university scale; 500MB+ minimum footprint |
| ELK (over Loki) | 10-100x more storage cost, 4GB+ RAM minimum for Elasticsearch |

---

## Key Research Sources

- NVIDIA KAI Scheduler (open-sourced April 2025): [github.com/NVIDIA/KAI-Scheduler](https://github.com/NVIDIA/KAI-Scheduler)
- Modal.com architecture: [amplifypartners.com/blog-posts/how-modal-built-a-data-cloud-from-the-ground-up](https://www.amplifypartners.com/blog-posts/how-modal-built-a-data-cloud-from-the-ground-up)
- CVE-2025-23266 (NVIDIAScape): [wiz.io/blog/nvidia-ai-vulnerability-cve-2025-23266-nvidiascape](https://www.wiz.io/blog/nvidia-ai-vulnerability-cve-2025-23266-nvidiascape)
- LeftoverLocals GPU memory leak: [blog.trailofbits.com/2024/01/16/leftoverlocals](https://blog.trailofbits.com/2024/01/16/leftoverlocals-listening-to-llm-responses-through-leaked-gpu-local-memory/)
- GPUnion campus GPU sharing (HotNets 2025): [arxiv.org/html/2507.18928v2](https://arxiv.org/html/2507.18928v2)
- TensorFusion fractional GPU: [tensor-fusion.ai](https://tensor-fusion.ai/guide/overview)
- Stanford Sherlock cluster: [sherlock.stanford.edu/docs/user-guide/gpu/](https://www.sherlock.stanford.edu/docs/user-guide/gpu/)
- pgledger (double-entry bookkeeping): [github.com/pgr0ss/pgledger](https://github.com/pgr0ss/pgledger)
