# VM Admission Queue and Capacity Accounting

How Hopper decides whether a VM starts now or waits, and exactly how every
capacity number on screen is calculated.

- **Audience:** anyone reviewing or extending the scheduler.
- **Scope:** CPU, memory, and workspace-storage accounting; the FCFS queue; the
  concurrency guarantees that keep the two consistent.

---

## 1. The problem

The cluster is finite. Before this feature, a VM create request either
succeeded or failed with an error once the cluster filled up: users had to sit
and retry until someone else's VM happened to terminate.

The queue replaces that with a promise. If there is room, your VM starts now.
If there isn't, your request is recorded and starts automatically, in order,
the moment capacity frees.

Two things had to be true for that promise to hold:

1. **The fit check must predict what Kubernetes will actually do.** If the
   gateway's idea of "full" disagrees with the scheduler's, we either admit VMs
   that then fail to schedule, or queue VMs that would have run fine.
2. **No two admitters may spend the same slot.** Multiple gateway workers plus
   racing user requests all consume from one pool.

---

## 2. Where the numbers come from

There is **no host probing anywhere** — no `psutil`, no `libvirt`, no reading
`/proc`. Every figure is derived from Kubernetes' own accounting, which is the
only thing that actually governs whether a pod schedules.

```
free = Σ (Ready nodes' allocatable) − Σ (live VMs' requests) − reserve
```

Each term:

| Term | Source | Notes |
|---|---|---|
| **Ready nodes' allocatable** | `ListNodes` gRPC → orchestrator → `CoreV1().Nodes().List()` | `allocatable`, not `capacity` — what's left after kubelet's own reservations. Non-Ready nodes contribute nothing. |
| **Live VMs' requests** | `SELECT cpu, memory, plan FROM pod_sessions WHERE state IN (…)`, summed in Python | Only states `pending`, `creating`, `running` hold capacity. The summation is in `compute_capacity`, not a SQL aggregate. |
| **Reserve** | Config (`cluster_reserve_cpu`, `cluster_reserve_memory`, `cluster_reserve_storage`) | Covers `kube-system` pods the gateway cannot see. Defaults: 1 core, 2Gi, 10Gi. |

The whole formula is a pure function in
`services/api-gateway/app/services/vm_capacity.py` — no DB, no I/O, so it is
unit-testable in isolation. Nothing is cached; it is recomputed on every read.

### Node filtering

`ListNodes` (`services/orchestrator/internal/k8s/pod.go`) excludes nodes VMs
could never land on, via `schedulableForVMs`:

- cordoned nodes (`Spec.Unschedulable`)
- nodes carrying a `NoSchedule` / `NoExecute` taint — VM pods have no tolerations

This matters: without it the control-plane node is counted, and the cluster
appears to have memory that no VM can ever be scheduled onto. Covered by
`TestSchedulableForVMs` (`services/orchestrator/internal/k8s/node_schedulable_test.go`).

---

## 3. The critical detail: requests vs limits

**This is the part that surprises people, and it is deliberate.**

A VM is created with both a *request* (what the scheduler reserves for it) and a
*limit* (the ceiling it may burst to). They are not the same, and for CPU they
differ by design:

```
cpu_request = max(100m, cpu_limit ÷ 4)     ← what capacity accounting charges
cpu_limit   = the plan's advertised CPU     ← what the VM may actually burst to

mem_request = mem_limit                     ← memory is charged in full
```

Defined once in `cpuRequestFor`
(`services/orchestrator/internal/k8s/pod.go`) and mirrored exactly by
`cpu_request_millis` (`vm_capacity.py`). The two **must** stay in sync — the Python
docstring names the Go function as the source of truth.

**Why a quarter?** VMs spend almost all their time idle at a shell prompt.
Reserving the full limit would block new VMs from scheduling against capacity
that is sitting unused. Requesting a quarter lets VMs bin-pack roughly 4x
denser, while the CPU *limit* still caps any individual burst. This is the same
burstable model as AWS T-series or GCP shared-core instances.

**Why is memory charged in full?** Memory is incompressible. A process cannot
be throttled down to fit the way CPU can — it gets OOM-killed. Overcommitting
memory trades a slow VM for a dead one, so memory reserves its full limit and
is, in practice, the constraint that actually gates admission.

### What each plan actually costs the pool

| Plan | Advertised | CPU charged | Memory charged | Storage charged |
|---|---|---|---|---|
| `small` | 1 CPU, 2 GB, 5 GB | **0.25 cores** | 2 GiB | 5 GiB |
| `medium` | 2 CPU, 4 GB, 10 GB | **0.5 cores** | 4 GiB | 10 GiB |
| `large` | 4 CPU, 8 GB, 20 GB | **1.0 core** | 8 GiB | 20 GiB |

So **starting a "1 CPU" small VM reduces free CPU by 0.25, and releasing it
returns 0.25.** That is correct, not a rounding error. The VM can still use a
full core whenever one is idle.

Because a small VM draws a much larger share of the memory pool than of the CPU
pool, **memory runs out first in practice** and CPU rarely binds. On a host with
24 GiB and 11 cores, one small VM takes 8.3% of memory but only 2.3% of CPU — so
memory exhausts roughly 3.7x sooner. This holds for every plan, and is pinned by
`test_memory_binds_before_cpu_for_each_plan`
(`services/api-gateway/tests/unit/test_vm_capacity.py`) rather than left to the
specific numbers above, which are illustrative.

### Storage is a logical quota

Node `ephemeral-storage` is not reported by `ListNodes`, so unlike CPU and
memory the storage **total is configured**, not measured (`cluster_storage_total`,
default 150Gi). Used storage is the sum of live VMs' plan disk, resolved from the
plan (`_plan_disk`) because disk is not a `pod_sessions` column.

Note the current limitation: **VMs are ephemeral — no PVC is provisioned**, so
storage is an allocation quota that prevents overselling rather than a
measurement of real free disk.

Worth being precise about what's missing, because it is less than it looks. PVC
create/delete is **already implemented** in the Kubernetes layer, gated on
`opts.DiskGiB > 0` (`pod.go`), and the proto already carries a `disk` field. Two
links are absent between them:

1. the gateway never sends `disk` to `create_pod` (it defaults to `""`), and
2. the gRPC handler never maps `req.Disk` onto `CreatePodOpts.DiskGiB`
   (`services/orchestrator/internal/grpc/pod_service.go`).

Passing disk from the gateway alone would therefore still provision nothing —
both links are needed.

---

## 4. The request path

```
POST /pods/
  │
  ├─ credit check ─────────────── 402 if balance < plan rate
  ├─ per-user cap (3 live VMs) ── 429 if at cap
  │
  ├─ fetch_nodes()  ── unreachable? ──► FAIL OPEN: create synchronously,
  │                                     no capacity gate (never worse than
  │                                     before the queue existed)
  │
  └─ reserve_sync_slot()          [under the admission lock]
       │
       ├─ someone already queued? ──► queue (FCFS fairness: no queue-jumping
       │                              even if this request would fit)
       ├─ plan_fits()? ── no ──────► queue
       └─ yes ─────────────────────► reserve a PodSession row → 201 Created
                                     (then create_pod gRPC, lock released)
```

Queued requests return **202 Accepted** with a 1-based queue position rather
than an error. The frontend branches on the `queued` discriminator in the body
and redirects to the queue page.

**Why the "someone is already waiting" check matters:** without it, a small VM
could slip past a queued large VM forever, because the small one fits into gaps
the large one can't. That is starvation. The check enforces strict FCFS: if a
line exists, you join it.

### The admission loop

A background loop (`reconcile_pass`) re-runs on a 5s tick or when nudged:

```
_requeue_stuck_admitting()      ← reap crashed admits
fetch_nodes()                    ← None ⇒ skip the pass entirely

── Phase 1: reserve (under the admission lock, one short txn) ──
  cap = free capacity
  for each 'queued' entry, ordered by seq ASC:
      doesn't fit?        → BREAK   (head-of-line, no backfill)
      user at 3-VM cap?   → CONTINUE (skip without blocking the line)
      atomically claim: UPDATE … SET state='admitting' WHERE state='queued'
      reserve a pending PodSession
      decrement local free counters   ← so one pass can't over-admit
  COMMIT                              ← releases the lock

── Phase 2: materialize (unlocked) ──
  create_pod gRPC per reservation; on failure mark the session 'failed'
```

**Head-of-line, no backfill** is a deliberate fairness choice: if the front
entry doesn't fit, the pass stops rather than letting smaller entries behind it
jump ahead. It costs some utilization to guarantee the front of the line is
never starved. The per-user cap is the one exception — a user at their cap is
skipped, because they are not blocked on capacity and would otherwise wedge the
queue for everyone.

### Waking the loop

Capacity frees whenever a VM leaves `pending`/`creating`/`running`. Some paths
call `nudge()` directly (user delete); others don't (billing exhaustion, session
reaper, NATS state repair). Those rely on the orchestrator's `pod.stopped` NATS
event, consumed with **no queue group** so every worker nudges its own local
loop and the leader acts.

Core NATS has no persistence, so a dropped event would strand the queue — the
**5s tick is the required backstop**, not a redundancy.

---

## 5. Correctness under concurrency

The first cut of this design over-admitted under concurrency: it read free
capacity and then created the pod, leaving a window in which two requests could
both see the same free slot and both take it. Each row below is a race that had
to be closed to make the queue's promise hold.

| Risk | Mitigation |
|---|---|
| Two admitters spend the same slot | All admission serializes on one Postgres advisory **xact** lock (`_ADMISSION_LOCK_KEY`). The capacity read and the reservation are in the same short transaction. |
| Slow gRPC held under the lock | `create_pod` runs in **Phase 2, after commit**. The lock covers only the DB reservation. `fetch_nodes` is deliberately called *outside* it too. |
| Cancel-then-admit races / double-admit | Atomic claim: `UPDATE … WHERE state='queued' RETURNING id`. Losing the race returns no row and the entry is skipped. |
| One pass admitting past the pool | Local free counters are decremented per admit within the pass. |
| Per-user cap bypassed via the queue | The cap is enforced inside the loop, not only at the router. |
| Worker crashes mid-admit | Entries stuck in `admitting` past 120s are reaped and requeued. The FK is nulled **before** deleting the orphan session. |
| Multiple workers running the loop | Postgres lease (`scheduler_leader`), taken by a single conditional `UPDATE` — pooler-safe, and always advanced by the **server** clock so worker clock skew is irrelevant. |
| Orchestrator down blocks all creates | **Fail open** — create without the gate rather than deny service. |

**Reservation *is* the record.** Inserting the `pending` `PodSession` under the
lock is what consumes the capacity, because `_free_from_nodes` counts exactly
those rows. There is no separate ledger to drift out of sync.

### FCFS ordering

Order comes from `seq`: `BigInteger Identity(always=True, start=1)`, unique,
with a partial index on `(seq) WHERE state = 'queued'`. Identity (not a
timestamp) means ordering is gapless and immune to clock skew and to two entries
landing in the same millisecond.

`cpu`/`memory` are **frozen onto the queue entry** at enqueue time, so changing a
plan's defaults later cannot retroactively alter what an already-queued request
asked for.

---

## 6. The availability readout

`GET /pods/availability` is best-effort and **never 500s**: if the orchestrator
is unreachable every capacity field returns `null` (the UI shows em dashes)
while `queue_length`, read straight from Postgres, stays real.

`used` is derived as `total − free`, so the three values always reconcile.
**Note this folds in the reserve** — `used_cores` is not purely VM requests.

The panel (`frontend/src/routes/pods/+page.svelte`) polls it every 5s.

### A presentation hazard worth recording

The quarter-core rule makes the CPU figure look wrong to anyone who hasn't read
§3. Starting a VM advertised as *1 CPU* moves free CPU by 0.25 — and the
original formatter rounded to one decimal, so a 0.25-core release rendered as
`8` → `8.3`. Both the model and the rounding were invisible, and the combination
reads as broken arithmetic even though the math is exact.

The fix (#93) was presentation-only, leaving the scheduling math untouched:
figures render at 2dp (`frontend/src/lib/capacity/format.ts`) so a quarter core
shows as `8.25`, and the panel states the model itself:

> A VM reserves a **quarter** of its plan's CPU and bursts up to the full limit
> whenever cores are idle — so a 1 CPU VM takes 0.25 from free CPU. Memory and
> storage are reserved in full. Free storage is a workspace quota, not measured
> disk.

The general lesson: a correct number that contradicts what the product advertises
is a defect in the readout, not a rounding preference.

---

## 7. Verification

Automated coverage in the repo:

| What | Where |
|---|---|
| The pure capacity math — quantity parsing, the quarter-core rule, reserves, fit, and that memory binds before CPU for every plan (`test_memory_binds_before_cpu_for_each_plan`) | `services/api-gateway/tests/unit/test_vm_capacity.py` |
| Node filtering (cordoned / tainted excluded) | `services/orchestrator/internal/k8s/node_schedulable_test.go` — `TestSchedulableForVMs` |
| Queue admission end-to-end | `services/api-gateway/tests/integration/test_vm_queue_live.py` |

Access control is enforced in code and covered above: `DELETE /pods/queue/{id}`
checks `entry.user_id == current_user.sub` (403 otherwise), and `GET /pods/queue`
is filtered to the caller, so one user can neither see nor cancel another's
entry.

Manual verification on a kind cluster during development: 4 users × small VMs
against a deliberately constrained pool — 2 admitted (201), 2 queued (202,
positions 1 and 2); the readout matched actual state; terminating a VM admitted
the next in line FCFS. Storage checked with 1 small + 1 large:
`used = 10 (reserve) + 5 + 20 = 35Gi`, consistent with `used = total − free`.
These are recorded observations from a development cluster, not reproducible
assertions — the automated tests above are the durable evidence.

---

## 8. Known limitations

Stated plainly, because each is a deliberate trade rather than an oversight:

1. **Aggregate fit, not per-node bin-packing.** `plan_fits` compares against
   cluster-wide free capacity. A VM can pass the gate and still fail to schedule
   if no *single* node has room — fragmentation. Correct fix is per-node fit or
   delegating to a real queueing system (Kueue manifests exist but are unwired).
2. **Storage is a logical quota**, not measured disk, and no PVC is provisioned.
3. **Head-of-line blocking wastes some utilization** by design, in exchange for
   no starvation.
4. **Fail-open bypasses the capacity gate** when the orchestrator is unreachable
   — availability chosen over enforcement.
5. **Tiny orphan-pod window** if a worker dies between `create_pod` and the state
   write. Pod names are time-based rather than deterministic, so the reaper
   cannot always identify the orphan.
6. **Two parallel CPU-request formulas** (Go and Python) must stay in sync by
   convention, enforced only by tests and a docstring.
7. **Two `ListNodes` gRPC calls per availability request** — one for
   `nodes_ready`, one inside `current_capacity` — polled every 5s per open
   browser. They could share a single call.

---

## 9. Where the code lives

| Concern | File |
|---|---|
| Pure capacity math | `services/api-gateway/app/services/vm_capacity.py` |
| Admission loop, leader lease, reservations | `services/api-gateway/app/services/vm_scheduler.py` |
| Enqueue / position / count | `services/api-gateway/app/services/vm_queue.py` |
| NATS wake-up consumer | `services/api-gateway/app/services/vm_scheduler_consumer.py` |
| API surface | `services/api-gateway/app/routers/pods.py` |
| Plan definitions (source of truth) | `services/api-gateway/app/schemas/pod.py` |
| Reserve / pool config | `services/api-gateway/app/config.py` |
| Pod spec, `cpuRequestFor`, `ListNodes`, PVC support | `services/orchestrator/internal/k8s/pod.go` |
| gRPC handler (`CreatePodOpts` mapping) | `services/orchestrator/internal/grpc/pod_service.go` |
| Queue tables + leader lease | `services/api-gateway/alembic/versions/014_vm_scheduler_queue.py` |
| Availability panel + queue page | `frontend/src/routes/pods/+page.svelte`, `frontend/src/routes/pods/queue/+page.svelte` |
