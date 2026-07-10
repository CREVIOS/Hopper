# Hopper E2E Tests

This Playwright suite stays self-contained under `tests/e2e` and targets the
real SvelteKit frontend routes and auth flow already present in the repo.

## Install

```bash
cd tests/e2e
pnpm install
```

## Run

```bash
pnpm test
pnpm test -- --grep "Authentication"
pnpm test:headed
pnpm test:debug
pnpm report
```

## Auth configuration

Student and admin tests need one of these credential paths:

- Real login:
  - `E2E_STUDENT_EMAIL` and `E2E_STUDENT_PASSWORD`
  - `E2E_ADMIN_EMAIL` and `E2E_ADMIN_PASSWORD`
- Dev-login fallback:
  - `DEV_LOGIN_PASS_ALT` for `/dev-login?as=user`
  - `DEV_LOGIN_PASS` for `/dev-login?as=admin`

If those values are missing, the auth-dependent tests are skipped with an
explicit reason. The Playwright web server injects the frontend proxy defaults
needed to run against `https://hopper.farefin.com` without requiring a
`frontend/.env` file.
