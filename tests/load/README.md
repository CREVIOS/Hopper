# Load Testing

The load suite is split into:

- `tests/load/class-start.js`
  - lightweight smoke validation against the deterministic test stack
  - covers `GET /healthz`, `GET /credits/balance`, `GET /pods/`, one pod create, one pod fetch, and one pod termination
- `tests/load/scenarios.js`
  - extended multi-scenario exercise for class start, metrics polling, spike traffic, class end, and billing-heavy reads

Expected environment:

- `BASE_URL`
  - default: `http://127.0.0.1:8000`
- `ACCESS_TOKEN`
  - default: `e2e-student`
  - the deterministic mock API also accepts this value via the `session_token` cookie injected by the scripts

Canonical commands from repo root:

```bash
./scripts/test/run.sh test-services-up
./scripts/test/run.sh test-load-smoke
./scripts/test/run.sh test-load
./scripts/test/run.sh test-services-down
```

Artifacts:

- smoke summary: `test-results/load/class-start-summary.json`
- full run summary: `test-results/load/scenarios-summary.json`
