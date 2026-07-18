# E2E Coverage Matrix

Aligned to `docs/E2E_TESTING.md` as of 2026-07-18.

Legend:

- `covered`: backed by a concrete Playwright spec in `tests/e2e/specs`
- `partial`: some user-visible path is covered, but the full acceptance criteria
  are not yet testable in the current app or mock harness
- `pending`: no meaningful automated E2E coverage yet
- `future`: explicitly out of scope for current implementation

| Test case | Status | Notes |
|---|---|---|
| `TC-AUTH-001` | `covered` | Password login, dashboard redirect, and HttpOnly auth cookies are asserted. |
| `TC-AUTH-002` | `partial` | Student/professor/admin nav gating is covered; the exact dashboard section mix still differs from the plan and TA-specific assertions are still absent. |
| `TC-AUTH-003` | `covered` | Direct API access to another student's pod is denied; the UI resolves that denial to `VM not found`. |
| `TC-AUTH-004` | `covered` | Silent refresh, redirect-to-login, and the session-expired banner copy are covered. |
| `TC-AUTH-005` | `covered` | Anonymous API requests are asserted to return `401`. |
| `TC-POD-001` | `partial` | Launch flow, plan/template selection, list update, and SSH details are covered; status transitions and duration-based pricing are not implemented in the app. |
| `TC-POD-002` | `covered` | Low-balance launch disablement and inline message are covered. |
| `TC-POD-003` | `partial` | Metrics tab and SSE-fed CPU/memory rendering are covered; reconnect indicator, temperature, and power draw are not implemented. |
| `TC-POD-004` | `partial` | Termination confirmation, redirect, and appearance in history are covered; billing-finalization details are not surfaced. |
| `TC-POD-005` | `partial` | Failed create requests surface an error; persisted failed-session history is not implemented. |
| `TC-POD-006` | `covered` | Fourth-pod rejection is covered. |
| `TC-CREDIT-001` | `partial` | Balance and ledger rendering are covered; live minute-by-minute deduction is not implemented. |
| `TC-CREDIT-002` | `covered` | A low-balance banner with remaining-credit copy and estimated runtime is covered on the dashboard. |
| `TC-CREDIT-003` | `pending` | Grace-period auto-termination flow is not implemented in the current mock/app path. |
| `TC-CREDIT-004` | `covered` | Professor allocation to course students is covered. |
| `TC-CREDIT-005` | `pending` | This is better exercised as backend concurrency/invariant testing than UI E2E today. |
| `TC-TERM-001` | `covered` | Terminal websocket connection and command execution are covered. |
| `TC-TERM-002` | `covered` | Terminal viewport resize is asserted directly in Playwright. |
| `TC-TERM-003` | `covered` | Reconnect status and successful recovery after a forced WebSocket drop are covered. |
| `TC-TERM-004` | `partial` | Paste input is automated against the live shell session; copy verification is still missing. |
| `TC-ADMIN-001` | `partial` | Overview stats render; plan-specific GPU heatmap and live updates are not implemented. |
| `TC-ADMIN-002` | `covered` | User search, allocation, and role change are covered. |
| `TC-ADMIN-003` | `pending` | Course creation UI is not implemented in the current frontend. |
| `TC-ADMIN-004` | `partial` | Node inventory renders; drain/maintenance action is not implemented. |
| `TC-TMPL-001` | `partial` | Template selection and launch are covered; template-specific env/startup inspection is not implemented. |
| `TC-TMPL-002` | `pending` | Course template management UI is not implemented. |
| `TC-EDGE-001` | `partial` | A failed in-flight launch is simulated and asserted not to create duplicate VMs, but a delayed reconnect with final-state recovery is still missing. |
| `TC-EDGE-002` | `partial` | Browser-close persistence and dashboard recovery are automated, but metrics resumption and continuous credit deduction are not asserted. |
| `TC-EDGE-003` | `pending` | Session-duration expiry flow is not implemented. |
| `TC-EDGE-004` | `partial` | A second tab picking up new pods and credit changes is automated via live polling, but no true SSE duplicate/staleness assertions exist. |
| `TC-EDGE-005` | `covered` | Capacity exhaustion queues the request and routes to `/pods/queue`. |
| `TC-SCAV-001` | `future` | Scavenger plans are explicitly out of the current catalogue. |
| `TC-SCAV-002` | `future` | Scavenger preemption is explicitly out of the current catalogue. |
| Cross-browser matrix | `partial` | Config can opt into Firefox/WebKit with `E2E_CROSS_BROWSER`, but the suite is not enforced there by default. |
| Accessibility criteria | `partial` | Keyboard reachability to a core launch action is asserted, but axe, color-contrast, and broader focus/error coverage are still missing. |
| Performance criteria | `partial` | Mock-environment timing assertions exist for login and primary navigation, but the rest of the documented thresholds are not enforced yet. |
