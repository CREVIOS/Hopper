# Hopper - Testing Plan

> Comprehensive testing strategy covering all layers of the GPU cloud platform.

---

## Testing Philosophy

1. **Test without GPUs first**: The majority of the platform logic (billing, auth, pod lifecycle) can be tested without GPU hardware
2. **Layered mocking**: Mock at the lowest useful boundary (K8s API, DCGM metrics, SSH connections)
3. **Chaos over coverage**: A 100% covered billing system that fails during a network partition is worse than a 80% covered system that's been chaos-tested
4. **Test what matters**: Focus on financial correctness (credits), security boundaries (isolation), and reliability (pod lifecycle)

---

## Test Pyramid

```
         ╱╲
        ╱  ╲         E2E Tests (Playwright)
       ╱    ╲        Full student/admin workflows, cross-browser
      ╱──────╲
     ╱        ╲       Integration Tests
    ╱          ╲      Service-to-service, DB, K8s API, NATS
   ╱────────────╲
  ╱              ╲     Unit Tests
 ╱                ╲    Business logic, credit calculations, state machines
╱──────────────────╲
```

| Layer | Count Target | Speed | GPU Required |
|-------|-------------|-------|-------------|
| Unit | 200+ | < 5 min total | No |
| Integration | 80+ | < 15 min total | No (mocked) |
| E2E | 30+ | < 30 min total | Staging (1-2 GPUs) |
| Load | 5 scenarios | < 30 min total | Staging |
| Chaos | 8 experiments | < 1 hour total | Staging |
| Security | 10 scenarios | Manual + automated | Staging |

---

## 1. Unit Testing

### 1.1 Credit Ledger (Python - pytest)

The most critical unit tests in the system. Financial correctness is non-negotiable.

```python
# tests/unit/test_credit_ledger.py

class TestCreditLedger:
    """Test double-entry bookkeeping invariants."""

    def test_deduction_creates_balanced_entries(self):
        """Every transfer produces exactly two entries that sum to zero."""

    def test_deduction_fails_on_insufficient_balance(self):
        """Cannot deduct more than available balance."""

    def test_concurrent_deductions_are_serialized(self):
        """Advisory locks prevent double-spend under concurrent access."""
        # Spawn 10 threads each trying to deduct 50 credits from 100-credit account
        # Exactly 2 should succeed, 8 should fail

    def test_balance_never_goes_negative(self):
        """Under no circumstances can balance drop below 0."""

    def test_compensating_entry_reverses_transaction(self):
        """Refund creates new entries, does not modify existing ones."""

    def test_ledger_entries_are_immutable(self):
        """UPDATE and DELETE operations on ledger_entries are rejected."""

    def test_previous_balance_chain_integrity(self):
        """Each entry's previous_balance equals the prior entry's current_balance."""

    def test_transfer_metadata_preserved(self):
        """Transfer metadata (pod_id, gpu_type) is stored and queryable."""
```

### 1.2 Pod Lifecycle State Machine (Go - testing)

```go
// orchestrator/lifecycle_test.go

func TestPodLifecycle(t *testing.T) {
    t.Run("valid_transitions", func(t *testing.T) {
        // REQUESTED -> PROVISIONING -> RUNNING -> TERMINATED
    })

    t.Run("invalid_transition_rejected", func(t *testing.T) {
        // TERMINATED -> RUNNING should error
    })

    t.Run("failed_from_any_active_state", func(t *testing.T) {
        // PROVISIONING -> FAILED, RUNNING -> FAILED are valid
    })

    t.Run("idempotent_creation", func(t *testing.T) {
        // Creating same pod twice returns existing pod, not error
    })

    t.Run("finalizer_prevents_premature_deletion", func(t *testing.T) {
        // Pod with active billing cannot be deleted until billing settles
    })
}
```

### 1.3 GPU Tier Pricing (Python - pytest)

```python
class TestGPUPricing:
    def test_premium_tier_rate(self):
        """RTX PRO 6000 Blackwell MIG charges 15 credits/hr."""

    def test_standard_tier_rate(self):
        """RTX 5090/4090 charges 10 credits/hr."""

    def test_budget_tier_rate(self):
        """RTX 4070 charges 5 credits/hr."""

    def test_scavenger_tier_free(self):
        """Scavenger (preemptible) pods charge 0 credits."""

    def test_partial_hour_billing(self):
        """45-minute session on Standard tier charges correctly (per-minute)."""

    def test_billing_stops_on_termination(self):
        """No credits deducted after pod enters TERMINATED state."""
```

### 1.4 RBAC Authorization (Python - pytest)

```python
class TestRBACAuthorization:
    def test_student_can_create_own_pod(self):
    def test_student_cannot_view_other_student_pod(self):
    def test_ta_can_view_course_pods(self):
    def test_ta_cannot_view_other_course_pods(self):
    def test_professor_can_allocate_credits(self):
    def test_student_cannot_allocate_credits(self):
    def test_admin_can_access_all_resources(self):
    def test_expired_token_rejected(self):
    def test_invalid_token_rejected(self):
    def test_role_scope_enforcement(self):
        """TA for CS229 cannot access CS231N resources."""
```

### 1.5 Session Reaper (Python - pytest)

```python
class TestSessionReaper:
    def test_expired_session_cleaned_up(self):
        """Sessions past expires_at are terminated and namespace deleted."""

    def test_active_session_not_reaped(self):
        """Sessions before expires_at are left running."""

    def test_reaper_idempotent(self):
        """Running reaper twice doesn't double-terminate."""

    def test_reaper_handles_already_deleted_namespace(self):
        """Gracefully handles race condition where namespace was already deleted."""

    def test_audit_event_emitted_on_reap(self):
        """NATS event emitted when session is reaped."""
```

---

## 2. Integration Testing

### 2.1 Test Infrastructure

Use Testcontainers for deterministic, isolated test environments:

```yaml
# docker-compose.test.yml
services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_DB: hopper_test
      POSTGRES_PASSWORD: test
    ports: ["5432:5432"]

  nats:
    image: nats:2.10-alpine
    command: ["--jetstream"]
    ports: ["4222:4222"]

  keycloak:
    image: quay.io/keycloak/keycloak:25.0
    command: ["start-dev"]
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: admin
    ports: ["8080:8080"]

  mock-k8s:
    build: ./tests/mocks/k8s-api
    ports: ["6443:6443"]

  mock-dcgm:
    build: ./tests/mocks/dcgm-exporter
    ports: ["9400:9400"]
```

### 2.2 API Gateway Integration Tests (Python - pytest + httpx)

```python
class TestPodAPI:
    """Test FastAPI endpoints against real PostgreSQL and mocked K8s."""

    async def test_create_pod_with_sufficient_credits(self):
        """POST /pods creates pod and deducts initial credits."""

    async def test_create_pod_insufficient_credits(self):
        """POST /pods returns 402 Payment Required when balance is 0."""

    async def test_create_pod_exceeds_quota(self):
        """POST /pods returns 429 when student exceeds max concurrent pods."""

    async def test_get_pod_metrics_sse(self):
        """GET /pods/{id}/metrics returns SSE stream with GPU metrics."""

    async def test_terminate_pod(self):
        """DELETE /pods/{id} triggers graceful termination."""

    async def test_pod_termination_stops_billing(self):
        """Credits stop being deducted after pod termination."""

    async def test_auth_required(self):
        """All endpoints return 401 without valid JWT."""

    async def test_rate_limiting(self):
        """Excessive requests return 429 Too Many Requests."""
```

### 2.3 Orchestrator Integration Tests (Go)

```go
func TestOrchestratorIntegration(t *testing.T) {
    // Uses client-go fake clientset

    t.Run("create_pod_with_gpu_request", func(t *testing.T) {
        // Creates pod with nvidia.com/gpu resource request
        // Verifies gVisor RuntimeClass is set
        // Verifies namespace isolation
    })

    t.Run("pod_event_published_to_nats", func(t *testing.T) {
        // Creates pod, verifies NATS receives state transition events
    })

    t.Run("billing_started_on_running", func(t *testing.T) {
        // Simulates pod reaching Running state
        // Verifies billing ticker starts via gRPC call to billing service
    })

    t.Run("namespace_cleanup_on_termination", func(t *testing.T) {
        // Terminates pod, verifies namespace and all resources deleted
    })

    t.Run("handles_pod_failure_gracefully", func(t *testing.T) {
        // Simulates pod entering Failed state
        // Verifies billing stops, cleanup occurs, error event emitted
    })
}
```

### 2.4 NATS Event Flow Tests

```python
class TestEventFlow:
    async def test_pod_created_event_triggers_billing_start(self):
        """Publishing gpu.pod.running event starts credit deduction."""

    async def test_pod_terminated_event_triggers_billing_stop(self):
        """Publishing gpu.pod.terminated event stops credit deduction."""

    async def test_low_balance_alert_emitted(self):
        """billing.alert.low event emitted when balance < 10%."""

    async def test_event_replay_after_consumer_restart(self):
        """JetStream replays unacknowledged events after consumer restarts."""

    async def test_dead_letter_on_processing_failure(self):
        """Failed message processing routes to dead letter queue."""
```

### 2.5 Keycloak Integration Tests

```python
class TestKeycloakIntegration:
    async def test_oidc_token_issuance(self):
        """Keycloak issues valid JWT with expected claims."""

    async def test_role_claims_in_token(self):
        """JWT contains user roles (student, ta, professor, admin)."""

    async def test_token_refresh(self):
        """Refresh token produces new valid access token."""

    async def test_token_validation_by_api(self):
        """FastAPI correctly validates and decodes Keycloak JWT."""

    async def test_invalid_token_rejected(self):
        """Token from different realm/issuer is rejected."""
```

---

## 3. Load Testing (Grafana k6)

### 3.1 Scenarios

```javascript
// tests/load/scenarios.js

export const options = {
  scenarios: {
    // Scenario 1: Class starting - 30 students launch pods simultaneously
    class_start: {
      executor: 'shared-iterations',
      vus: 30,
      iterations: 30,
      maxDuration: '5m',
    },

    // Scenario 2: Steady state - students checking dashboard metrics
    metrics_polling: {
      executor: 'constant-vus',
      vus: 100,
      duration: '10m',
      startTime: '5m',
    },

    // Scenario 3: Spike - multiple classes starting at once
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 150 },
        { duration: '5m', target: 150 },
        { duration: '1m', target: 0 },
      ],
      startTime: '15m',
    },

    // Scenario 4: End of class - mass pod termination
    class_end: {
      executor: 'shared-iterations',
      vus: 30,
      iterations: 30,
      maxDuration: '5m',
      startTime: '22m',
    },

    // Scenario 5: Billing stress - concurrent credit operations
    billing_stress: {
      executor: 'constant-vus',
      vus: 50,
      duration: '5m',
      startTime: '27m',
    },
  },

  thresholds: {
    'http_req_duration{scenario:class_start}': ['p(95)<2000'],  // Pod creation < 2s API response
    'http_req_duration{scenario:metrics_polling}': ['p(95)<200'],  // Metrics < 200ms
    'http_req_duration{scenario:spike}': ['p(95)<5000'],  // Spike tolerance
    http_req_failed: ['rate<0.01'],  // < 1% error rate
  },
};
```

### 3.2 Performance Targets

| Metric | Target | Rationale |
|--------|--------|-----------|
| Pod creation API response | < 2s (p95) | Students expect near-instant response |
| Pod ready (SSH-able) | < 60s | Including image pull (cached) |
| Dashboard metrics refresh | < 200ms (p95) | SSE delivery latency |
| Credit balance query | < 50ms (p95) | Always-visible balance must be fast |
| Concurrent SSE connections | 200+ | 100 students with 2 sessions each |
| Pod termination | < 10s | Including namespace cleanup |
| Login flow | < 3s | SSO redirect + token exchange |

---

## 4. Chaos Engineering (Chaos Mesh)

### 4.1 Experiments

| # | Experiment | What We Test | Success Criteria |
|---|-----------|-------------|-----------------|
| 1 | Kill random GPU pod | Pod cleanup, billing stops | Credits stop, session status updated, cleanup complete |
| 2 | Network partition GPU node | Pod resilience, SSH reconnection | Running pods survive, SSH reconnects, metrics show gap not crash |
| 3 | Kill NATS pod | Event bus resilience | Events buffered, replayed after recovery, no lost billing events |
| 4 | Kill orchestrator pod | State reconciliation | K8s restarts orchestrator, informer cache rebuilds, no orphaned pods |
| 5 | PostgreSQL slow queries | Billing latency tolerance | Billing degrades gracefully, no double-charges |
| 6 | Fill disk on GPU node | Storage pressure handling | Pods evicted gracefully, alerts fire, new pods schedule elsewhere |
| 7 | Kill DCGM exporter | Metrics gap handling | Dashboard shows "stale" indicator, no crashes |
| 8 | Simultaneous pod creation + termination | Race condition detection | Billing consistent, no orphaned namespaces |

### 4.2 Verification Checklist (Run After Every Chaos Session)

```bash
# 1. Billing integrity check
SELECT SUM(CASE WHEN direction = 1 THEN amount ELSE -amount END)
FROM ledger_entries;
# Must equal 0 (double-entry invariant)

# 2. No orphaned namespaces
kubectl get ns | grep student- | wc -l  # Should match active sessions count
SELECT COUNT(*) FROM active_sessions WHERE status = 'running';

# 3. No running pods without active sessions
kubectl get pods -A -l app=student-pod --field-selector=status.phase=Running | wc -l
# Should match active sessions count

# 4. No negative balances
SELECT * FROM account_balances WHERE balance < 0;
# Should return 0 rows

# 5. NATS stream health
nats stream report  # No stuck consumers, no unacknowledged messages
```

---

## 5. Security Testing

### 5.1 Container Escape Tests

| Test | Method | Expected Result |
|------|--------|----------------|
| Mount host filesystem | Pod spec with `hostPath` | Rejected by PodSecurityStandard |
| Privileged container | Pod spec with `privileged: true` | Rejected by admission controller |
| Host network access | Pod spec with `hostNetwork: true` | Rejected by PodSecurityStandard |
| Exploit CVE-2025-23266 | 3-line Dockerfile with LD_PRELOAD | Blocked (patched Container Toolkit) |
| Syscall escape (gVisor) | Raw syscalls from within container | Intercepted by gVisor |

### 5.2 Network Isolation Tests

| Test | Method | Expected Result |
|------|--------|----------------|
| Cross-namespace pod access | `curl` from pod-A to pod-B in different namespace | Connection refused (Calico policy) |
| Control plane access | `curl` to Kubernetes API from student pod | Connection refused |
| DNS exfiltration | Resolve external DNS from student pod | Allowed (only kube-dns, no custom resolvers) |
| Internet access | `curl https://pypi.org` | Allowed (ports 80/443 only) |
| Internal service access | `curl` to NATS/PostgreSQL from student pod | Connection refused |

### 5.3 Authentication/Authorization Tests

| Test | Method | Expected Result |
|------|--------|----------------|
| API without token | `curl -X POST /pods` | 401 Unauthorized |
| Expired token | Use token past `exp` claim | 401 Unauthorized |
| Wrong role | Student token on admin endpoint | 403 Forbidden |
| Cross-tenant access | Student A token accessing Student B's pod | 403 Forbidden |
| Token from wrong issuer | JWT signed by different Keycloak realm | 401 Unauthorized |
| Credit manipulation | Modify credit balance via SQL injection | Input sanitized (parameterized queries) |

### 5.4 GPU Memory Isolation Tests

| Test | Method | Expected Result |
|------|--------|----------------|
| Read residual GPU memory | Allocate + read uninitialized CUDA memory | Zeroed (CUDA_DEVICE_MEMORY_CLEANUP=1) |
| VRAM overallocation | Allocate more VRAM than assigned | Pod killed by monitoring sidecar |
| MIG boundary crossing | Access memory outside MIG partition | Hardware-blocked by MIG |

---

## 6. Testing Without GPUs (CI/CD Pipeline)

### 6.1 Mock Strategy

```
Layer 1: Application Logic (no mocks needed)
  - Credit calculations, state machines, RBAC checks
  - Run: Every commit, < 2 min

Layer 2: Service Integration (mock K8s + DCGM)
  - FastAPI → mock K8s API → mock pod responses
  - Orchestrator → fake client-go clientset
  - Dashboard → mock DCGM metrics endpoint
  - Run: Every PR, < 10 min

Layer 3: Infrastructure Integration (Testcontainers)
  - Real PostgreSQL, NATS, Keycloak in containers
  - Mock only: K8s API, DCGM exporter
  - Run: Every PR merge to main, < 15 min

Layer 4: Staging (real K8s + 1-2 GPUs)
  - Full stack on staging cluster
  - Run: Nightly, < 1 hour
```

### 6.2 CI Pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Python unit tests
        run: pytest tests/unit/ -v --cov
      - name: Go unit tests
        run: cd orchestrator && go test ./... -v -race

  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    services:
      postgres:
        image: timescale/timescaledb:latest-pg16
      nats:
        image: nats:2.10-alpine
      keycloak:
        image: quay.io/keycloak/keycloak:25.0
    steps:
      - uses: actions/checkout@v4
      - name: Run integration tests
        run: pytest tests/integration/ -v

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install dependencies
        run: cd frontend && pnpm install
      - name: Run Svelte tests
        run: cd frontend && pnpm test
      - name: Build check
        run: cd frontend && pnpm build

  e2e-tests:
    runs-on: ubuntu-latest
    needs: [integration-tests, frontend-tests]
    steps:
      - uses: actions/checkout@v4
      - name: Start test stack
        run: docker compose -f docker-compose.test.yml up -d
      - name: Install Playwright
        run: npx playwright install
      - name: Run E2E tests
        run: npx playwright test
```

---

## 7. Test Data Strategy

### 7.1 Seed Data (for development and testing)

```sql
-- Seed users
INSERT INTO users (id, email, role) VALUES
  ('student-1', 'alice@university.edu', 'student'),
  ('student-2', 'bob@university.edu', 'student'),
  ('ta-1', 'carol@university.edu', 'ta'),
  ('prof-1', 'dave@university.edu', 'professor'),
  ('admin-1', 'eve@university.edu', 'admin');

-- Seed credit accounts with initial balance
INSERT INTO accounts (id, name, type, owner_id, owner_type) VALUES
  ('acct_alice', 'Alice Credits', 'asset', 'student-1', 'student'),
  ('acct_bob', 'Bob Credits', 'asset', 'student-2', 'student'),
  ('system_revenue', 'System Revenue', 'liability', NULL, 'system');

-- Seed initial credit allocation (100 credits each)
SELECT add_credits('acct_alice', 100, 'initial_allocation', '{}');
SELECT add_credits('acct_bob', 100, 'initial_allocation', '{}');
```

### 7.2 Test Fixtures

```python
# tests/conftest.py

@pytest.fixture
async def student_with_credits(db):
    """Create a student user with 100 credits."""
    user = await create_user(email="test@uni.edu", role="student")
    account = await create_account(owner=user)
    await add_credits(account.id, 100)
    return user, account

@pytest.fixture
async def running_pod(student_with_credits, mock_k8s):
    """Create a student with a running GPU pod."""
    user, account = student_with_credits
    pod = await create_pod(user_id=user.id, gpu_type="rtx4090")
    mock_k8s.set_pod_status(pod.name, "Running")
    return user, account, pod
```

---

## 8. Metrics to Track

| Metric | Tool | Alert Threshold |
|--------|------|----------------|
| Unit test coverage | pytest-cov / go test -cover | < 80% → warning |
| Integration test pass rate | CI pipeline | < 100% → block merge |
| E2E test pass rate | Playwright | < 95% → block deploy |
| Load test p95 latency | k6 | > 500ms → investigate |
| Chaos experiment failures | Chaos Mesh | Any billing inconsistency → critical |
| Security test failures | Manual + automated | Any → block release |
| Test execution time | CI pipeline | Unit > 5min, Integration > 15min → optimize |
