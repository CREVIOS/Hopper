# Student-Side Implementation Plan

> **For agentic workers:** implement task-by-task, TDD where the harness allows.
> Steps use checkbox (`- [ ]`) syntax. This plan is executed in-session by the author,
> so steps state approach + exact files + interfaces + test cases rather than transcribing
> every final line; real code is written at execution against these decisions.

**Goal:** Make student VMs durable and honest — land credit-low notifications, fix the
credit-exhaustion stale-state bug, inject registered SSH keys, and add a persistent
per-user `/workspace`.

**Scope (approved):** (1) land the notifications branch, (2) fix the pod-id stale-state
bug, (3) SSH-key injection, (4) persistent workspace. Student-facing security fixes
(H-2, H-3) are documented in `02-security-findings.md` but out of scope for this pass.

## Status (updated 2026-07-11, branch `feat/student-side-durability`)

| Task | Status | Commit / note |
|---|---|---|
| 0. Green baseline (admin test) | ✅ DONE | `test: repair admin RBAC unit test` |
| 2. Stale-state bug + /usage IDOR | ✅ DONE | `fix(billing,usage): …` — see deviation below |
| 3. SSH-key injection | ✅ DONE | `feat(vm): inject registered SSH public keys` |
| 4. Persistent workspace (FR-HC-28) | ✅ DONE | `feat(vm): persistent per-user /workspace` (migration **013**) |
| 1. Land notifications branch | ⛔ REMAINING | see the renumber note in Task 1 below |

**Verified here:** `go build`/`vet`/`test`, `pytest` (changed areas +7 tests, 0 new
failures), `ruff`, linear Alembic chain (…012→013), app import. **Needs a live cluster
(no cluster in this env):** key-based SSH into a VM, and `/workspace` persistence across
restart/re-launch.

**Task 2 deviation (important):** the plan proposed making the API UUID the canonical
manager id in the orchestrator. That was **rejected during implementation** because
`tx_id = <podId>:<seq>` and `seq` resets on orchestrator restart — a *stable* id would
collide post-restart tx_ids and **under-bill after a restart**. The shipped fix is
**gateway-only**: `billing_consumer` and `/usage` now match a pod by `id` OR `pod_name`,
robust to both the fresh `vm-<nano>` and post-reconcile UUID, with no billing-path change.
It also closed the `/usage` IDOR (security M-3) since the fix must load the session anyway.

**Task 1 renumber (important):** Task 4 took migration **013**, so when landing the
notifications branch its `011_notifications` must be renumbered to **`014`**
(`down_revision="013"`), not 013 as originally written below. Also note `billing_consumer.py`
and `pods.py` now carry my Task 2/3/4 changes, so the merge is a 3-way in those files.

**Tech Stack:** Go orchestrator (gRPC), FastAPI gateway (Python 3.12, poetry), SvelteKit
frontend, Alembic migrations, protobuf via `scripts/generate-proto.sh` (protoc fallback —
`buf` absent), Postgres/TimescaleDB.

## Global Constraints

- **Branch first:** all work on `feat/student-side-durability` off `main` (never commit to `main`).
- **Immutability / small files / error handling** per repo coding-style rules.
- **Commit format:** `<type>: <desc>`; one commit per task (attribution disabled globally).
- **Verification limits:** no live k3s cluster in this environment (it's remote on Azure).
  Verify via `go build`/`go vet`/`go test`, `pytest` (unit; integration needs Docker),
  frontend `npm run check`/`build`, and Alembic `upgrade head` offline. Live VM launch,
  actual SSH-with-key, and PVC persistence must be verified on the cluster post-deploy —
  each such item is flagged **[cluster-verify]**.
- **Migration numbering is linear** (`00N_*` with `revision`/`down_revision` string ids).
  Current head chain: `010 → 011_pending_teacher → 012_email_codes`.

---

## Task 0: Green baseline — fix the red admin unit test

**Files:** Modify `tests/unit/routers/test_admin.py` (currently imports removed `_require_admin_only`).

**Why:** `test_admin.py:8` imports `_require_admin_only` and `:30` asserts professors are
allowed — both removed by the RBAC-tightening commit (a6a9c48). The module fails at
collection (ImportError), so the unit suite is red. TDD needs a green baseline.

- [ ] Read `admin.py` current guard (`_require_admin`, admin-only) and `test_admin.py`.
- [ ] Update the test to import `_require_admin` and assert: admin → allowed; professor & student → `HTTPException(403)`. Remove the stale `_require_admin_only` symbol + the allows-professor assertion.
- [ ] Run `poetry run pytest tests/unit/routers/test_admin.py -q` → PASS (collection fixed).
- [ ] Commit: `test: repair admin RBAC unit test after admin-only tightening`.

---

## Task 1: Land the notifications + credit-alert branch

**Source:** `origin/feature/notifications-credit-alerts` (single commit `9856e39`) — adds
`routers/notifications.py`, `services/{credit_alerts,notification_service}.py`,
`models/notification.py`, `schemas/notification.py`, `alembic/versions/011_notifications.py`,
frontend `NotificationBell.svelte` + `stores/notifications.ts` + types, and modifies
`main.py`, `credits.py`, `pods.py`, `billing_consumer.py`, `credit_service.py`.

**Central conflict:** the branch's `011_notifications` (`revision="011", down_revision="010"`)
collides with main's `011_pending_teacher`. Must be renumbered to `013` after `012_email_codes`.

**Files:** Merge brings the above; Modify `alembic/versions/013_notifications.py` (renamed),
reconcile `services/billing_consumer.py` (branch superset vs main's ResourceClosedError fix).

- [ ] Merge into the feature branch: `git merge --no-ff origin/feature/notifications-credit-alerts` (expect conflicts in `billing_consumer.py`, migration dir, maybe `pods.py`/`main.py`).
- [ ] Resolve migration collision: rename the branch migration file to `013_notifications.py`, set `revision="013"`, `down_revision="012"`. Confirm `alembic history` is linear with one head.
- [ ] Reconcile `billing_consumer.py`: keep main's idempotent/ResourceClosedError-safe deduct path AND the branch's notification-on-exhaustion + `publish_billing_exhausted`. Ensure the exhaustion handler still marks the DB session terminated (its `PodSession.id == pod_id` lookup is fixed by Task 2).
- [ ] Reconcile `main.py`: register `notifications.router` and start the credit-alert loop (per branch), keeping main's existing router/consumer startup.
- [ ] Frontend: ensure `NotificationBell.svelte` is mounted in the layout and `stores/notifications.ts` polls the `/notifications` endpoints.
- [ ] Tests: run the branch's `tests/test_credit_alerts.py` + `tests/test_notification_service.py` (adapt import paths to the repo-root `tests/` layout if needed). `poetry run pytest -q` green.
- [ ] `poetry run alembic upgrade head` offline (SQLite/URL) to confirm the chain applies. **[cluster-verify]** real notification delivery on credit drain.
- [ ] Frontend `npm run check` green.
- [ ] Commit: `feat(notifications): land credit-low alerts + notification bell (migration 013)`.

---

## Task 2: Fix the pod-id key mismatch (stale state + empty usage)

**Root cause:** `grpc/pod_service.go:66,78` registers the in-memory pod under
`ID = "vm-<unixNano>"` (the K8s name) while the DB PK / labels / gateway use the API UUID
(`req.PodId`). Billing (`ticker.go` → `billing.deducted/exhausted`) and metrics carry that
`vm-<nano>` id, so `billing_consumer._handle_billing_exhausted` (`PodSession.id == pod_id`)
and `usage.py` (per-pod query by UUID) miss for fresh pods. It self-heals only after
`watcher.Reconcile` relabels the manager id to the UUID — proving UUID is the intended id.

**Fix:** make the API UUID the canonical manager id at create time, keeping the K8s object
name `vm-<nano>` as `PodName`. This aligns create with reconcile (removing a latent
id-changes-across-reconcile bug too).

**Files:** Modify `services/orchestrator/internal/grpc/pod_service.go` (Create: `ID: apiPodID`,
keep `PodName: podName`), verify `internal/billing/ticker.go`, `internal/events/metrics_publisher.go`
(payload `pod_id` = `p.ID`), `internal/k8s/watcher.go` (reconcile id already = UUID label),
and the **terminate path** (`TerminatePod` must resolve id→`PodName` for the K8s delete, not
use id as the K8s name). Tests: `internal/grpc/*_test.go`, gateway `tests/*` for exhaustion.

- [ ] Read the full id flow: `pod_service.go` Create + Terminate, `manager.go` (keying),
  `ticker.go` (Start uses `p.ID`), `metrics_publisher.go` (subject uses `PodName`, payload id),
  `watcher.go` Reconcile, and `pods.py` DELETE → `orchestrator_client.terminate_pod(<which id?>)`.
  Confirm terminate resolves via `manager.Get(id).PodName` (not id-as-k8s-name).
- [ ] **Failing test (Go):** a table test asserting that after `CreatePod(req.PodId="uuid-123")`,
  the manager holds the pod under key `"uuid-123"` and `PodName` starts with `"vm-"`, and the
  billing tick event `PodID == "uuid-123"`.
- [ ] Implement: set `ID: apiPodID` in `podManager.Create` (fallback to `podName` when
  `req.PodId==""`); keep `PodName: podName`. Ensure billing `Start(p.ID,...)` and metrics
  payload use `p.ID`. Adjust Terminate to look up `PodName` via the manager if it doesn't already.
- [ ] Run `go test ./... && go vet ./...` in `services/orchestrator` → PASS.
- [ ] **Gateway test:** assert `_handle_billing_exhausted` with `pod_id=<uuid>` flips the
  matching `PodSession.state → "terminated"` (regression for the stale-state bug).
- [ ] `poetry run pytest -q` → PASS.
- [ ] Commit: `fix(orchestrator): use API UUID as canonical pod id so exhaustion + usage resolve`.
- [ ] **[cluster-verify]** launch a VM, exhaust credits, confirm the DB session flips to
  terminated and the UI reflects it; per-pod usage chart populates for a fresh pod.

---

## Task 3: SSH-key injection (make the existing key CRUD real)

**Approach (no image rebuild):** the orchestrator already sets the container command to run
`chpasswd` then `supervisord` and injects `ROOT_PASSWORD` env. Add an `AUTHORIZED_KEYS` env
(newline-joined public keys — not secret) and extend the command to write
`/root/.ssh/authorized_keys` (mode 600, dir 700) before starting supervisord. The gateway
fetches the launching user's keys from `ssh_keys` and passes them via a new proto field.

**Files:**
- `proto/hopper/pod/v1/pod.proto`: add `repeated string authorized_keys = 9;` to `CreatePodRequest`; regenerate stubs (`scripts/generate-proto.sh`).
- `services/api-gateway/app/routers/pods.py`: on create, `select SshKey.public_key where user_id=…`, pass `authorized_keys=[…]`.
- `services/api-gateway/app/services/orchestrator_client.py`: `create_pod(..., authorized_keys: list[str] = [])`.
- `services/orchestrator/internal/grpc/pod_service.go` + `internal/k8s/pod.go`: thread keys into `CreatePodOpts`; add env + extend the container command to materialize `authorized_keys`.
- Frontend copy already correct (`settings/ssh-keys/+page.svelte` promises this) — no change beyond verifying it renders once real.

- [ ] Read `pod.go` container `command`/`args` + env construction (the chpasswd+supervisord line) and `ssh_keys` model.
- [ ] Proto: add field 9; run `scripts/generate-proto.sh`; confirm Python (`app/proto/…/pod_pb2.py`) + Go (`api/proto/…`) stubs regenerate and compile.
- [ ] **Go test:** `CreatePodOpts.AuthorizedKeys=["ssh-ed25519 AAAA… a@b"]` → the rendered
  container command contains a heredoc/echo writing that key to `/root/.ssh/authorized_keys`
  with `chmod 600`, and env `AUTHORIZED_KEYS` is set. Keys are shell-safe (write via a quoted
  heredoc, not interpolated into `sh -c`).
- [ ] Implement gateway (fetch keys, pass through) + orchestrator (env + command). Skip the
  authorized_keys write when the list is empty (keeps password-only VMs working).
- [ ] `go test ./... && go vet ./...`; `poetry run pytest -q` (add a gateway test asserting
  `create_pod` is called with the user's keys) → PASS.
- [ ] Frontend `npm run check`.
- [ ] Commit: `feat(vm): inject registered SSH public keys into launched VMs`.
- [ ] **[cluster-verify]** add a key, launch a VM, `ssh -i` with that key succeeds passwordlessly.

---

## Task 4: Persistent per-user workspace (FR-HC-28)

**Semantics (from `SRS_ADDENDUM.md:11-71`):** exactly one persistent **RWO** PVC per user,
created lazily on first launch, mounted **read-write at `/workspace`** in every session,
**never deleted** by the session lifecycle (only an explicit admin action may delete it —
FR-HC-30, out of scope here). Distinct from the existing per-pod `ws-<pod>` PVC (which is
pod-scoped and GC'd) — this is user-scoped and durable.

**Design:**
- New table `user_workspaces` (per addendum): `id, user_id UNIQUE, pvc_name, storage_class,
  capacity_gb, used_gb NULLABLE, created_at, last_mounted_at NULLABLE`.
- Gateway: on create, `get-or-create` the user's workspace row (`pvc_name = f"ws-user-{user_id}"`,
  `capacity_gb` from plan: small 20, large 100 — map current small/medium/large), pass
  `workspace_pvc_name` + `workspace_capacity_gb` + `storage_class` via proto.
- Orchestrator: **idempotently ensure the PVC exists** (Get→Create if missing) with NO
  owner-reference to the pod (so it survives pod deletion); mount RWO at `/workspace`.
  `TerminatePod`/exhaustion/watcher deletion must **not** delete this PVC (only per-pod
  resources). On single-node k3s, RWO + ≤3 concurrent same-user pods co-scheduled on one node is fine.

**Files:**
- `services/api-gateway/alembic/versions/014_user_workspaces.py` (after 013).
- `services/api-gateway/app/models/user_workspace.py` + register in `models/__init__.py`.
- `services/api-gateway/app/services/workspace_service.py`: `get_or_create_workspace(db, user_id, plan)`.
- `proto/…/pod.proto`: `string workspace_pvc_name = 10; int32 workspace_capacity_gb = 11; string storage_class = 12;` (regen).
- `services/api-gateway/app/routers/pods.py` (create): call workspace service, pass fields.
- `services/orchestrator/internal/k8s/pod.go`: ensure-PVC (idempotent) + RW mount at `/workspace`; guard deletes to exclude the user PVC.
- `services/orchestrator/internal/grpc/pod_service.go`: thread fields into `CreatePodOpts`.
- Frontend: `PodFiles.svelte` copy ("ephemeral… roadmap") → "persistent `/workspace`"; upload help already references `/workspace`.

- [ ] Read `pod.go` existing PVC block (`ws-<pod>`, gated on `DiskGiB>0`, `:113-136,205-217,284-292`) and all delete paths (`TerminatePod`, exhaustion, `watcher` external-delete) to ensure the user PVC is excluded from cleanup.
- [ ] **Migration + model:** create `014_user_workspaces.py` (`down_revision="013"`) + `UserWorkspace` model; `poetry run alembic upgrade head` offline → OK.
- [ ] **Gateway test:** `get_or_create_workspace` creates a row once per user (unique), returns
  stable `pvc_name`, and maps plan→capacity. `poetry run pytest -q` for it → PASS.
- [ ] Proto: add fields 10-12; regen stubs; compile.
- [ ] **Go test:** given `CreatePodOpts.WorkspacePVCName="ws-user-x", WorkspaceCapacityGB=20`,
  the built PVC spec is RWO `20Gi`, has no pod owner-reference, and the pod mounts it RW at
  `/workspace`; and a Terminate does not enqueue that PVC for deletion.
- [ ] Implement ensure-PVC (idempotent Get→Create) + mount + delete-guard; gateway get-or-create + pass-through.
- [ ] `go test ./... && go vet ./...`; `poetry run pytest -q` → PASS; frontend `npm run check`.
- [ ] Update `PodFiles.svelte` persistence copy; commit: `feat(vm): persistent per-user /workspace PVC (FR-HC-28)`.
- [ ] **[cluster-verify]** launch → write to `/workspace` → terminate → relaunch → file present. Confirm PVC not deleted on terminate.

---

## Execution order & rationale

`0 → 1 → 2 → 3 → 4`. Baseline first. Notifications (1) early so its `billing_consumer`
superset merges before I touch that file; Task 2's id fix then repairs both main's and the
merged notification-on-exhaustion lookup. SSH-keys (3) before workspace (4) to shake out the
proto-regen cycle on the smaller change. Tasks 3–4 share the proto + `pod_service.go` +
`pod.go` create path, so they run sequentially, not in parallel.

## Self-review notes

- Every spec item maps to a task (notifications=T1, bug=T2, keys=T3, workspace=T4, baseline=T0).
- Proto field numbers are distinct and additive (9 keys; 10-12 workspace) — no reuse of 1-8.
- Migration ids are linear: 012 → 013_notifications → 014_user_workspaces.
- Cross-task interface: gateway `orchestrator_client.create_pod` grows `authorized_keys`,
  `workspace_pvc_name`, `workspace_capacity_gb`, `storage_class` — all optional/defaulted so
  callers/tests unaffected until wired.
