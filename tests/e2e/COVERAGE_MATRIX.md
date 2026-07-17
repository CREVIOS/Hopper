# E2E Coverage Matrix

Aligned to `docs/E2E_TESTING.md` as of 2026-07-17.

Legend:

- `covered`: backed by a concrete Playwright spec in `tests/e2e/specs`
- `partial`: some user-visible path is covered, but the full acceptance criteria
  are not yet testable in the current app or mock harness
- `pending`: no meaningful automated E2E coverage yet
- `future`: explicitly out of scope for current implementation

| Test case | Status | Notes |
|---|---|---|
| `TC-AUTH-001` | `covered` | Password login, dashboard redirect, and HttpOnly auth cookies are asserted. |
| `TC-AUTH-002` | `partial` | Student/professor/admin nav gating is covered; the exact dashboard section mix still differs from the plan. |
| `TC-AUTH-003` | `covered` | Direct API access to another student's pod is denied; the UI resolves that denial to `VM not found`. |
| `TC-AUTH-004` | `partial` | Silent refresh and redirect-to-login are covered; no banner copy is currently implemented for expired sessions. |
| `TC-AUTH-005` | `covered` | Anonymous API requests are asserted to return `401`. |
| `TC-POD-001` | `partial` | Launch flow, plan/template selection, list update, and SSH details are covered; status transitions and duration-based pricing are not implemented in the app. |
| `TC-POD-002` | `covered` | Low-balance launch disablement and inline message are covered. |
| `TC-POD-003` | `partial` | Metrics tab and SSE-fed CPU/memory rendering are covered; reconnect indicator, temperature, and power draw are not implemented. |
| `TC-POD-004` | `partial` | Termination confirmation, redirect, and appearance in history are covered; billing-finalization details are not surfaced. |
| `TC-POD-005` | `partial` | Failed create requests surface an error; persisted failed-session history is not implemented. |
| `TC-POD-006` | `covered` | Fourth-pod rejection is covered. |
| `TC-CREDIT-001` | `partial` | Balance and ledger rendering are covered; live minute-by-minute deduction is not implemented. |
| `TC-CREDIT-002` | `pending` | No low-balance warning banner exists on the current credits/dashboard UI. |
| `TC-CREDIT-003` | `pending` | Grace-period auto-termination flow is not implemented in the current mock/app path. |
| `TC-CREDIT-004` | `covered` | Professor allocation to course students is covered. |
| `TC-CREDIT-005` | `pending` | This is better exercised as backend concurrency/invariant testing than UI E2E today. |
| `TC-TERM-001` | `covered` | Terminal websocket connection and command execution are covered. |
| `TC-TERM-002` | `partial` | Multiple terminal tabs are covered; viewport-resize assertions are not yet added. |
| `TC-TERM-003` | `pending` | Reconnect UX is implemented in the component but not yet simulated in Playwright. |
| `TC-TERM-004` | `pending` | Clipboard interaction is not yet automated. |
| `TC-ADMIN-001` | `partial` | Overview stats render; plan-specific GPU heatmap and live updates are not implemented. |
| `TC-ADMIN-002` | `covered` | User search, allocation, and role change are covered. |
| `TC-ADMIN-003` | `pending` | Course creation UI is not implemented in the current frontend. |
| `TC-ADMIN-004` | `partial` | Node inventory renders; drain/maintenance action is not implemented. |
| `TC-TMPL-001` | `partial` | Template selection and launch are covered; template-specific env/startup inspection is not implemented. |
| `TC-TMPL-002` | `pending` | Course template management UI is not implemented. |
| `TC-EDGE-001` | `pending` | Network interruption during provisioning is not simulated yet. |
| `TC-EDGE-002` | `pending` | Browser-close persistence is not automated. |
| `TC-EDGE-003` | `pending` | Session-duration expiry flow is not implemented. |
| `TC-EDGE-004` | `pending` | Multi-tab SSE sync is not implemented on the dashboard today. |
| `TC-EDGE-005` | `covered` | Capacity exhaustion queues the request and routes to `/pods/queue`. |
| `TC-SCAV-001` | `future` | Scavenger plans are explicitly out of the current catalogue. |
| `TC-SCAV-002` | `future` | Scavenger preemption is explicitly out of the current catalogue. |
| Cross-browser matrix | `partial` | Config can opt into Firefox/WebKit with `E2E_CROSS_BROWSER`, but the suite is not enforced there by default. |
| Accessibility criteria | `pending` | No dedicated keyboard or axe checks yet. |
| Performance criteria | `pending` | No explicit timing assertions yet. |
