# Hopper E2E Tests

This Playwright suite lives entirely under `tests/e2e` and exercises the real
SvelteKit frontend routes against the deterministic mock stack in `tests/mocks`.
The spec files are organized around the acceptance suites in
`docs/E2E_TESTING.md`, and the current case-by-case status is tracked in
`tests/e2e/COVERAGE_MATRIX.md`.

## Install

```bash
cd tests/e2e
pnpm install
```

## Run

```bash
docker compose -f ../../docker-compose.test.yml up -d --build
pnpm test
pnpm test -- --grep "Authentication"
pnpm test:headed
pnpm test:debug
pnpm report
```

The mock API is reset before every test. Specs can also seed targeted state
through `POST /__test/setup`, which lets the suite cover role-specific flows,
queueing, session refresh, admin actions, and cross-tenant access checks
without touching production code.

## Auth configuration

The default mocked credentials are:

- Student: `student-1@test.edu` / `e2e`
- Professor: `professor@test.edu` / `e2e`
- Admin: `admin@test.edu` / `e2e`

Override them with env vars when you need to point at a different backend or
credential source.

The helper layer still supports these credential paths:

- Real login:
  - `E2E_STUDENT_EMAIL` and `E2E_STUDENT_PASSWORD`
  - `E2E_ADMIN_EMAIL` and `E2E_ADMIN_PASSWORD`
- Dev-login fallback:
  - `DEV_LOGIN_PASS_ALT` for `/dev-login?as=user`
  - `DEV_LOGIN_PASS` for `/dev-login?as=admin`

The Playwright web server injects the frontend proxy defaults needed to run the
suite without a `frontend/.env` file.
