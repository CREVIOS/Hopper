# Hopper - Implementation Tasks

> 4-phase implementation plan. Each phase delivers a usable increment. Tasks are ordered by dependency within each phase.

---

## Phase 1: Foundation (Weeks 1-4)

> **Goal**: Bare-metal Kubernetes cluster with GPU support, basic pod creation, and SSH access.

### DevOps

- [ ] **D1.1** Provision bare-metal servers with Ansible
  - Install Ubuntu 22.04 LTS on all nodes
  - Configure networking (static IPs, DNS)
  - Set up SSH access for ops team
  - Harden OS (disable root SSH, configure firewall, fail2ban)

- [ ] **D1.2** Install NVIDIA drivers and container runtime
  - Install NVIDIA driver 550+ via Ansible role
  - Install NVIDIA Container Toolkit v1.17.8+ (patched for CVE-2025-23266)
  - Configure containerd with NVIDIA runtime as default
  - Validate GPU access: `nvidia-smi` in container

- [ ] **D1.3** Bootstrap Kubernetes cluster
  - Install kubeadm/kubelet/kubectl on all nodes
  - Initialize control plane (kubeadm init)
  - Join worker nodes (GPU nodes)
  - Configure kubeconfig and RBAC

- [ ] **D1.4** Install NVIDIA GPU Operator
  - Deploy via Helm (v25.3.1+)
  - Configure time-slicing (4 replicas per GPU for consumer cards)
  - Configure MIG on RTX PRO 6000 Blackwell (4x 24GB if available)
  - Deploy DCGM Exporter as DaemonSet
  - Validate: `kubectl describe node` shows `nvidia.com/gpu` resources

- [ ] **D1.5** Install container runtime security
  - Deploy gVisor (runsc) on all GPU nodes
  - Create RuntimeClass `gvisor` for student pods
  - Test GPU workload under gVisor (PyTorch training, inference)
  - Document any incompatible CUDA operations

- [ ] **D1.6** Install Calico for network isolation
  - Deploy Calico via Helm
  - Create GlobalNetworkPolicy: default deny inter-namespace
  - Allow DNS, internet egress (80/443), SSH gateway ingress
  - Test isolation between namespaces

- [ ] **D1.7** Set up Teleport SSH gateway
  - Deploy Teleport on Kubernetes (Helm chart)
  - Configure Teleport as SSH proxy
  - Set up static IP / DNS for `ssh.hopper.{university}.edu`
  - Create Teleport roles mapping to GPU access levels
  - Test: SSH into a manually-created GPU pod via Teleport

### Backend

- [ ] **B1.1** Set up Go orchestration service skeleton
  - Initialize Go module with client-go, gRPC, NATS dependencies
  - Implement gRPC service definition (PodOrchestrator)
  - Implement basic pod create/delete using client-go
  - Add Kubernetes namespace creation per user
  - Containerize with multi-stage Dockerfile

- [ ] **B1.2** Implement pod lifecycle state machine
  - Define states: REQUESTED, PROVISIONING, RUNNING, FAILED, TERMINATED
  - Use Kubernetes informers (shared informer factory) for pod state tracking
  - Emit state transitions to NATS JetStream
  - Implement idempotent pod creation (deterministic naming)
  - Add finalizers for cleanup guarantee

- [ ] **B1.3** Set up NATS JetStream
  - Deploy NATS on Kubernetes via Helm
  - Create JetStream streams for pod events and billing events
  - Implement Go producer (orchestrator → NATS)
  - Test message persistence and replay

- [ ] **B1.4** Set up PostgreSQL + TimescaleDB
  - Deploy PostgreSQL 16 with TimescaleDB extension on Kubernetes
  - Run initial schema migration (users, sessions, accounts)
  - Set up PgBouncer for connection pooling
  - Configure daily pg_dump backups

### Frontend

- [ ] **F1.1** Initialize SvelteKit project
  - Create SvelteKit 2 project with Svelte 5
  - Configure Tailwind CSS 4, shadcn-svelte components
  - Set up project structure: routes, lib, components
  - Configure adapter-node for self-hosted deployment

---

## Phase 2: Core Platform (Weeks 5-8)

> **Goal**: Full credit system, authentication, real-time dashboard, and pod management UI.

### Backend

- [ ] **B2.1** Set up FastAPI API gateway
  - Initialize FastAPI project with Pydantic v2
  - Implement REST endpoints: `POST /pods`, `GET /pods`, `DELETE /pods/{id}`
  - Implement SSE endpoint: `GET /pods/{id}/metrics`
  - Add request validation, error handling, structured logging
  - Generate OpenAPI documentation

- [ ] **B2.2** Implement gRPC communication
  - Define .proto files for PodOrchestrator and BillingService
  - Generate Python stubs (for FastAPI) and Go stubs (for orchestrator)
  - Wire FastAPI REST endpoints → gRPC calls to Go orchestrator
  - Implement gRPC streaming for metrics relay

- [ ] **B2.3** Implement credit ledger (double-entry bookkeeping)
  - Create schema: accounts, transfers, ledger_entries
  - Implement append-only enforcement (PostgreSQL RULEs)
  - Implement `deduct_credits()` function with advisory locks
  - Implement `add_credits()` for allocations and refunds
  - Create account_balances view
  - Write unit tests for race condition scenarios

- [ ] **B2.4** Implement billing ticker
  - Per-minute credit deduction for running pods
  - Integrate with pod lifecycle (start billing on RUNNING, stop on TERMINATED)
  - Implement low-balance warning (emit NATS event at < 10%)
  - Implement auto-termination when credits reach 0
  - Grace period: 5-minute SIGTERM before SIGKILL (allow checkpoint saving)

- [ ] **B2.5** Implement session reaper service
  - Background task that checks for expired sessions every 10 seconds
  - Delete namespace (kills pod, PVC, secrets)
  - Update session status in database
  - Emit audit event via NATS
  - Send notification to student (webhook/email)

- [ ] **B2.6** Set up Keycloak
  - Deploy Keycloak on Kubernetes
  - Create realm for university
  - Configure OIDC client for Hopper application
  - Set up role hierarchy: admin, professor, ta, student
  - Test token issuance and validation in FastAPI

- [ ] **B2.7** Implement university SSO integration
  - Configure Keycloak SAML identity brokering with university Shibboleth IdP
  - Map `eduPersonAffiliation` attributes to Keycloak roles
  - Implement WAYF (Where Are You From) discovery if multi-university
  - Test full SSO flow: student login → Shibboleth → Keycloak → JWT → Hopper

### Frontend

- [ ] **F2.1** Implement authentication flow
  - Keycloak OIDC integration (redirect-based login)
  - Token storage and refresh
  - Protected route middleware
  - User profile page (email, role, university)

- [ ] **F2.2** Build pod management dashboard
  - Pod creation form: GPU tier selector, container image selector, session duration
  - Pod template library: PyTorch, TensorFlow, JAX, custom
  - Active pods list with status indicators (Pending, Running, Failed, Terminated)
  - Pod detail view: logs, metrics, SSH connection info
  - Pod termination with confirmation dialog

- [ ] **F2.3** Build real-time GPU metrics panel
  - SSE connection to `/pods/{id}/metrics` endpoint
  - GPU utilization gauge (0-100%, color-coded)
  - VRAM usage bar (used/total)
  - Temperature gauge with thermal zones (green/yellow/red)
  - Power draw line chart with TDP reference
  - Auto-reconnection on connection loss

- [ ] **F2.4** Build credit dashboard
  - Current balance display (prominent, always visible)
  - Usage history table (session, GPU type, duration, credits charged)
  - Spending projection chart (credits remaining vs burn rate)
  - Low balance warning banner
  - Transaction log (all ledger entries)

- [ ] **F2.5** Build web terminal
  - xterm.js integration with WebSocket backend
  - Terminal resize handling (fit addon)
  - Connection status indicator
  - Copy/paste support
  - Link detection (web-links addon)

### DevOps

- [ ] **D2.1** Install KAI Scheduler
  - Deploy KAI Scheduler on Kubernetes
  - Configure hierarchical queues: University → Department → Course
  - Set fractional GPU policies (0.25 GPU minimum)
  - Configure fairshare with 7-day half-life decay

- [ ] **D2.2** Install Kueue for admission control
  - Deploy Kueue via Helm
  - Create ClusterQueues per GPU tier (Premium, Standard, Budget)
  - Define ResourceFlavors for MIG slices vs time-sliced GPUs
  - Test job queuing when resources are exhausted

- [ ] **D2.3** Set up monitoring stack
  - Deploy Prometheus via Helm (kube-prometheus-stack)
  - Configure DCGM Exporter scraping
  - Deploy Grafana with NVIDIA DCGM dashboard (#12239)
  - Deploy AlertManager with critical alerts (GPU temp, node down)
  - Configure TimescaleDB remote_write for long-term storage

- [ ] **D2.4** Set up logging stack
  - Deploy Grafana Loki via Helm
  - Deploy Promtail as DaemonSet with student pod log collection
  - Configure label extraction: namespace, user_id, session_id, course_id
  - Create Grafana dashboard for log exploration

---

## Phase 3: Hardening & Polish (Weeks 9-12)

> **Goal**: Security hardening, admin tools, testing, and production readiness.

### Backend

- [ ] **B3.1** Implement RBAC enforcement
  - Middleware: extract JWT claims → resolve permissions
  - Per-endpoint authorization checks
  - Resource-scoped permissions (course_id, department_id)
  - Admin-only endpoints: user management, credit allocation, system config

- [ ] **B3.2** Implement rate limiting
  - Per-user API rate limits (slowapi)
  - Pod creation rate limit: max 3 concurrent pods per student
  - SSE connection limit: max 10 concurrent streams per user
  - Admin bypass for rate limits

- [ ] **B3.3** Implement pod template system
  - Template CRUD API (professors/admins can create templates)
  - Template fields: base image, GPU requirements, environment variables, startup scripts
  - Pre-built templates: PyTorch 2.5, TensorFlow 2.17, JAX 0.5, RAPIDS 24.12
  - Template versioning and soft-delete

- [ ] **B3.4** Implement scavenger queue
  - Allow zero-credit students to run on idle GPUs
  - Mark scavenger pods as preemptible
  - Implement preemption logic: when a paying user needs a GPU, evict oldest scavenger pod
  - 30-second graceful termination for checkpoint saving

- [ ] **B3.5** Implement audit logging
  - Log all state-changing operations to dedicated audit table
  - Fields: who, what, when, resource, old_state, new_state, ip_address
  - Retention: 1 year minimum
  - Admin query API for audit logs

### Frontend

- [ ] **F3.1** Build admin dashboard
  - System overview: total GPUs, active pods, active users, credit pool
  - Per-GPU node status (utilization heatmap)
  - User management: search, view sessions, adjust credits
  - Course management: create courses, assign TAs, set quotas
  - Audit log viewer with filters

- [ ] **F3.2** Build professor/TA dashboard
  - Course student list with current sessions
  - Bulk credit allocation to course students
  - GPU quota management per course
  - Usage analytics: per-student GPU hours, credit burn rate
  - Template management (create/edit course-specific templates)

- [ ] **F3.3** Notification system
  - In-app notifications: low balance, session expiring, pod failed
  - Email notifications for critical events (optional, via webhook)
  - Notification preferences per user

- [ ] **F3.4** Mobile responsiveness
  - Responsive dashboard layout for tablet/phone
  - Touch-friendly pod management
  - Credit balance quick-view

### DevOps

- [ ] **D3.1** Set up ArgoCD for GitOps
  - Deploy ArgoCD on Kubernetes
  - Configure SSO with Keycloak
  - Create App of Apps: all Hopper services + infrastructure
  - Sync waves: infra first (NATS, PG) → services (API, orchestrator) → frontend
  - Enable auto-sync for staging, manual sync for production

- [ ] **D3.2** Set up Pulumi for infrastructure management
  - Define Pulumi stacks: dev, staging, production
  - Codify Kubernetes resource definitions (namespaces, quotas, network policies)
  - Codify DNS, TLS certificates
  - Store state in Pulumi Cloud or self-hosted S3

- [ ] **D3.3** Set up Ansible playbooks for GPU node management
  - Playbook: `gpu-node-setup.yml` (driver, toolkit, containerd, kubelet)
  - Playbook: `gpu-node-update.yml` (driver update with drain/uncordon)
  - Playbook: `security-hardening.yml` (OS hardening, firewall rules)
  - Inventory: group by GPU type for targeted operations

- [ ] **D3.4** Implement backup and disaster recovery
  - PostgreSQL: daily pg_dump + WAL archiving (point-in-time recovery)
  - Keycloak: realm export on schedule
  - Kubernetes: etcd snapshot daily
  - Test restore procedure monthly

- [ ] **D3.5** Security audit
  - Review Calico GlobalNetworkPolicy coverage
  - Verify gVisor RuntimeClass is enforced on all student pods
  - Verify NVIDIA Container Toolkit version (CVE-2025-23266 patch)
  - Run `kube-bench` for CIS Kubernetes benchmarks
  - Review all RBAC bindings
  - Verify PodSecurityStandards (restricted profile)

### Testing

- [ ] **T3.1** Unit tests for credit system
  - Test double-entry balance invariants
  - Test advisory lock under concurrent deductions
  - Test compensating entries
  - Test zero-balance prevention
  - Test refund flows

- [ ] **T3.2** Integration tests for pod lifecycle
  - Test full lifecycle: create → running → terminate
  - Test failure handling: image pull error, GPU allocation failure
  - Test billing integration: credits deducted during runtime
  - Test session expiry and reaper cleanup

- [ ] **T3.3** Load tests
  - k6 scenario: 30 students creating pods simultaneously (class start)
  - k6 scenario: 100 concurrent SSE connections (metrics polling)
  - k6 scenario: 100 concurrent billing transactions
  - k6 scenario: spike test (0 → 100 → 0 VUs)
  - Threshold: p95 < 500ms, error rate < 1%

---

## Phase 4: Production & Scale (Weeks 13-16)

> **Goal**: Production deployment, student onboarding, and operational maturity.

### DevOps

- [ ] **D4.1** Production deployment
  - Deploy full stack to production cluster
  - Verify all ArgoCD applications synced and healthy
  - Verify monitoring and alerting operational
  - Verify Teleport SSH access from campus and VPN

- [ ] **D4.2** Chaos engineering
  - Deploy Chaos Mesh on staging cluster
  - Run experiments: GPU pod kill, network partition, NATS failure
  - Verify billing consistency after all chaos scenarios
  - Verify pod cleanup after orchestrator crash
  - Verify dashboard shows appropriate error states

- [ ] **D4.3** Performance tuning
  - Profile FastAPI endpoints (identify slow queries)
  - Optimize Kubernetes scheduling latency
  - Tune PgBouncer pool sizes
  - Tune Prometheus scrape intervals and retention
  - Benchmark pod creation time (target: < 30s from request to SSH-ready)

- [ ] **D4.4** Set up on-call and runbooks
  - Create runbooks for common incidents: GPU node down, credit system error, SSH gateway unreachable
  - Configure AlertManager routing (critical → PagerDuty, warning → Slack)
  - Create incident response procedure
  - Document escalation path

### Frontend

- [ ] **F4.1** Onboarding flow
  - First-login welcome wizard
  - GPU tier explanation and recommendations
  - SSH key setup instructions (with copy-to-clipboard)
  - Quick-start tutorial: create pod → connect → run PyTorch

- [ ] **F4.2** Documentation site
  - Getting started guide
  - SSH connection guide (Teleport tsh + native SSH)
  - GPU tier descriptions and pricing
  - FAQ (common errors, billing questions)
  - API documentation (link to auto-generated OpenAPI)

### Backend

- [ ] **B4.1** Implement usage analytics API
  - Per-student usage over time
  - Per-course aggregate usage
  - Per-GPU utilization trends
  - Credit allocation vs consumption reports
  - Export to CSV for department reporting

- [ ] **B4.2** Implement webhook integrations
  - Slack/Discord notifications for admins (critical alerts)
  - Email notifications for students (session expiry, low balance)
  - Webhook API for custom integrations

### Testing

- [ ] **T4.1** End-to-end tests (see E2E_TESTING.md)
  - Full student workflow: SSO login → create pod → monitor → SSH → terminate
  - Full admin workflow: create course → allocate credits → view usage
  - Cross-browser testing (Chromium, Firefox, WebKit)

- [ ] **T4.2** Security penetration testing
  - Container escape attempts from student pod
  - Cross-namespace network access attempts
  - API authorization bypass attempts
  - Credit manipulation attempts
  - SSH key reuse after session termination

- [ ] **T4.3** Student beta testing
  - Onboard 10-20 students from a single course
  - Monitor credit consumption patterns
  - Collect feedback on UX (pod creation, SSH, dashboard)
  - Identify and fix top 5 usability issues
  - Measure pod creation time, SSH latency, dashboard load time

- [ ] **T4.4** Scale testing
  - Simulate 100 concurrent students (k6)
  - Measure: pod creation latency, credit deduction accuracy, SSE connection stability
  - Identify bottlenecks and optimize
  - Document capacity limits per GPU node configuration

---

## Task Count Summary

| Phase | DevOps | Backend | Frontend | Testing | Total |
|-------|--------|---------|----------|---------|-------|
| Phase 1: Foundation | 7 | 4 | 1 | 0 | **12** |
| Phase 2: Core | 4 | 7 | 5 | 0 | **16** |
| Phase 3: Hardening | 5 | 5 | 4 | 3 | **17** |
| Phase 4: Production | 4 | 2 | 2 | 4 | **12** |
| **Total** | **20** | **18** | **12** | **7** | **57** |

---

## Critical Path

The following tasks are on the critical path (blocking downstream work):

```
D1.2 (NVIDIA drivers) → D1.3 (K8s cluster) → D1.4 (GPU Operator)
  → B1.1 (Go orchestrator) → B1.2 (Pod lifecycle)
    → B2.1 (FastAPI) → B2.2 (gRPC) → F2.2 (Pod dashboard)

D1.4 (GPU Operator) → D2.1 (KAI Scheduler) → D2.2 (Kueue)

B1.4 (PostgreSQL) → B2.3 (Credit ledger) → B2.4 (Billing ticker)
  → F2.4 (Credit dashboard)

B2.6 (Keycloak) → B2.7 (SSO) → F2.1 (Auth flow)
```

---

## Definition of Done (Per Task)

- [ ] Code passes linting and formatting checks
- [ ] Unit tests written and passing (where applicable)
- [ ] Integration test written (for backend services)
- [ ] Documentation updated (API docs, runbooks)
- [ ] Code reviewed by at least one team member
- [ ] Deployed to staging and manually verified
- [ ] Monitoring/alerts configured (for infrastructure tasks)
