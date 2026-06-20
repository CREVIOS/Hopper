# SRS Addendum — Responses to Four-Eyed Raven Review

Status: Authoritative resolutions for the gaps flagged in the Four-Eyed Raven
SRS feature-gap review. Each section below resolves the open question or
under-specified requirement and is to be folded into the next revision of
`SRS Four-Eyed Raven.tex` (or `SRS Hopper Combined.tex`). Section numbers
below mirror the review.

---

## 2.2 Persistent workspace across sessions — **Resolved: Must-Have**

Open Question 4 in the SRS asked whether a persistent home directory should
survive across sessions. **Resolution: yes, mandatory.** Without it, multi-day
ML work (datasets, virtualenvs, checkpoints) is infeasible — US-HC-17 (resume
from previous session) becomes empty without backing storage.

### New functional requirement

> **FR-HC-28 — Persistent user workspace.** Every authenticated student
> account is associated with exactly one persistent ReadWriteOnce PVC.
> The PVC is created lazily on first session launch and mounted read-write
> at `/workspace` in every subsequent session for that user. The PVC is
> never deleted by the session lifecycle; only an explicit admin action
> (FR-HC-30) may delete it. Per-session ephemeral scratch storage remains
> separate and continues to be reclaimed at session end.

### New data-model entity

```
user_workspaces
  id              UUID, PK
  user_id         FK → users.id, UNIQUE
  pvc_name        VARCHAR(253), NOT NULL  -- K8s PVC object name
  storage_class   VARCHAR(63),  NOT NULL  -- e.g. "longhorn", "local-path"
  capacity_gb     INTEGER,      NOT NULL  -- requested PVC size
  used_gb         NUMERIC(10,2), NULLABLE -- last observed usage, refreshed by metrics consumer
  created_at      TIMESTAMP,    NOT NULL DEFAULT now()
  last_mounted_at TIMESTAMP,    NULLABLE
```

`users.id` gains an implicit one-to-one relation: `user_workspaces.user_id`
unique. Session provisioning (FR-HC-04) must look up or create the row and
declare the PVC as a required mount in the pod spec.

### Storage quotas

Each tier inherits a workspace quota from its plan:

| Plan  | Workspace capacity |
| ----- | ------------------ |
| small | 20 GiB             |
| large | 100 GiB            |

When `used_gb` reaches 95 % of `capacity_gb`, the orchestrator emits a
`workspace.quota.warning` NATS event; new uploads above 100 % are rejected
by the file-transfer endpoint (`/files/{pod_id}/upload`) with HTTP 413.

### Admin controls

> **FR-HC-30 — Workspace lifecycle controls.** Admins may resize a
> workspace (up only), reset its quota, or delete it entirely. A deletion
> is irreversible and recorded in the audit log with `action=workspace.delete`.

### UI contract

The file-transfer panel and pod detail view both surface `/workspace`
as the persistent root, distinct from the ephemeral `/root` home. The
SRS user-stories table is updated so US-HC-17 (resume from previous
session) cites FR-HC-28 as its backing requirement.

---

## 2.3 Session extension is under-specified — **Resolved**

FR-HC-27 (session extension) is amended with concrete limits:

> **FR-HC-27 (revised).** A running session MAY be extended by the user
> up to a maximum of **3 extension events per session**, each adding
> at most **+1 hour** to the session TTL, for a **cumulative cap of
> +3 hours** beyond the original TTL. Each extension is conditional on
> (a) the user holding sufficient credits to cover the extension window
> at the session's tier rate, and (b) the absolute wall-clock TTL
> `started_at + 8h` not having elapsed. Wall-clock cap overrides
> remaining credit balance — a session may never run longer than 8 h
> from start regardless of balance, so a single user cannot hold a
> high-demand GPU tier indefinitely.

> **TC-HC-27a.** Extension attempt #4 returns HTTP 409
> `extension_limit_reached`.

> **TC-HC-27b.** Extension after wall-clock 8 h returns HTTP 409
> `ttl_cap_reached`, even with credits remaining.

> **TC-HC-27c.** Queue priority: when a user with a high-demand-tier
> session extends, their next extension request is deprioritized so
> waiting students can be served first.

---

## 3.1 Rate limiting NFRs — **Defined**

Adds NFR-NF-008 through NFR-NF-013 with concrete thresholds per endpoint
class. These give TC-HC-25 (rate-limit test case) measurable assertions.

| ID         | Endpoint class                                    | Limit                 | Window | Scope     |
| ---------- | ------------------------------------------------- | --------------------- | ------ | --------- |
| NFR-NF-008 | Session launch (`POST /pods`)                     | 10 requests           | 1 min  | per user  |
| NFR-NF-009 | Session status poll (`GET /pods`, `GET /pods/{}`) | 60 requests           | 1 min  | per user  |
| NFR-NF-010 | Credit balance (`GET /credits/balance`)           | 60 requests           | 1 min  | per user  |
| NFR-NF-011 | Auth (`POST /auth/login`, `/auth/callback`)       | 30 requests           | 1 min  | per IP    |
| NFR-NF-012 | File upload (`POST /files/{}/upload`)             | 20 requests, 100 MB/s | 1 min  | per user  |
| NFR-NF-013 | All other authenticated endpoints                 | 120 requests          | 1 min  | per user  |

Exceeding any limit returns HTTP 429 with `Retry-After`. Limits are
already enforced by `slowapi`; this NFR documents the values applied.

---

## 3.2 Onboarding flow (US-HC-20) — **Deferred to v2**

US-HC-20 (guided onboarding) lacks a wireframe, acceptance criteria, and
test case. Rather than over-spec it for v1, **defer to v2** and update
the user-stories table to mark US-HC-20 with `target_release = v2`. In
v1, the login page documents the SSO-only registration path (see §4.1
below), which is sufficient for the closed-cohort student audience.

---

## 3.3 Session state machine — **Diagrammed**

`pod_sessions.state` transitions, who triggers each, and side-effects:

```
                +--------------------- (admin force-terminate) ---------------------+
                |                                                                    v
            +---+----+      +----------+      +---------+      +----------+      +------------+
( user ) -->| PENDING |---->| CREATING |----->| RUNNING |----->| STOPPING |----->| TERMINATED |
            +--------+      +----------+      +---------+      +----------+      +------------+
                                |                  ^  |  ^                              ^
                                |                  |  |  +---- (extend, retry) ---------+
                                |                  |  |
                                |                  |  +--- (wall-clock cap / TTL) -------+
                                |                  |                                      |
                                |                  +--- (user manual terminate) ---------+
                                v
                            +--------+
                            | FAILED |
                            +--------+
```

| Transition                 | Trigger                                  | Side effects                                                     |
| -------------------------- | ---------------------------------------- | ---------------------------------------------------------------- |
| `–` → `PENDING`            | `POST /pods` accepted, credit check ok   | Row inserted; orchestrator gRPC `CreatePod` queued               |
| `PENDING` → `CREATING`     | Orchestrator dequeues, applies K8s spec  | PVC bind, namespace label, secret materialization                |
| `CREATING` → `RUNNING`     | Pod `Ready` watch event                  | **Billing starts** (per-min ticker); SSH cert issued; node\_port allocated; metrics consumer subscribes |
| `CREATING` → `FAILED`      | Pod stuck `ImagePullBackOff` / crash > 60 s | Billing never starts; audit log `pod.create.failed`             |
| `RUNNING` → `STOPPING`     | User `DELETE /pods/{id}`, TTL hit, or admin terminate | **Billing stops** at this timestamp (final prorated charge); SSH cert revoked |
| `STOPPING` → `TERMINATED`  | K8s pod fully removed                    | Workspace PVC unmount only — never deleted; metrics flush        |
| `RUNNING` → `FAILED`       | Pod evicted (OOM, node drain)            | Billing stops; audit log `pod.evicted`; user notified            |
| any active → `TERMINATED`  | Admin force-terminate (FR-HC-19)         | Billing stops; audit log `pod.admin.force_terminate`             |

This belongs in Section 6.2 (Data Model) or 7 (Behavioural Specs) of the
SRS; final placement at the editor's discretion.

---

## 3.6 Audit log retention & export — **Defined**

Adds NFR-NF-014 and NFR-NF-015:

> **NFR-NF-014 — Audit retention.** Audit-log entries (FR-HC-21) are
> retained for a **minimum of 90 days**. The system MAY retain longer if
> storage permits but MUST NOT purge below the 90-day mark unless an
> admin explicitly truncates the table. A nightly housekeeping job
> (orchestrator, leader-elected) deletes entries with
> `created_at < now() − retention_days` where `retention_days`
> defaults to 90 and is configurable via `HOPPER_AUDIT_RETENTION_DAYS`.

> **NFR-NF-015 — Audit export.** Admins MAY export the audit log over
> a configurable date range as CSV or JSON via
> `GET /admin/audit/export?from=&to=&format=csv|json`. The endpoint is
> rate-limited per NFR-NF-013 and the action is itself recorded as an
> audit event (`audit.export`). Files larger than 50 MB are streamed.

(Implementation note: the existing `audit_logs` table already has the
`created_at` index, so retention pruning and range exports are
index-supported without schema changes.)

---

## 3.7 Active-session support path — **Added**

Adds FR-HC-29:

> **FR-HC-29 — Report Issue.** The active-session view exposes a
> "Report Issue" affordance that captures `session_id`,
> `timestamp` (server-side, on receipt), the authenticated `user_id`,
> and a free-text description (5–2000 chars) the user provides. The
> report is persisted in the `issue_reports` table (status defaults
> to `open`). Admin console lists open reports and allows resolution;
> resolution writes `resolved_at` and flips status to `resolved`.
> No SLA is committed in v1; the requirement is operational — it
> exists so reports land in a single triage queue instead of email.

---

## 4.1 No account registration or password recovery — **Documented**

There is no in-app sign-up flow because all accounts are pre-provisioned
through institutional SSO (Keycloak federated to the university IdP). The
login page now states this explicitly and points students at
`hopper-admin@cs.du.ac.bd` to be added if their account is missing.
Password recovery is delegated entirely to the institutional IdP — Hopper
does not store passwords and therefore cannot reset them. This is
documented on the sign-in page (see frontend `src/routes/login/+page.svelte`).

**SRS update:** add a single line under §3 (Constraints):

> **CON-AUTH-01.** Account creation and password recovery are out of
> scope for Hopper; both are delegated to the institutional identity
> provider (Keycloak federation). The product UI MUST surface this
> contract on the sign-in screen so users do not look for in-app
> sign-up or password-reset affordances.

---

## 4.2 Metrics view lacks historical context — **Resolved (UI)**

Implemented: dashboard now renders a per-user time-series chart
(`UsageTrend.svelte`) backed by `/usage/summary/me/series` which uses
TimescaleDB `time_bucket` over the existing `metrics_samples` hypertable.
Ranges supported: 1h, 6h, 24h, 7d. Metric tabs: CPU and memory. The
per-pod `PodUsage` view continues to surface pod-level trends.

---

## 4.3 File transfer guidance — **Resolved (UI + backend)**

Implemented: `PodFiles.svelte` now offers a directory browser keyed off
the new `GET /files/{pod_id}/list?path=` endpoint. Upload/download
inputs surface inline validation (absolute path, no double-slash, no
control chars) and pre-fill from the browser. The persistent workspace
is documented inline as `/workspace`; the SSH/ephemeral home is `/root`.

---

## 4.4 SSH connection — **Partially resolved; one ops dependency**

Code-side fixes shipped:
1. Backend now sets `ssh_port` / `vscode_port` / `ssh_password` to `null`
   in API responses for any non-running pod, so the UI no longer renders
   stale connection strings (the original 32066 timeout was a NodePort
   from a *terminated* session that had been reassigned).
2. Frontend pod detail page also gates SSH command display on
   `state === 'running'`.
3. VS Code proxy now redirects unauthenticated HTML navigations to
   `/login` (with `return_to`) instead of returning a JSON 401, which
   was rendering as a stuck "loading screen" in the browser.

**Remaining (ops):** External reachability of NodePorts 30000–32767
requires an Azure NSG rule (per README §7). Verify with `az network
nsg rule list` on the cluster's NSG; if absent, apply the documented
allow rule. Until that's open, external SSH will time out regardless of
code state.

---

## 4.5 Admin user menu unresponsive — **Resolved (frontend)**

Root cause: `dropdown-menu-item.svelte` forwarded `onclick` to a
`bits-ui` v2 Menu.Item, which intercepts pointer events and dispatches
selection via `onSelect` — the native `onclick` either missed or raced
the portal close. Fix: forward our public `onclick` prop to `onSelect`
on the underlying primitive, so all menu items (admin console, SSH
keys, sign-out, theme toggles, pod actions) work consistently.
