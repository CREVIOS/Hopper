# Coverage Reports

This directory is the test-facing entry point for coverage output.

- `REPORT.md`
  - generated Markdown summary across Python, frontend, and Go coverage artifacts
- source artifacts remain in:
  - `coverage/python/`
  - `coverage/frontend/`
  - `coverage/orchestrator/`

Refresh from repo root:

```bash
./scripts/test/run.sh test-coverage
```

If coverage artifacts already exist and you only want to rebuild the Markdown report:

```bash
./scripts/test/run.sh test-coverage-report
```
