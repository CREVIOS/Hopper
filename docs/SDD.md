# Hopper — Software Design Document (SDD)

| Field | Value |
|--------|--------|
| **Course** | CSE 4113: Internet Programming Lab |
| **Deliverable** | Software Design Document (SDD) |
| **Project** | Hopper (Hopper Cloud) — a VM / compute provisioning panel for universities |
| **Submitted to** | Prof. Dr. Md. Mamun Or Rashid; Mr. Md. Fahim Arefin; Mr. Md. Ahasanul Alam |
| **Document version** | 0.2 |
| **Date** | April 2026 |

---

## Abstract

This Software Design Document specifies the **architecture and major design decisions** for **Hopper**, a self-hosted platform that gives students and staff **self-service access** to isolated workloads on **Kubernetes**, with **institutional SSO (Keycloak)**, **credit-based usage**, and a **web portal (SvelteKit)** backed by a **FastAPI** gateway and a **Go** orchestration service. The design is a **collaboration** between **Four-Eyed Raven** (Team 1), who established the **Hopper Cloud** core baseline, and **VMpire (Byte Me, Team 2)**, who contribute **complementary** lifecycle, approval, and quota requirements—**one shared codebase** at `https://github.com/CREVIOS/Hopper`, informed by both teams’ Software Requirements Specifications.

---

## Teams

| Team | Name | Role in this project |
|------|------|------------------------|
| **Team 1** | **Four-Eyed Raven** | **Hopper Cloud** origin: GPU-centric platform baseline, core portal and orchestration scope |
| **Team 2** | **VMpire (Byte Me)** | **Partner team**: lifecycle governance, approvals, quotas, notifications, and admin-facing workflows—integrated with Team 1’s design |

**Related documents:** `docs/ARCHITECTURE.md`, `docs/TECH_STACK.md`, `docs/TASKS.md`, `README.md`, **`docs/SRS Hopper Combined.tex`** (canonical SRS for the collaboration), `docs/SRS Four-Eyed Raven.tex`, `docs/SRS  Byte Me 🦇.tex` (lineage SRS files; the Byte Me path on disk has two spaces before “Byte”; filename may include a bat emoji).

---

## Contents

1. [Document control](#1-document-control) — metadata, authors, revision history  
2. [Purpose and scope](#2-purpose-and-scope-of-this-sdd)  
3. [System context](#3-system-context)  
4. [Design goals and constraints](#4-design-goals-and-constraints)  
5. [High-level architecture](#5-high-level-architecture)  
6. [Component design](#6-component-design)  
7. [Data design](#7-data-design)  
8. [Key runtime flows](#8-key-runtime-flows)  
9. [Security design](#9-security-design)  
10. [Non-functional design](#10-non-functional-design)  
11. [Evolution roadmap](#11-evolution-roadmap-design-level)  
12. [References](#12-references)  

**Appendices**

- [A. Requirements traceability](#appendix-a-requirements-traceability)  
- [B. External interface overview](#appendix-b-external-interface-overview)  
- [C. Critical flows — success, failure, recovery](#appendix-c-critical-flows--success-failure-recovery)  
- [D. State machines](#appendix-d-state-machines)  
- [E. Data model — depth](#appendix-e-data-model--depth)  
- [F. Security architecture (extended)](#appendix-f-security-architecture-extended)  
- [G. Non-functional requirements — targets](#appendix-g-non-functional-requirements--targets)  
- [H. Deployment and operations (design view)](#appendix-h-deployment-and-operations-design-view)  
- [I. Configuration model](#appendix-i-configuration-model)  
- [J. Verification strategy](#appendix-j-verification-strategy)  
- [K. Glossary and assumptions](#appendix-k-glossary-and-assumptions)  
- [L. Document alignment and versioning](#appendix-l-document-alignment-and-versioning)

---

## 1. Document control

| Field | Value |
|--------|--------|
| **Product** | Hopper (Hopper Cloud) |
| **Repository** | `https://github.com/CREVIOS/Hopper` |
| **SDD version** | 0.2 |
| **Status** | Submitted (course deliverable) |
| **Date** | April 2026 |

### 1.1 Authorship and team structure

**Collaboration model:** **Four-Eyed Raven** (Team 1) and **VMpire (Byte Me, Team 2)** are **joint contributors** to one Hopper product. Team 1 anchored the original **Hopper Cloud** vision and repository; Team 2 brings the **VMpire** requirements set (lifecycle, approvals, quotas, operations). Both teams’ SRS inputs are merged in **`docs/SRS Hopper Combined.tex`** and implemented on a **single** roadmap—this is a **shared** design, not two separate products.

### 1.2 Authors by team

#### Four-Eyed Raven (Team 1)

| Name | Identifier / contact |
|------|----------------------|
| Tazkia Malik | Roll 7 — maliktazkia@gmail.com |
| Md. Sadek Hossain Asif | Roll 15 — asifsadek509@gmail.com |
| Tanzila Khan | Roll 25 — tanzila011001@gmail.com |
| Taif Ahmed Turjo | Roll 45 — ahmedtaif437@gmail.com |

#### VMpire — Byte Me (Team 2)

| Name | Identifier / contact |
|------|----------------------|
| Anindya Kundu | Roll 09 — sanindya50@gmail.com |
| Kabya Mithun Saha | Roll 16 — kabyasaha1812@gmail.com |
| Md. Muhaiminul Islam Ninad | Roll 43 — ninadgns@gmail.com |
| Fayek Ahmed | Roll 57 — fayekahmedrahat90@gmail.com |

### 1.3 Revision history

| Version | Date | Summary |
|---------|------|---------|
| 0.1 | April 2026 | Initial SDD: unified design for Four-Eyed Raven + VMpire (Byte Me); aligns repo with both SRS themes |
| 0.2 | April 2026 | Traceability, interface/event specs, flows, state machines, data/security/NFR/deployment/config/testing depth, glossary; SRS path housekeeping |

---

## 2. Purpose and scope of this SDD

### 2.1 Purpose

- Record **what** the system does at a design level (major components, data, interfaces, security boundaries).
- Give **all eight members** a single reference for how work maps to architecture.
- Document how **Four-Eyed Raven** and **VMpire (Byte Me)** SRS themes come together in one implementation (see §1.1 and §3).

### 2.2 In scope (design)

- Web portal, API gateway, orchestration service, persistence, eventing, and Kubernetes integration as implemented or specified in-repo.
- Cross-cutting concerns: authentication, credits/ledger, session/pod lifecycle, observability hooks.

### 2.3 Out of scope (this document)

- Low-level line-by-line API listing (see OpenAPI via FastAPI and `README.md` endpoint tables).
- Full hypervisor/vSphere/Proxmox integration (the VMpire lineage SRS discussed external APIs; Hopper targets Kubernetes—see §6.4).

---

## 3. System context

### 3.1 Problem summary (collaborative product)

- **Four-Eyed Raven — Hopper Cloud:** Students need **fair, isolated access** to institutional **GPU** (and related) compute without ad-hoc admin work; **credits**, **auditability**, **gVisor**, **network policy**, and **Teleport-class SSH** are central.
- **VMpire (Byte Me):** Academic environments also need **clear lifecycle governance**—**approvals**, **quotas**, **visibility into workloads**, **expiration policies**, and **notifications**—so staff and students share a fair, accountable platform.

**Unified stance:** The **shipping system** is **Hopper** on **Kubernetes**: user-facing “VMs” are **workload sessions backed by Pods** (see `README.md` VM plans and orchestrator). **GPU** depth is specified in the Four-Eyed Raven SRS and `docs/ARCHITECTURE.md`; the **current repo** may emphasize CPU/RAM plans in places while protos and docs still reflect GPU evolution—design treats **orchestrator + plans** as the abstraction for tiered compute.

### 3.2 Stakeholders (combined)

Students/researchers, lab administrators, instructors/PIs, platform engineers, and institutional IT—as in both SRS documents—with **role models** that combine the **Hopper Cloud** role ladder (student through platform admin) and **VMpire**-aligned needs for **instructors** and **lab administrators** (dashboards, approvals, course context). Some items remain **scheduled** for later milestones.

---

## 4. Design goals and constraints

| Goal | Design implication |
|------|---------------------|
| Security-first multi-tenancy | Default-deny networking (Calico/Cilium per deployment), curated images, identity via Keycloak |
| Fair usage | Double-entry **credit ledger**, per-minute metering, automated termination on exhaustion |
| Operational simplicity | Few moving parts at app layer: FastAPI + Go orchestrator + Postgres + NATS |
| Academic SSO | OIDC through Keycloak; SAML brokering as per deployment docs |
| Four-Eyed Raven non-goals | No public multi-tenant SaaS, no real-money payments in v1, no student-built image registry in v1 |
| VMpire collaboration themes | **Approval-before-provision**, **richer expiration notifications**, **course-scoped quotas** → **coordinated** with the shared architecture (see §8; roadmap §11) |

**Technical constraints** (from SRS + repo): PostgreSQL with Alembic migrations; gRPC between API gateway and orchestrator; NATS JetStream for billing/metrics events; Kubernetes API for workload lifecycle.

---

## 5. High-level architecture

The runtime architecture matches **`docs/ARCHITECTURE.md`** and **`README.md`**:

```
Browser ──► Ingress ──► SvelteKit (frontend)
                     ──► FastAPI (API gateway) ──► PostgreSQL
                     ──► Keycloak (OIDC)         ──► NATS JetStream
                                                      │
                         Orchestrator (Go) ◄──────────┘
                                │
                                ▼
                         Kubernetes API ──► User workload Pods / Services
```

**Layers:**

1. **Access:** Keycloak (auth); SSH via NodePort/Teleport patterns per environment (`README.md` vs full Teleport in ARCHITECTURE).
2. **Application:** SvelteKit UI; FastAPI REST + SSE; Go orchestrator (gRPC server, billing ticker, K8s integration, NATS publish).
3. **Data:** PostgreSQL (users, sessions, append-only ledger); optional TimescaleDB for metrics time-series as deployed.
4. **Platform:** Kubernetes, GPU/CPU scheduling stack as configured (`k8s/`, GPU Operator values, etc.).

---

## 6. Component design

### 6.1 Frontend (`frontend/`)

- **SvelteKit 2 / Svelte 5** with server loads and client stores (`auth`, `pods`).
- **Routes:** dashboard, pods (list + detail with metrics/terminal placeholders), credits, admin stub, login.
- **Transport:** HTTP to `/api`; SSE for pod metrics where implemented.

**Design note:** Some **VMpire**-described UI (approval queue, global workload table, quota panel) is **not yet fully implemented** in the current baseline; it remains **on the shared roadmap** (see §11).

### 6.2 API gateway (`services/api-gateway/`)

- **FastAPI** application: routers for `auth`, `pods`, `credits`, `admin`.
- **Responsibilities:** OIDC session handling, JWT validation, credit checks on create, ledger operations, NATS consumption for billing deductions, SSE bridging for metrics.
- **Persistence:** SQLAlchemy async models: `User`, `Account`, `Transfer`, `LedgerEntry`, `PodSession` (see Alembic migrations).

### 6.3 Orchestrator (`services/orchestrator/`)

- **Go** service: gRPC **Pod** and **Billing** services, K8s client, NATS publishers, periodic billing/metrics loops (`internal/` packages: `grpc`, `k8s`, `pod`, `billing`, `events`).
- **Responsibilities:** Create/terminate pods, reflect status, stream metrics to gateway path, emit billing events.

### 6.4 VMpire SRS mapping (Kubernetes vs hypervisor API)

The **VMpire** lineage SRS discussed a **hypervisor REST API**. **Hopper’s combined design standardizes on Kubernetes**: provisioning is **namespace/pod/service** creation—not vSphere/Proxmox directly. Features such as **pending → approved → provisioning** map to **workflow state** and **admin APIs** on the **same** orchestrator and database, as a **unified** approach with Team 1’s core flows.

### 6.5 Protocol contracts (`proto/`)

- `hopper/pod/v1/pod.proto` — `PodOrchestrator`: create, terminate, status, metrics stream, etc.
- `hopper/billing/v1/billing.proto` — `BillingService`: deduct, balance, usage stream.

Code generation: scripts in `scripts/`, Docker builds, `generate_proto.sh` under api-gateway.

### 6.6 Infrastructure and GitOps (`infrastructure/`, `k8s/`)

- **Pulumi** (Python) and **Ansible** playbooks for bring-up.
- **Kubernetes manifests** under `k8s/deploy/`, network policies, scheduler/GPU operator **values** under `k8s/*`.
- **Observability** under `observability/` (Prometheus, Grafana, Loki configs).

**REST/gRPC/NATS/SSE surfaces and state machines:** [Appendix B](#appendix-b-external-interface-overview), [Appendix D](#appendix-d-state-machines).

---

## 7. Data design

### 7.1 Core entities (as implemented)

- **User** — identity, role, university linkage.
- **Account / Transfer / LedgerEntry** — double-entry credit ledger; immutability enforced at DB layer (rules/triggers per migrations).
- **PodSession** — session lifecycle, plan/tier fields, SSH metadata, status, charges.

### 7.2 VMpire data concepts (future alignment)

Entities from the **VMpire** requirements—**VM Request**, **Quota Policy** scoped by course/department, **Notification**—should be introduced **without breaking** ledger integrity: e.g. `vm_requests` or `provisioning_requests` table with FK to `users`, state machine **pending → approved → …** joining to `PodSession` on approval.

**Relationships, indexes, ledger locking:** [Appendix E](#appendix-e-data-model--depth).

---

## 8. Key runtime flows

### 8.1 Create session (“VM”)

1. User selects **plan/tier** → `POST /pods/` with auth cookie.
2. Gateway validates JWT, checks **credit sufficiency**, creates **PodSession**, calls orchestrator **CreatePod** via gRPC.
3. Orchestrator creates K8s resources; returns connection info (e.g. SSH port).
4. **Billing loop:** orchestrator ticks → NATS `billing.deducted` → gateway updates ledger; on zero balance, exhaustion path triggers termination (see `README.md`).

### 8.2 Terminate session

User or admin triggers delete → gateway → orchestrator **TerminatePod** → cleanup; ledger and session state updated; events emitted.

### 8.3 Observability path

Metrics from orchestrator → NATS / SSE → dashboard components (`GpuMetrics` / CPU-RAM analogs depending on build).

**Failure branches, idempotency, and ordering:** [Appendix C](#appendix-c-critical-flows--success-failure-recovery).

---

## 9. Security design

| Concern | Approach |
|---------|----------|
| Authentication | Keycloak OIDC; JWT validation in gateway |
| Authorization | Role claims; route guards server-side |
| Network | Default-deny policies; documented Cilium/Calico intent |
| Audit | Ledger + session events; expand to full audit table per Four-Eyed Raven FR-HC-21 and VMpire FR-AUDIT-001 |
| Isolation | gVisor/runtime class and policies per `docs/ARCHITECTURE.md` for GPU rollout |

**Extended:** threat model, secrets, token lifetimes, and trust boundaries are in [Appendix F](#appendix-f-security-architecture-extended).

---

## 10. Non-functional design

| Area | Target (from combined SRS + repo docs) |
|------|------------------------------------------|
| Availability | Health endpoints; K8s replicas for stateless tiers |
| Performance | API responsiveness for dashboard; SSE for metrics; orchestrator tick interval documented |
| Observability | Prometheus/Grafana/Loki stack; structured logging in gateway |
| Testing | Unit, integration, e2e, load tests per `Makefile` and `docs/` |

**Measurable targets, backup/RPO/RTO, and “TBD” placeholders** are consolidated in [Appendix G](#appendix-g-non-functional-requirements--targets) with SRS NFR IDs.

---

## 11. Evolution roadmap (design-level)

| Phase | Emphasis |
|-------|----------|
| **Current** | MVP: SSO, pod/session lifecycle, credits, admin stubs, K8s deployment |
| **Next** | **Together:** platform hardening (RBAC depth, audit log UI, Teleport/gVisor/GPU operator as environments mature) **and** collaborative features from the combined SRS (approval workflow, quotas, notifications, instructor/lab dashboards) |
| **Later** | Full GPU tier UX parity with ARCHITECTURE.md; optional external hypervisor only if an institution requires non-K8s assets |

---

## 12. References

- Internal: `docs/ARCHITECTURE.md`, `docs/TECH_STACK.md`, `docs/TASKS.md`, `README.md`
- Protobuf: `proto/hopper/pod/v1/pod.proto`, `proto/hopper/billing/v1/billing.proto`
- OpenAPI: served by FastAPI at `/docs` (Swagger UI) when the API gateway is running
- SRS: **`docs/SRS Hopper Combined.tex`** (combined teams — canonical with SDD v0.2); source lineage: `docs/SRS Four-Eyed Raven.tex`, `docs/SRS  Byte Me 🦇.tex`
- External pointers cited in `docs/ARCHITECTURE.md` (NVIDIA KAI Scheduler, CVE-2025-23266, etc.)

---

## Appendix A. Requirements traceability

Maps SRS requirement IDs to this SDD and to **known code locations** (repository paths). “Partial / backlog” means not fully implemented or only partially aligned.

### A.1 Four-Eyed Raven (`docs/SRS Four-Eyed Raven.tex`) — functional

| ID | SDD section(s) | Primary code / artifact | Notes |
|----|------------------|-------------------------|--------|
| FR-HC-01, FR-HC-02 | §5–6, §9, App. B | `services/api-gateway/app/routers/auth.py`, `middleware/auth.py` | OIDC; token expiry → 401 |
| FR-HC-03–05 | §6–7, App. E | `routers/credits.py`, `services/credit_service.py`, `models/credit_ledger.py`, Alembic `001_*` | Ledger + RULEs in migration |
| FR-HC-06–08, FR-HC-25 | §6–8, App. C–D | `routers/pods.py`, `frontend/src/routes/pods/` | Create/list/terminate |
| FR-HC-09–11, FR-HC-24 | §5–6 | `k8s/`, `services/orchestrator/internal/k8s/` | GPU/MIG/time-slice: env-dependent |
| FR-HC-12–13 | §5 | `README.md` SSH; Teleport: backlog per ARCHITECTURE | NodePort SSH in POC |
| FR-HC-14–15 | §5, App. F | `k8s/deploy/04-network-policies.yaml` | Calico/Cilium as deployed |
| FR-HC-16–18 | §8, App. C | `billing_consumer.py`, `orchestrator` ticker + NATS | Reaper = exhaust path + TTL backlog |
| FR-HC-19–20 | §6 | `routers/credits.py`, `routers/admin.py` | Admin UI partial |
| FR-HC-21 | §7, App. E | Audit table: backlog; ledger is audit-like | |
| FR-HC-22–23 | §6 | PVC strategy in SRS vs repo: confirm `k8s` | |
| FR-HC-26 | App. B | `auth` router logout | |
| FR-HC-27 | — | Partial / backlog | Session extend |

### A.2 Four-Eyed Raven — non-functional

| ID | SDD / appendix | Evidence in repo |
|----|----------------|------------------|
| NFR-HC-1–4 | App. G | Latencies: provisioning timeout 30s gRPC client; billing 1 min tick |
| NFR-HC-5–18 | App. G, H | HA, mTLS, gVisor, observability: partial vs `docs/ARCHITECTURE.md` |
| NFR-HC-10 | App. C, E | Idempotency keys: **not** implemented for NATS deductions; ledger uses DB transaction + advisory lock |

### A.3 VMpire (Byte Me) — functional

*Source lineage file:* `docs/SRS  Byte Me 🦇.tex` (filename may include a bat emoji).

| ID | SDD section(s) | Primary code / artifact | Notes |
|----|------------------|-------------------------|--------|
| FR-REQ-001, FR-REQ-002 | §6.4, §7.2 | Backlog — no approval queue table/API yet | Workflow future |
| FR-QUOTA-001, FR-QUOTA-002 | §4 | Partial: credits + max 3 concurrent VMs in `pods.py` | Course quotas backlog |
| FR-MON-001–003 | §6, App. B | Dashboard + admin stub; metrics SSE | Global admin VM view partial |
| FR-LIFE-001–003 | App. D | `PodSession.state` simpler than Expiring→Decommissioned | Align over time |
| FR-REQ-003 | — | Backlog | Extension requests |
| FR-NOTIF-001 | — | Backlog | Email/in-app |
| FR-AUDIT-001 | App. E, F | Ledger immutable; full audit stream backlog | |
| FR-USER-001, FR-AUTH-001 | §9, App. F | JWT roles + Keycloak | SSO via OIDC |

### A.4 VMpire (Byte Me) — non-functional

| ID | App. G | Notes |
|----|--------|--------|
| NFR-PERF-001, NFR-PERF-002 | Mapped with Four-Eyed Raven targets | Vitals ≤60s vs metrics 5s NATS path |
| NFR-AVAIL-001 | TBD owner | |
| NFR-SEC-001–003 | App. F | |
| NFR-AUDIT-001 | Backlog | Retention policy TBD |
| NFR-SCALE-001 | TBD | |
| NFR-MAINT-001 | §6.4 | K8s adapter vs hypervisor — design choice |

---

## Appendix B. External interface overview

Authoritative wire details: **OpenAPI** (`/docs` on API gateway), **`.proto` files** under `proto/`. This appendix names stable surfaces only.

### B.1 REST (HTTP) — API gateway

**Base:** application routes are mounted with prefixes shown (see `services/api-gateway/app/main.py`). **Versioning:** none in URL path (single version **0.1.0** in FastAPI app metadata); breaking changes should bump API version in a future revision.

| Area | Prefix | Main operations | Typical errors |
|------|--------|-----------------|----------------|
| Auth | `/auth` | login redirect, callback, refresh, me | 302 redirects, 401 unauthorized |
| Pods | `/pods` | `GET /plans`, `GET /`, `POST /`, `GET /{id}`, `DELETE /{id}`, `GET /{id}/metrics` (SSE) | 402 insufficient credits, 429 max concurrent VMs, 403/404 |
| Credits | `/credits` | balance, history, allocate (role-gated) | 403 |
| Admin | `/admin` | users, courses, gpu-nodes | 403 |
| Health | `/` | `healthz`, `readyz` | — |

**Error model:** FastAPI `HTTPException` → JSON `{"detail": "..."}` unless redirect. No unified error code enum in v0.1.

**Pagination:** not applied to list endpoints in current code; document as **TBD** for large user/session lists.

### B.2 gRPC — orchestrator (internal)

**Service `PodOrchestrator`** (`proto/hopper/pod/v1/pod.proto`)

| RPC | Request | Response | Idempotency / notes |
|-----|---------|----------|---------------------|
| `CreatePod` | `CreatePodRequest` | `PodStatus` | **Not idempotent** — each call creates a new orchestrator-side pod id / workload. Retries can duplicate resources unless gateway deduplicates (currently **does not**). |
| `TerminatePod` | `PodId` | `TerminateResponse` | Safe to retry; returns `success: false` if pod unknown. |
| `GetPodStatus` | `PodId` | `PodStatus` | Read-only. |
| `StreamMetrics` | `PodId` | stream `VmMetrics` | Server stream; client cancel ends call. |
| `WatchPodStatus` | `PodId` | stream `PodStatus` | Minimal implementation (single send in code path). |
| `ListNodes` | `ListNodesRequest` | `ListNodesResponse` | Read-only. |

**Service `BillingService`** (`proto/hopper/billing/v1/billing.proto`): defined; **consumption path in POC is NATS + SQL ledger**, not only gRPC — confirm deployment wiring if extended.

### B.3 NATS subjects (fire-and-forget)

Defined in `services/orchestrator/internal/events/nats.go` and usage in `pod_service.go`, `handlers.go`, `billing_consumer.py`.

| Subject | Publisher | Payload (JSON) | Consumer / effect |
|---------|-----------|----------------|-------------------|
| `pod.created` | Orchestrator | `pod_id`, `user_id`, `ssh_port`, `plan` | (no subscriber in gateway default) |
| `pod.started` | — | — | Constant defined; usage may vary |
| `pod.stopped` | Orchestrator | `pod_id` | — |
| `pod.failed` | Orchestrator | `pod_id`, `user_id`, `error` | — |
| `billing.deducted` | Orchestrator (ticker) | `pod_id`, `amount`, `user_id` | Gateway → `deduct_credits()` |
| `billing.exhausted` | Gateway | `pod_id`, `user_id` | Orchestrator → stop pod / transition |
| `billing.allocated` | — | — | Constant defined |
| `metrics.<pod_id>` | Orchestrator | `pod_id`, `cpu_percent`, `memory_*` | Gateway SSE |

**Source of truth:** **PostgreSQL** for balances and `pod_sessions`; orchestrator holds **in-memory** pod manager state (lost on process restart — **operational gap**). NATS messages are **not** durably processed with JetStream ACK in the shown POC paths; **at-least-once** delivery would require idempotent consumers (dedupe keys backlog).

### B.4 SSE — pod metrics

**Endpoint:** `GET /pods/{pod_id}/metrics` (`EventSourceResponse`).

| Event name | Purpose |
|------------|---------|
| `connected` | Initial JSON with `pod_id` |
| `metrics` | JSON body matching NATS `metrics.*` payload |
| `ping` | Keepalive every 30s idle |

---

## Appendix C. Critical flows — success, failure, recovery

### C.1 Create session (happy path)

1. Gateway checks credits and concurrency (`pods.py`).
2. Inserts `PodSession` `state=pending`, commits.
3. `CreatePod` gRPC → orchestrator registers pod, creates K8s workload, starts billing ticker, publishes `pod.created` / `billing.deducted` ticks.

### C.2 Create session — failure branches

| Failure | Behavior | Recovery / gap |
|---------|----------|----------------|
| gRPC `CreatePod` throws (K8s error, timeout) | Gateway sets `PodSession.state = failed`, commits | **No automatic deletion** of row; user sees failed VM; manual cleanup / retry policy TBD |
| Partial success (DB commit then crash before gRPC) | Unlikely single-transaction; current code commits then calls gRPC | **Orphan `pending`** if process dies between commit and call — needs reconciliation job (backlog) |
| Duplicate POST from client | Two rows unless idempotency key — **not implemented** | Add `Idempotency-Key` or use single-flight |

### C.3 Credit exhaustion

1. `billing.deducted` → `deduct_credits` → `ValueError` → publish `billing.exhausted`.
2. Orchestrator subscriber moves pod to stopping/terminated; gateway marks DB `terminated`.

**Ordering:** deductions are **serialized per account** via `pg_advisory_xact_lock(hashtext(account_id))` in `deduct_credits`. Out-of-order NATS messages could theoretically double-charge without idempotent message keys — **mitigation backlog**: JetStream + dedupe id per tick.

### C.4 Terminate

Gateway calls `TerminatePod`; on RPC error, gateway still sets DB `terminated` — **K8s and DB may diverge**; ops should rely on `README` / admin tooling to reconcile.

---

## Appendix D. State machines

### D.1 Orchestrator in-memory pod (`services/orchestrator/internal/pod/types.go`)

States: `pending`, `creating`, `running`, `stopping`, `terminated`, `failed`.

| From | Allowed to |
|------|------------|
| `pending` | `creating`, `failed` |
| `creating` | `running`, `failed` |
| `running` | `stopping`, `failed` |
| `stopping` | `terminated`, `failed` |

**Triggers:** gRPC `CreatePod` / `TerminatePod`, K8s failures, `billing.exhausted` handler (`handlers.go`). Terminal: `terminated`, `failed`.

### D.2 Database `pod_sessions.state` (`app/models/session.py`)

String column; values used in code include `pending`, `creating`, `running`, `terminated`, `failed` (align with gateway mapping from gRPC). **Must stay consistent** with orchestrator for POC; full **VMpire** lifecycle states (e.g. Expiring / Decommissioned) are **not** modeled yet.

### D.3 Future: provisioning request (VMpire FR-REQ-*)

Not implemented. Planned pattern: `provisioning_requests` state machine **pending → approved \| rejected →** links to `PodSession` on approve.

---

## Appendix E. Data model — depth

**ERD:** not embedded in SDD; use Alembic migrations + SQLAlchemy models as the schema source of truth.

### E.1 Core relationships

- **User** (1) — (N) **PodSession** (`user_id` indexed).
- **User** (1) — (1) **Account** (credit asset account); **Account** (N) **LedgerEntry**; **Transfer** (1) — (2) **LedgerEntry** (double-entry).

### E.2 Uniqueness and hot paths

| Entity | Uniqueness | Index / hot path |
|--------|------------|------------------|
| `users.email` | Unique | Login lookup |
| `pod_sessions.id` | PK | Per-pod ops |
| `ledger_entries.account_id` | Indexed | Latest balance = `ORDER BY created_at DESC LIMIT 1` per account |
| Advisory lock | Per deduction | `pg_advisory_xact_lock(hashtext(account_id))` |

### E.3 Ledger concurrency

Append-only **transfers** + **ledger_entries**; immutability via DB RULEs (migration `001`). **Deduction** runs in one transaction with advisory lock — prevents concurrent deductions from racing; NATS duplicate delivery remains a **product gap** without idempotent message handling.

---

## Appendix F. Security architecture (extended)

### F.1 Assets and trust boundaries

| Asset | Location | Boundary |
|-------|----------|----------|
| User credentials | Keycloak / IdP | Browser ↔ Keycloak |
| Session/JWT | HTTP-only cookie / Bearer | Browser ↔ API gateway |
| Credit balances | PostgreSQL | Gateway only |
| K8s API credentials | kubeconfig / in-cluster ServiceAccount | Orchestrator pod |

### F.2 Threats (abbreviated)

| Abuse | Mitigation / status |
|-------|---------------------|
| Stolen JWT | HTTPS; short access token TTL (Keycloak); logout clears session |
| User reads another user’s pods | `user_id` check on `GET`/`DELETE` |
| Network lateral movement | NetworkPolicies — see `k8s/deploy/` and ARCHITECTURE |
| Pod escape | gVisor / GPU stack per deployment — partial vs SRS |

### F.3 Secrets and rotation

| Secret | Where | Rotation |
|--------|-------|----------|
| DB password | `HOPPER_DATABASE_URL` env / K8s Secret | Ops process |
| Keycloak client secrets | Keycloak realm | IdP ops |
| JWT verification | JWKS URL from Keycloak | Keycloak key rotation |

**Service-to-service:** gRPC currently **insecure channel** in `orchestrator_client.py` (`insecure_channel`) — **must use TLS/mTLS in production** (documented gap).

---

## Appendix G. Non-functional requirements — targets

Merged **SRS targets** with **implementation notes**. **TBD** = not verified or not owned in this document.

| Metric | Combined SRS (Four-Eyed Raven + VMpire themes) | Repo / SDD note |
|--------|------------------------------|-----------------|
| Provision p95 time | ≤90s (NFR-HC-1) | gRPC timeout 30s on create; end-to-end may need raise |
| Dashboard load | ≤3s (NFR-HC-2, NFR-PERF-001) | TBD measured |
| Credit UI lag | ≤5s after deduction (NFR-HC-3) | Depends on UI refresh |
| Reaper / exhaust | ≤30s (NFR-HC-4) | Exhaust path via NATS + consumer |
| Control plane uptime | ≥99.5% (NFR-HC-5, NFR-AVAIL-001) | **TBD** — SLO owner |
| API p95 latency | — | **TBD** |
| Orchestrator billing tick | 60s | `billing/ticker.go` |
| Metrics publish interval | 5s | `metrics_publisher.go` |
| Max concurrent sessions per user | 3 | Hardcoded in `pods.py` |
| Backup / RPO / RTO | — | **TBD** — Postgres backup strategy in ops runbook |
| Stateful HA | Postgres, NATS | Single-replica typical in POC; **TBD** multi-replica |

---

## Appendix H. Deployment and operations (design view)

### H.1 Topology (typical)

- **Single Kubernetes cluster** for app workloads; namespace **`hopper`** for user VMs in POC (`README.md`).
- **Components:** Ingress → SvelteKit + API gateway + Keycloak + orchestrator + Postgres + NATS (see `docker-compose.yml` for local, `k8s/deploy/*.yaml` for cluster).

### H.2 Stateful vs stateless

| Tier | Stateful? | HA note |
|------|-------------|---------|
| API gateway, orchestrator, frontend | Stateless | Scale replicas; shared DB |
| PostgreSQL | Stateful | PersistentVolume; failover **TBD** |
| NATS | Stateful if JetStream file store | **TBD** |
| Keycloak | Stateful DB backend | — |

### H.3 Observability ownership

Prometheus / Grafana / Loki configs under `observability/`; **alert rules** in `observability/prometheus/alerts/` — **owner: platform ops**, not duplicated here.

### H.4 Upgrade / rollback

GitOps / manifest version pins (**TBD** formal policy); database migrations via Alembic — **forward-only** unless manual downgrade scripts.

---

## Appendix I. Configuration model

| Config | Mechanism | Examples |
|--------|-----------|----------|
| API gateway | **Environment variables** `HOPPER_*` (`app/config.py`) | `HOPPER_DATABASE_URL`, `HOPPER_NATS_URL`, `HOPPER_KEYCLOAK_*`, `HOPPER_ORCHESTRATOR_URL`, `HOPPER_CORS_ORIGINS` |
| Orchestrator | Env (see `internal/config/config.go`) | `HOPPER_NATS_URL` |
| VM plans / credits per hour | **`VM_PLAN_RESOURCES`** in `app/schemas/pod.py` | Change code + redeploy |
| K8s resource limits | Orchestrator / manifests | `k8s/`, Dockerfile |

**Runtime vs rebuild:** plan tiers and credit rates are **code constants** today — not feature flags. Moving tiers to **ConfigMap** or DB is a product decision.

---

## Appendix J. Verification strategy

| Layer | Automation | Location / notes |
|-------|------------|------------------|
| Unit / integration | pytest, testcontainers | `tests/integration/` |
| E2E | Playwright | `tests/e2e/` — see `docs/E2E_TESTING.md` |
| Load / chaos | k6, Chaos Mesh samples | `tests/load/`, `tests/chaos/` |
| gRPC contract | **Manual / backlog** | No dedicated buf-breaking CI in SDD scope |
| NATS | Integration with real NATS container | `conftest.py` |

**Release gate (suggested, not enforced here):** smoke E2E + migration apply on staging DB; **manual** exploratory for SSH and SSO.

---

## Appendix K. Glossary and assumptions

### K.1 Glossary

| Term | Meaning in Hopper |
|------|-------------------|
| **VM** | User-facing name for an isolated workload; implementation is **Kubernetes Pod** + Service (not always a full VM). |
| **Session** | Row in `pod_sessions` tracking lifecycle and SSH/port info. |
| **Plan** | SKU for CPU/RAM/disk/credits (e.g. small/medium/large) — `VM_PLAN_RESOURCES`. |
| **Credits** | Institutional accounting units; **not** real money in v1. |
| **Orchestrator** | Go service speaking gRPC + K8s API. |
| **Gateway** | FastAPI control plane. |

### K.2 Assumptions and dependencies

| Assumption | |
|------------|--|
| Single IdP realm (`hopper`) for POC; production may use SAML broker per ARCHITECTURE. | |
| Cluster has working **CNI** and **StorageClass** if PVCs used. | |
| GPU Operator / gVisor present **only if** GPU isolation features are enabled (varies vs README CPU-only POC). | |
| Users reach Keycloak and API over trusted network (TLS termination at Ingress). | |

**External systems:** Keycloak, Kubernetes API, NATS, PostgreSQL, (optional) Teleport, Prometheus stack.

---

## Appendix L. Document alignment and versioning

| Artifact | Version / commit | Notes |
|----------|------------------|--------|
| **This SDD** | **0.2** | Adds appendices A–L |
| **SRS Hopper Combined** | **0.2** (this repo, `docs/SRS Hopper Combined.tex`) | **Canonical SRS** for the merged team; aligns with this SDD |
| **SRS Four-Eyed Raven** | v0.1 in source (March 2025 in SRS metadata) | Requirements baseline (lineage) |
| **SRS VMpire (Byte Me)** | v0.1 (2026-03-07 in source) | VMpire requirements lineage |
| **API (OpenAPI)** | FastAPI `version="0.1.0"` in `main.py` | Bump when API contract changes |
| **Repository** | moving HEAD | No separate “Hopper release” tag required for course submission |

**SRS file paths (verified under `docs/`):**

- `docs/SRS Four-Eyed Raven.tex`
- `docs/SRS  Byte Me 🦇.tex` (two spaces after `SRS`)

---

*End of Software Design Document v0.2 — CSE 4113: Internet Programming Lab*
