# Load Testing

The load suite is split into:

- `tests/load/class-start.js`
  - lightweight smoke validation against the deterministic test stack
  - covers `GET /healthz`, `GET /credits/balance`, `GET /pods/`, one pod create, one pod fetch, and one pod termination
- `tests/load/scenarios.js`
  - bounded multi-scenario exercise for class start, metrics polling, spike traffic, class end, and billing-heavy reads
  - defaults are intentionally short and self-cleaning so the deterministic single-user stack does not accumulate pods and spiral into a runaway load run

Expected environment:

- `BASE_URL`
  - default: `http://127.0.0.1:8000`
- `ACCESS_TOKEN`
  - default: `e2e-student-1`
  - this is the deterministic mock token for `student-1@test.edu`, injected both as a bearer token and `session_token` cookie by the scripts

Canonical commands from repo root:

```bash
./scripts/test/run.sh test-services-up
./scripts/test/run.sh test-load-smoke
./scripts/test/run.sh test-load
./scripts/test/run.sh test-services-down
```

Useful overrides for a heavier run:

- `K6_MAX_LIVE_PODS`
  - maximum live pods the scenario will allow for the shared load-test user before it starts cleaning up
  - default: `2`
- `K6_CLASS_START_VUS`, `K6_CLASS_START_ITERATIONS`
- `K6_METRICS_VUS`, `K6_METRICS_DURATION`, `K6_METRICS_START_TIME`
- `K6_SPIKE_PEAK_VUS`, `K6_SPIKE_UP_DURATION`, `K6_SPIKE_HOLD_DURATION`, `K6_SPIKE_DOWN_DURATION`, `K6_SPIKE_START_TIME`
- `K6_CLASS_END_VUS`, `K6_CLASS_END_ITERATIONS`, `K6_CLASS_END_START_TIME`
- `K6_BILLING_VUS`, `K6_BILLING_DURATION`, `K6_BILLING_START_TIME`

Example:

```bash
K6_CLASS_START_VUS=30 K6_CLASS_START_ITERATIONS=30 K6_SPIKE_PEAK_VUS=80 ./scripts/test/run.sh test-load
```

Artifacts:

- smoke summary: `test-results/load/class-start-summary.json`
- full run summary: `test-results/load/scenarios-summary.json`
