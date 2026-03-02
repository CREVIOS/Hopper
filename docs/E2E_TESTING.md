# Hopper - End-to-End Testing Criteria

> E2E tests validate complete user workflows from browser to GPU pod and back. All tests use Playwright.

---

## Test Environment

### Requirements

- **Staging Kubernetes cluster** with at least 1-2 real GPUs (or mock GPU environment)
- **Real Keycloak** instance with test realm and test users
- **Real PostgreSQL + TimescaleDB** (seeded with test data)
- **Real NATS JetStream**
- **Mock DCGM exporter** (returns synthetic GPU metrics for consistent testing)
- **Teleport** configured with test certificates

### Test Users

| User | Role | Credits | Course |
|------|------|---------|--------|
| `e2e-student-1@test.edu` | student | 100 | CS229 |
| `e2e-student-2@test.edu` | student | 0 | CS229 |
| `e2e-student-3@test.edu` | student | 100 | CS231N |
| `e2e-ta@test.edu` | ta | 500 | CS229 |
| `e2e-professor@test.edu` | professor | 1000 | CS229, CS231N |
| `e2e-admin@test.edu` | admin | unlimited | all |

---

## Test Suites

### Suite 1: Authentication & Authorization

#### TC-AUTH-001: University SSO Login
```
GIVEN   a student navigates to the Hopper login page
WHEN    they click "Login with University SSO"
AND     authenticate with their university credentials (Keycloak test realm)
THEN    they are redirected to the dashboard
AND     their name and email are displayed
AND     their credit balance is visible
AND     the JWT is stored in an HttpOnly cookie
```

#### TC-AUTH-002: Role-Based Dashboard Rendering
```
GIVEN   a student logs in
THEN    they see: Pod Management, Credit Balance, Usage History
AND     they do NOT see: Admin Panel, User Management, System Metrics

GIVEN   a TA logs in
THEN    they see: Pod Management, Credit Balance, Course Students, Usage Analytics
AND     they do NOT see: Admin Panel, System Metrics

GIVEN   an admin logs in
THEN    they see all dashboard sections including Admin Panel and System Metrics
```

#### TC-AUTH-003: Cross-Tenant Isolation
```
GIVEN   student-1 (CS229) is logged in
AND     student-3 (CS231N) has a running pod
WHEN    student-1 tries to access student-3's pod via direct URL (/pods/{student3-pod-id})
THEN    they receive a 403 Forbidden error page
AND     no pod details are leaked
```

#### TC-AUTH-004: Session Expiry
```
GIVEN   a student is logged in with a session
WHEN    the access token expires (after 5 minutes)
THEN    the token is silently refreshed via the refresh token
AND     the user remains logged in without interruption

WHEN    the refresh token also expires (after 1 hour)
THEN    the user is redirected to the login page
AND     a "Session expired, please log in again" message is shown
```

#### TC-AUTH-005: Unauthorized API Access
```
GIVEN   no authentication token
WHEN    any API endpoint is called
THEN    a 401 Unauthorized response is returned
AND     no data is leaked in the response body
```

---

### Suite 2: Pod Lifecycle (Core Workflow)

#### TC-POD-001: Create GPU Pod (Happy Path)
```
GIVEN   a student with 100 credits is logged in
WHEN    they click "New Pod"
AND     select GPU tier "Standard (RTX 4090)"
AND     select template "PyTorch 2.5"
AND     set session duration to "2 hours"
AND     click "Launch"
THEN    a loading state is shown with progress indicators
AND     the pod status transitions: Requested → Provisioning → Running
AND     the pod appears in the "Active Pods" list
AND     the SSH connection command is displayed
AND     the estimated credit cost is shown (20 credits for 2hr at 10/hr)
AND     the total time from click to "Running" is < 60 seconds
```

#### TC-POD-002: Create Pod with Insufficient Credits
```
GIVEN   student-2 with 0 credits is logged in
WHEN    they attempt to create a GPU pod
THEN    the "Launch" button is disabled
AND     a message says "Insufficient credits. Contact your instructor for allocation."
AND     no pod is created (verified via API)
```

#### TC-POD-003: Pod Metrics Streaming
```
GIVEN   a student has a running pod
WHEN    they view the pod detail page
THEN    GPU utilization gauge updates every 2-5 seconds
AND     VRAM usage bar shows current/total memory
AND     Temperature gauge shows current temperature with color coding
AND     Power draw shows current watts
AND     all metrics update without page refresh (SSE connection)
AND     if the SSE connection drops, it reconnects within 5 seconds
AND     during reconnection, a "Reconnecting..." indicator is shown
```

#### TC-POD-004: Pod Termination
```
GIVEN   a student has a running pod
WHEN    they click "Terminate"
THEN    a confirmation dialog appears with warning about data loss
WHEN    they confirm termination
THEN    the pod status transitions: Running → Stopping → Terminated
AND     the SSH connection is closed
AND     metrics streaming stops
AND     the pod moves to "Recent Sessions" history
AND     final credit charges are displayed
AND     the credit balance is updated
```

#### TC-POD-005: Pod Failure Handling
```
GIVEN   a student creates a pod
WHEN    the pod fails (e.g., image pull error)
THEN    the pod status shows "Failed" with an error message
AND     no credits are charged for the failed attempt
AND     the student can retry pod creation
AND     the failed pod appears in session history with "Failed" status
```

#### TC-POD-006: Maximum Concurrent Pods
```
GIVEN   a student has 3 running pods (the maximum)
WHEN    they try to create a 4th pod
THEN    an error message says "Maximum concurrent pods reached (3/3)"
AND     the "New Pod" button is disabled
AND     no pod is created
```

---

### Suite 3: Credit System

#### TC-CREDIT-001: Real-Time Credit Deduction
```
GIVEN   a student with 100 credits has a running pod (10 credits/hr)
WHEN    1 minute passes
THEN    the credit balance on the dashboard decreases by ~0.17 credits
AND     the balance update happens without page refresh
AND     the transaction appears in the usage history
```

#### TC-CREDIT-002: Low Balance Warning
```
GIVEN   a student with 15 credits has a running pod (10 credits/hr)
WHEN    the balance drops below 10% of their starting allocation (< 10 credits)
THEN    a yellow warning banner appears: "Low balance: X credits remaining"
AND     an estimated time remaining is shown
```

#### TC-CREDIT-003: Zero Balance Auto-Termination
```
GIVEN   a student with 5 credits has a running pod (10 credits/hr)
WHEN    the balance reaches 0
THEN    a 5-minute grace period starts with a countdown warning
AND     the warning says "Pod will be terminated in X:XX. Save your work."
AFTER   5 minutes
THEN    the pod is gracefully terminated (SIGTERM → SIGKILL after 30s)
AND     the final balance is 0 (not negative)
AND     the session is marked as "Expired - insufficient credits"
```

#### TC-CREDIT-004: Credit Allocation by Professor
```
GIVEN   a professor is logged in
WHEN    they navigate to Course Management → CS229
AND     click "Allocate Credits"
AND     enter 50 credits for all students
AND     confirm
THEN    each student in CS229 receives 50 additional credits
AND     the allocation appears in each student's transaction history
AND     the professor's allocation budget decreases accordingly
```

#### TC-CREDIT-005: Credit Balance Consistency Under Load
```
GIVEN   a student with 100 credits
WHEN    10 concurrent API requests each try to deduct 20 credits
THEN    exactly 5 succeed (100 / 20 = 5)
AND     5 fail with "Insufficient credits"
AND     the final balance is exactly 0
AND     there are exactly 5 debit entries in the ledger
AND     the sum of all ledger entries for this account is 0 (invariant)
```

---

### Suite 4: Web Terminal

#### TC-TERM-001: Web Terminal Connection
```
GIVEN   a student has a running pod
WHEN    they click "Open Terminal" on the pod detail page
THEN    an xterm.js terminal opens in the browser
AND     shows a bash prompt within 5 seconds
AND     the terminal is correctly sized to the browser viewport
AND     typing commands produces output (e.g., `nvidia-smi` shows GPU info)
```

#### TC-TERM-002: Terminal Resize
```
GIVEN   a student has an active terminal session
WHEN    they resize the browser window
THEN    the terminal adjusts to the new dimensions
AND     text reflow is handled correctly
AND     no characters are lost or duplicated
```

#### TC-TERM-003: Terminal Reconnection
```
GIVEN   a student has an active terminal session
WHEN    the WebSocket connection drops (network interruption)
THEN    a "Disconnected. Reconnecting..." message is shown
AND     the terminal automatically reconnects within 10 seconds
AND     the session state is preserved (command history, working directory)
```

#### TC-TERM-004: Copy and Paste
```
GIVEN   a student has an active terminal session
WHEN    they select text in the terminal and copy (Ctrl+C / Cmd+C)
THEN    the text is copied to the clipboard
WHEN    they paste (Ctrl+V / Cmd+V)
THEN    the text is pasted into the terminal
```

---

### Suite 5: Admin Workflows

#### TC-ADMIN-001: System Overview Dashboard
```
GIVEN   an admin is logged in
WHEN    they navigate to the Admin Panel
THEN    they see:
  - Total GPUs: count by type and status
  - Active Pods: count with GPU utilization heatmap
  - Active Users: count with breakdown by role
  - Credit Pool: total allocated vs consumed
  - Recent alerts and events
AND     all values update in real-time
```

#### TC-ADMIN-002: User Management
```
GIVEN   an admin searches for a student by email
WHEN    the student is found
THEN    the admin can view:
  - All active and historical sessions
  - Credit balance and transaction history
  - Course enrollments
AND     the admin can:
  - Adjust credit balance (with reason, logged to audit)
  - Terminate active sessions
  - Change user role
```

#### TC-ADMIN-003: Course Management
```
GIVEN   a professor creates a new course
WHEN    they fill in: course name, semester, GPU tier, per-student credit allocation
AND     add students by email list (CSV or manual)
THEN    the course is created
AND     all students receive their initial credit allocation
AND     the course appears in the professor's dashboard
AND     students see the course in their profile
```

#### TC-ADMIN-004: GPU Node Management
```
GIVEN   an admin navigates to Infrastructure → GPU Nodes
THEN    they see all GPU nodes with:
  - GPU type and count
  - Current utilization (from DCGM)
  - Running pods
  - Node health status
  - MIG configuration (if applicable)
AND     they can drain a node (evict pods gracefully before maintenance)
```

---

### Suite 6: Pod Templates

#### TC-TMPL-001: Launch Pod from Template
```
GIVEN   a student is on the pod creation page
WHEN    they select the "PyTorch 2.5 + CUDA 12.4" template
THEN    the base image, environment variables, and startup script are pre-filled
AND     the GPU requirements are pre-configured
AND     the student can override any template field
WHEN    they click "Launch"
THEN    the pod starts with the template configuration
AND     `python -c "import torch; print(torch.cuda.is_available())"` returns True
```

#### TC-TMPL-002: Professor Creates Course Template
```
GIVEN   a professor is logged in
WHEN    they navigate to Course Management → Templates → Create
AND     define a custom template (base image, packages, datasets)
AND     assign it to their course
THEN    students in that course see the template in their pod creation dropdown
AND     students in other courses do NOT see it
```

---

### Suite 7: Edge Cases & Error Handling

#### TC-EDGE-001: Network Interruption During Pod Creation
```
GIVEN   a student clicks "Launch" to create a pod
WHEN    their network connection drops during provisioning
AND     reconnects after 30 seconds
THEN    the dashboard shows the correct pod state (either Running or Failed)
AND     no duplicate pods were created
AND     credits are charged correctly (or not at all if pod failed)
```

#### TC-EDGE-002: Browser Tab Close During Active Session
```
GIVEN   a student has a running pod and closes the browser tab
THEN    the pod continues running (backend manages lifecycle)
WHEN    the student opens the dashboard again
THEN    the pod still appears as Running
AND     metrics resume streaming
AND     credits were continuously deducted during the absence
```

#### TC-EDGE-003: Session Timeout
```
GIVEN   a student creates a pod with a 2-hour duration
WHEN    2 hours elapse
THEN    15 minutes before expiry: a warning notification appears
THEN    5 minutes before expiry: a critical warning appears
THEN    at expiry: the pod is gracefully terminated
AND     the session is marked as "Expired"
AND     final charges are calculated
```

#### TC-EDGE-004: Simultaneous Dashboard Access
```
GIVEN   a student has the dashboard open in two browser tabs
WHEN    they create a pod in Tab A
THEN    Tab B shows the new pod within 5 seconds (via SSE)
AND     credit balance updates in both tabs simultaneously
AND     there are no duplicate entries or stale data
```

#### TC-EDGE-005: Pod Creation During Cluster Capacity Exhaustion
```
GIVEN   all GPU resources are allocated
WHEN    a student tries to create a pod
THEN    they see a message: "All GPUs are currently in use. Your request has been queued."
AND     the pod status shows "Queued" with an estimated wait time
AND     when a GPU becomes available, the pod is automatically provisioned
AND     the student is notified when the pod is ready
```

---

### Suite 8: Scavenger Queue (Preemptible Pods)

#### TC-SCAV-001: Scavenger Pod on Idle GPU
```
GIVEN   a student with 0 credits
AND     GPUs are idle (no paying workloads)
WHEN    they create a pod and select "Scavenger (free, preemptible)"
THEN    the pod launches on an idle GPU
AND     no credits are charged
AND     a warning banner says "This pod may be preempted at any time"
```

#### TC-SCAV-002: Scavenger Pod Preemption
```
GIVEN   a scavenger pod is running on a GPU
WHEN    a paying student requests that GPU tier
THEN    the scavenger pod receives a 30-second SIGTERM
AND     the scavenger student sees a notification: "Your pod is being preempted. Save your work."
AFTER   30 seconds
THEN    the scavenger pod is terminated
AND     the paying student's pod starts on the freed GPU
```

---

## Cross-Browser Testing Matrix

| Browser | Version | OS | Priority |
|---------|---------|-----|----------|
| Chrome/Chromium | Latest | macOS, Linux, Windows | P0 |
| Firefox | Latest | macOS, Linux | P1 |
| Safari/WebKit | Latest | macOS | P1 |
| Edge | Latest | Windows | P2 |

**Minimum requirements**: All Suite 1-4 tests pass on Chrome. Suite 1-4 also pass on Firefox and Safari.

---

## Accessibility Criteria

| Criterion | Standard | Test Method |
|-----------|----------|------------|
| Keyboard navigation | All interactive elements reachable via Tab | Playwright `page.keyboard` |
| Screen reader | ARIA labels on gauges, buttons, status indicators | axe-core audit |
| Color contrast | WCAG 2.1 AA (4.5:1 for text) | Playwright accessibility snapshot |
| Focus indicators | Visible focus ring on all interactive elements | Visual inspection |
| Error messages | Announced to screen readers via aria-live | axe-core audit |

---

## Performance Criteria (E2E)

| Metric | Threshold | Measurement |
|--------|-----------|-------------|
| Login to dashboard | < 3s | Playwright timing |
| Dashboard initial load (LCP) | < 2s | Playwright performance API |
| Pod creation to "Running" | < 60s | Playwright waitForSelector timeout |
| Metrics first paint | < 5s after pod Running | Playwright SSE observation |
| Terminal first prompt | < 5s after "Open Terminal" | Playwright WebSocket observation |
| Page navigation | < 500ms | Playwright timing |
| Credit balance update | < 2s after deduction | Playwright SSE observation |

---

## Playwright Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000,  // 2 min per test (pod creation can take time)
  retries: 1,        // Retry once on failure (infrastructure flakiness)
  workers: 2,        // Parallel workers (limited by staging GPU count)

  use: {
    baseURL: process.env.HOPPER_URL || 'http://localhost:3000',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],

  webServer: {
    command: 'docker compose -f docker-compose.test.yml up',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
```

---

## Test Execution Schedule

| Trigger | Suites | Environment | Duration |
|---------|--------|-------------|----------|
| Every commit | Suite 1-2 (mocked backend) | CI (GitHub Actions) | < 5 min |
| Every PR | Suite 1-6 (mock + Testcontainers) | CI | < 15 min |
| Nightly | All suites (1-8) | Staging (real GPUs) | < 45 min |
| Pre-release | All suites + cross-browser + accessibility | Staging | < 2 hours |
| Post-deployment | Suite 2, 3, 4 (smoke tests) | Production | < 10 min |
