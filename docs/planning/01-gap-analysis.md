# Hopper — Gap Analysis: Student Side & Admin Side

> Verified against `main` on 2026-07-10 by a full code-level audit (four parallel
> read-only passes + manual confirmation). Every claim carries `file:line`
> evidence. Cross-referenced against `docs/SRS Hopper Combined.tex`,
> `docs/SRS_ADDENDUM.md`, and `docs/TASKS.md`.
>
> Legend: **DONE** (wired end-to-end) · **PARTIAL** (pieces missing) ·
> **STUB** (exists, does nothing) · **MISSING** (no code) · **BUG** (implemented but incorrect).

---

## 0. Executive Summary

The core happy-path is solid: a funded student can sign up, verify email, log in,
launch a CPU VM, use an in-browser terminal + VS Code + file transfer, watch live
and historical metrics, and see a real double-entry credit ledger drain until the
VM is auto-killed. Admins can manage users/roles, approve teachers, grant credits,
and view nodes/stats/active-VMs/audit logs.

What's missing clusters into four themes:

1. **Durability** — VMs are *ephemeral*. No persistent workspace (the single
   biggest gap), no stop/resume, SSH keys never reach the VM.
2. **Lifecycle & feedback** — no session TTL/extension, no notifications, and a
   **confirmed bug** leaves killed VMs stuck showing "running" with no explanation.
3. **Admin authority** — admins can *see* everything but can't *act* on other
   users' VMs (no force-terminate), can't triage issues (no UI), can't manage
   plans/pricing/quotas/courses.
4. **SRS drift** — GPU/MIG/gVisor/Teleport were dropped; roles went 6→3; signup
   was built despite being scoped out; multi-cluster was explicitly out-of-scope.

---

## 1. STUDENT SIDE

### 1.1 What's DONE (complete, end-to-end)

| Area | Evidence |
|---|---|
| Auth: signup, email verify, resend, login (direct grant + OIDC/PKCE), forgot/reset, refresh, logout | `routers/auth.py:224,266,291,308,325,352,120/373,473,540` |
| Dashboard (balance, active VMs, avg CPU/mem, usage trend, recent pods & transactions) | `routes/dashboard/+page.server.ts:16-30`, `+page.svelte:99-139` |
| Pod lifecycle: list / create (plan+template) / detail / terminate | `routers/pods.py:75,90,172,191`; UI `routes/pods/+page.svelte`, `pods/[id]/+page.svelte` |
| In-browser terminal (xterm.js ↔ asyncssh over port-forward) | `pods.py:507-698`; `lib/components/Terminal.svelte` |
| In-browser VS Code (HTTP+WS reverse proxy, ownership-gated) | `pods.py:277-506`; ingress `03-ingress.yaml:127-153` |
| File browser: list / navigate / upload / download (SCP over port-forward, path guards) | `routers/files.py:33,79,146,185`; `lib/components/PodFiles.svelte` |
| SSH key **management** CRUD (validation, fingerprint dedup, advisory lock, 10-key cap) | `routers/ssh_keys.py:32,56,117` |
| Credits: balance + full ledger history (real double-entry) | `routers/credits.py:21,32`; `services/credit_service.py` |
| Usage: live SSE gauges + historical charts (TimescaleDB `time_bucket`) | `pods.py:221`; `routers/usage.py:22,93,161`; `UsageTrend.svelte`, `PodUsage.svelte` |
| Issue reporting (create) | `routers/issues.py:33`; `pods/[id]/+page.svelte:599-633` |

### 1.2 What's LEFT (ranked by impact)

**1. Persistent workspace — MISSING (highest impact).** SRS `FR-HC-28`
(Must-Have, `SRS_ADDENDUM.md:11-71`) requires one persistent PVC per student
mounted at `/workspace`. The K8s layer fully supports it (`k8s/pod.go:114,206,285`
create PVC `ws-<pod>` when `DiskGiB>0`), but the value is dropped at **two layers**:
the gateway never sends `disk` (`pods.py:148-155` → defaults `""`) and the gRPC
handler never reads `req.Disk` (`pod_service.go:104-112`, no `DiskGiB`/`StorageClass`).
Net: `DiskGiB` is always 0 → no PVC → `/workspace` is the ephemeral image dir →
**all student data is lost on restart/terminate.** The UI even advertises disk
sizes it never provisions (`types/index.ts:15-35`). No `user_workspaces`
table/model/migration exists. *This defeats the platform's core purpose (multi-day ML work).*

**2. SSH public keys never injected into VMs — MISSING/misleading.** Key CRUD is
complete, but no `authorized_keys` injection exists anywhere (`pod.go:234-246`
sets only a root password; proto `CreatePodRequest` has no key field). The UI
explicitly promises "keys registered here are pushed to every VM… passwordless SSH"
(`settings/ssh-keys/+page.svelte:148`). That path never works — students must use
the generated root password.

**3. Credit-exhaustion feedback + stale-state — BUG + MISSING.** On exhaustion the
orchestrator kills the VM, but the gateway's DB-terminate handler looks up
`PodSession.id == pod_id` (`billing_consumer.py:115`) where `pod_id` from the
billing event is the manager id `vm-<unixNano>` (`pod_service.go:66,78,140`), **not
the session UUID PK** → lookup misses → **DB session stays "running"** with dead
connections and no explanation. There is also no `reason`/`message` field on the
session and no user notification. (Self-heals only after an orchestrator reconcile
relabels ids to the UUID — `watcher.go:42,50`.)

**4. Notifications / credit-low alerts — MISSING on main.** No warning before a VM
is auto-killed. A near-complete implementation (threshold bands 60/30/10/5 min,
notification model + bell UI + tests) sits on `origin/feature/notifications-credit-alerts`
but is **unmerged and blocked by a migration-number collision** (`011_notifications`
vs `011_pending_teacher` on main). SRS `FR-HC-18`, `TASKS.md:541-544` (F3.3).

**5. Session TTL + extension — MISSING (dormant stub).** `pod_sessions.expires_at`
exists (`models/session.py:24`) but is never set or enforced; no `/extend` endpoint.
SRS `FR-HC-27` (`SRS_ADDENDUM.md:74-98`: max 3× +1h, 8h wall-clock cap) unimplemented.

**6. Per-pod historical usage often empty — BUG (same root cause as #3).**
`metrics_samples.pod_id` is stored as `vm-<nano>` for fresh pods while the per-pod
chart queries by UUID (`usage.py:22`, `PodUsage.svelte:20`) → "No usage data yet".

**7. Stop / pause / resume (keep data) — MISSING.** Terminate-only
(proto has only `CreatePod`/`TerminatePod`); every stop destroys the pod. Blocked on #1.

**8. File delete / rename / mkdir — MISSING.** `files.py` has only list/upload/download.

**9. Profile editing + account deletion — MISSING.** `/me` is read-only
(`auth.py:520`); `university_id` column exists but no API reads/writes it; no avatar; no delete.

**10. Idle auto-shutdown — MISSING.** Only the 10-min *terminal-tab* idle close
exists (`pods.py:584`); no CPU/activity-based VM shutdown. Only credit exhaustion stops a VM.

**11. `PUT /settings/vscode` — STUB.** Accept-and-discard (`settings.py:9-22`), no UI, blocked on #1.

**12. Cleanup / cosmetic:** dead `routers/terminal.py` (orphaned kubectl-exec
terminal), duplicate 503 block (`pods.py:311-329`), misnamed `GpuMetrics.svelte`
(CPU/mem only, no GPU), hardcoded always-green "Cluster online" (`Sidebar.svelte:184-195`),
hardcoded VS Code "Preview :5000" (`pods/[id]/+page.svelte:570-576`),
`nodeIp` defaults to `127.0.0.1` when `NODE_IP` unset.

---

## 2. ADMIN & TEACHER SIDE

### 2.1 What's DONE

| Area | Evidence |
|---|---|
| Users list + role change (blocks self-demote, blocks removing last admin, Keycloak-first + force-logout + audit) | `routers/admin.py:32,227-294` |
| Teacher-request approve/reject (→ professor in Keycloak+DB, force-logout) | `admin.py:58,79,114` |
| Credit allocation: admin grant (system→user) + professor→student (advisory-locked, 402 on insufficient) | `routers/credits.py:111-154`; `credit_service.py:76,129` |
| Node capacity view (gRPC `ListNodes`, real capacity/allocatable/pod counts) | `admin.py:145`; `pod_service.go:253` |
| Platform stats (total users / active VMs / total created) | `admin.py:173` |
| Active VMs list (all users, joined with owner) — **read-only** | `admin.py:196` |
| Audit log viewer (auto-capture middleware + explicit rows) — limit/offset only | `admin.py:297`; `middleware/audit.py` |
| Teacher console: student list + allocate dialog bounded by own balance | `routes/teacher/+page.svelte` |
| Issue **backend** (admin list + resolve) | `routers/issues.py:67,82` |

### 2.2 What's LEFT (ranked by impact)

**1. Admin force-terminate any VM — MISSING.** SRS `FR-HC-20` / `US-HC-12`.
`DELETE /pods/{id}` is strictly owner-scoped (`pods.py:204`), no admin override.
The active-VMs view is read-only. **Admins cannot kill a runaway/abusive VM.**

**2. Issue-resolution admin console — MISSING frontend.** Backend is done
(`issues.py:67-97`) but the admin page has no Issues tab and nothing fetches
`/issues/admin`. Issues can be *filed* and never *triaged*. Also one-directional:
no reply/thread field, so students never see a response. SRS `FR-HC-29`.

**3. Courses management — STUB.** `GET /admin/courses` returns `[]`
(`admin.py:134-142`); no course model, migration, or UI. Blocks all course-scoped
features (rosters, per-course credit pools, bulk allocation). SRS `FR-QUOTA-002`, `TASKS.md:531`.

**4. Quotas (storage + resource) — MISSING.** No quota model/endpoint/enforcement.
SRS `FR-HC-23`, `FR-HC-30` (workspace resize/reset/delete), `FR-QUOTA-001/002`.

**5. Admin control of plans / pricing / images — MISSING.** Hardcoded in **two
places** (`schemas/pod.py:25-41` + orchestrator `billing/types.go:8-11`); any price
change needs a code edit in two services. No admin CRUD.

**6. VM request + approval workflow — MISSING.** SRS `FR-REQ-001/002`, `UC-BM-01/02`.
VMs are provisioned on demand with no admin gate/queue.

**7. Audit export + filtering + retention — MISSING.** `NFR-NF-015`
(`GET /admin/audit/export?…format=csv|json`) and `FR-AUDIT-001` filtering absent;
endpoint is limit/offset only. `NFR-NF-014` (90-day retention housekeeping) not implemented.

**8. Admin inspect other users' VM detail/metrics — MISSING.** Ownership-locked
(`pods.py:185,240`); active-VMs rows show only plan/state/owner, no drill-down.

**9. Professor console not course-scoped — PARTIAL.** `/credits/students` returns
*every* student platform-wide (`credits.py:100`), not a roster; no per-course
allocation; no view of students' pods/usage; no reports/exports. `TASKS.md:535` (F3.2).

**10. `ta` role + dept/university admin tiers — MISSING.** SRS specifies a 6-tier
role model (`SRS Hopper Combined.tex:376-401`); shipped model is 3 roles
(admin/professor/student). TA dashboard + assign-TA features depend on the missing role.

**11. Admin-configurable expiration/lifecycle policies + system config — MISSING.**
SRS `FR-LIFE-002`, `TASKS.md:499`. No admin settings UI at all.

**12. New users start at 0 credits — onboarding gap.** Signup creates an account
but never grants credits (`auth.py:255`), and pod-create hard-blocks on balance
(`pods.py:107`). A fresh student is stuck until an admin/teacher funds them. No
default-grant, bulk-grant, or periodic-allowance mechanism.

**13. Impersonation — MISSING** (explicitly checked; no code).

**Minor:** professor sees a dead "Admin console" menu link that bounces them
(`UserMenu.svelte:56-59` vs `admin/+page.server.ts:12-14`); admin actions are
**double-logged** (explicit row + middleware row); unused `GET /credits/teachers`
endpoint (`credits.py:89`).

---

## 3. Cross-cutting: SRS-vs-Reality Divergences

| SRS / Addendum said | Reality on `main` |
|---|---|
| GPU compute (MIG, time-slicing) is the whole point | **GPU entirely dropped** — migration `003_gpu_to_vm_plans` moved to CPU VMs; no GPU code, plans, or metrics anywhere. `GpuMetrics.svelte` shows CPU/mem only. |
| gVisor (runsc) syscall isolation (`FR-HC-09`, `NFR-HC-7`) | Not implemented — standard runtime; only an Ansible TODO. |
| Teleport SSH gateway + ephemeral certs (`FR-HC-12/13`) | Not implemented — plain sshd on NodePorts + root password. |
| No in-app signup; SSO-only; no password reset (`CON-AUTH-01`, `SRS_ADDENDUM.md:208`) | **Contradicted** — full self-service signup + email verification + password reset shipped later. |
| 6-tier role hierarchy | Down-scoped to 3 roles. |
| Multi-cluster federation **out of scope** (`SRS…:294`) | Now being planned (this initiative) — a deliberate v2 expansion. |
| Calico GlobalNetworkPolicy | Live policies are **Cilium**. |
| Billing charges final partial minute (`StopAndProrate`) | Implemented but **never called** — last partial minute unbilled. |

---

## 4. Confirmed Bugs (not just missing features)

1. **`pod_id` key mismatch** (`pod_service.go:66,78` vs `billing_consumer.py:115`,
   `usage.py:22`): fresh pods use manager id `vm-<nano>` while DB/queries use the
   session UUID → (a) killed VMs stay "running" in the DB, (b) per-pod usage charts
   empty until an orchestrator reconcile. **CONFIRMED.**
2. **Unit suite red on `main`**: `tests/unit/routers/test_admin.py:8` imports
   `_require_admin_only`, removed by the RBAC-tightening commit (a6a9c48) →
   ImportError at collection → the admin unit module fails to collect. **CONFIRMED.**

---

## 5. In-flight branches (relevant to this work)

- **`origin/feature/notifications-credit-alerts`** — student notifications +
  credit-low alerts, ~90% built with tests. Blocked by migration `011` collision.
- **`origin/security/hopper-audit-remediation`** — k8s hardening, `/usage` authz
  test, pod-ownership hardening, orchestrator changes. (See security findings doc.)

*Neither is merged; both should be reconciled before net-new work in the same files.*
