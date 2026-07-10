# Hopper — Security Findings (Student & Admin Surfaces)

> Defensive review of the team's own project, verified against `main` on
> 2026-07-10 (independent deep read of the auth stack, all routers, credit
> service, orchestrator pod spec, K8s manifests, network policies, ingress, and
> the VM image). Evidence is `file:line`. No files were modified during review.
>
> Severity: **CRITICAL** / **HIGH** / **MEDIUM** / **LOW**.
> "In-flight?" flags findings the `origin/security/hopper-audit-remediation`
> branch appears to already address (reconcile before re-fixing).

---

## 0. Posture Summary

The codebase shows real security awareness and gets the hard parts right:

- **JWT**: RS256-pinned (no alg-confusion), verifies signature/`aud`/`iss`/`exp`
  with `require_exp`, JWKS cached with lock + forced refresh on `kid` rotation (`middleware/auth.py:58-101`).
- **AuthZ**: every `/admin` route enforces `role=="admin"` (`admin.py:22-29`);
  every pod/file endpoint enforces ownership (`pods.py:185,204,240,308,443,538`, `files.py:45`).
- **Ledger**: amount bounded `Field(gt=0, le=1e9)`, self-transfer blocked, professor→student
  only, source balance checked under `pg_advisory_xact_lock` (`credits.py:65-154`, `credit_service.py:152`).
- **Pod sandbox** (`orchestrator/internal/k8s/pod.go:160-296`): `automountServiceAccountToken:false`,
  `allowPrivilegeEscalation:false`, seccomp `RuntimeDefault`, drop-ALL caps + minimal re-add (no `NET_RAW`),
  LXCFS mounts are single read-only files (`Type:File`), root password from `crypto/rand` (144-bit).
- **Abuse**: slowapi per-route limits, pod cap 3, SSH-key cap 10, constant-time (`secrets.compare_digest`)
  5-attempt-capped single-use email codes (`verification.py`), nginx edge rate limits.
- **IMDS**: VM egress blocks 169.254/16 + Alibaba/Oracle metadata (`04-network-policies.yaml:155-163`).

The material risks cluster into: **committed credentials**, **signup email-verification
bypass**, **broken access control on the `image` field**, **an over-privileged gateway**,
and **VM root-password sprawl**.

---

## HIGH

### H-1. Committed working IdP + DB credentials — `k8s/deploy/00-secrets.yaml`
`stringData` ships **real** values: `keycloak-admin` = `admin/admin` (`:38-40`, the
Keycloak **master-realm superuser**, consumed by `01-infra.yaml:212-217`) and
`hopper-db` = `hopper/hopper_dev` + full `database-url` (`:24-28`). The repo is public.
The admin console isn't on the public ingress (`03-ingress.yaml`, good), but any
in-cluster foothold (e.g. a gateway RCE — see H-4) can reach `keycloak:8080` and log
in as `admin/admin` to mint admin tokens / reset any password → **total takeover**;
the DB holds plaintext VM passwords + the ledger.
**Fix:** replace with placeholders (as the sibling `hopper-keycloak-admin` secret already does),
generate random creds in-cluster, rotate `admin/admin` and `hopper_dev` immediately.

### H-2. Email-verification bypass at signup — `routers/auth.py:224-263`
Signup creates the Keycloak user with `emailVerified=false` and `requiredActions=[]`
(`keycloak_admin.py:164`), then immediately `_password_grant` + `_issue_session` → returns
valid auth cookies **before any verification**. `require_email_verified` is only checked in
`login_direct` (`:364`) and `callback` (`:427`); `/auth/refresh` never re-checks (`:473-517`),
so the session is durable. **Impact:** an attacker registers *any unused allowed-domain email*
(`someone@du.ac.bd`) with their own password and operates as that identity — the code goes to
the real owner, but the attacker already holds a working session.
**Fix:** don't issue a session from `/signup` (require `/verify-email` first), or re-check
`email_verified` on `/auth/refresh`. *(This also interacts with the SRS-vs-code signup pivot — see gap analysis §3.)*

### H-3. Arbitrary / unauthorized container image on pod create — `schemas/pod.py:44-54`, `pods.py:129`, `pod_service.go:109`
`CreatePodRequest.image: str | None`; when set, `resolved_image()` returns it **verbatim**,
bypassing the `VM_TEMPLATE_IMAGES` allowlist, with **no role check** in `pods.create_pod`.
The orchestrator runs it as the Pod image (`pod.go:221`). **Impact:** any student runs an
arbitrary image from any registry — supply-chain risk, resource/disk abuse, and a hand-picked
rootfs to probe for sandbox escape. (The strong pod sandbox limits incremental RCE, but this
is a clear broken-access-control + unvalidated-input defect.)
**Fix:** ignore client `image` for non-admins; validate any override against a server-side allowlist.

### H-4. Internet-facing gateway runs under the powerful orchestrator ServiceAccount — `k8s/deploy/02-apps.yaml:24`
The api-gateway is set `serviceAccountName: orchestrator`, whose Role (`:173-188`) holds
`pods`/`services` create/update/delete, **`pods/exec`**, **`pods/portforward`**, `pods/log`,
PVC create/delete, and cluster `nodes` read; its SA token is mounted. The gateway only needs
`pods:get,list` + `pods/portforward:create`. **Impact:** a gateway RCE yields `kubectl exec`
into **any** pod in `hopper` (Postgres, Keycloak, other VMs) + pod create/delete.
**In-flight?** `02-apps.yaml` is modified on the remediation branch — verify whether it splits the SA.
**Fix:** give the gateway its own least-privilege SA; keep exec/create/delete on the orchestrator only.

---

## MEDIUM

### M-1. VM root-password sprawl + internet-open root SSH (aggregate)
The per-pod root password is stored in **four** places: pod annotation `hopper.dev/ssh-password`
(`pod.go:192-194`), env `ROOT_PASSWORD` (`:245`), **plaintext in the DB** (`models/session.py:22`),
and **returned in API bodies** for running pods (`pods.py:56`, `schemas/pod.py:69`). Meanwhile
every VM's sshd is reachable from `0.0.0.0/0` on port 22 (`04-network-policies.yaml:319-337`)
with `PermitRootLogin yes` + `PasswordAuthentication yes` (`images/hopper-vm/Dockerfile:12-13`).
The 144-bit password makes guessing infeasible, but **any** annotation/DB read (see H-1) → root
on every VM, internet-wide, with no fail2ban/allowlist. It's the user's own credential, but the
sprawl multiplies the exposure.
**Fix:** store the password in a per-pod `Secret` (`secretKeyRef`), scope RBAC to the orchestrator,
deliver to the browser via one dedicated non-cached endpoint, restrict SSH ingress to campus/VPN,
and prefer the users' uploaded SSH keys (also fixes the "keys never injected" gap) over password auth.

### M-2. Signup / reset codes logged to stdout when SMTP unset (the default) — `services/email.py:94-95`
If `smtp_host` is empty the verification/reset code is `logger.warning(...)`. The default
`hopper-smtp` secret ships `smtp-host: ""` (`00-secrets.yaml:86`) and the env ref is `optional:true`,
so unless SMTP is provisioned out-of-band, **every signup/reset code is logged** → Loki. Log
access → account takeover.
**Fix:** fail closed (refuse to issue codes) when SMTP is unconfigured outside dev; never log code plaintext.

### M-3. IDOR on `GET /usage/{pod_id}` — `routers/usage.py:22-60`
Queries `metrics_samples WHERE pod_id = :pod_id` for any caller-supplied `pod_id` with **no
ownership check** (contrast `/summary/me`, which scopes by `user_id`). A student can enumerate
pod UUIDs and read other tenants' CPU/RAM series.
**In-flight?** The remediation branch adds `tests/test_usage_auth.py` + `usage.py` changes — likely fixes this. Reconcile.
**Fix:** load the `PodSession` and enforce `user_id == current_user.sub` (mirror `files._get_user_pod`).

### M-4. Client-IP spoofing via `--forwarded-allow-ips=*` — `k8s/deploy/02-apps.yaml:53-54`
Uvicorn trusts `X-Forwarded-For` from any peer and rewrites `client.host` to the client-supplied
value. The slowapi limiter keys on `get_remote_address` and the audit log records `request.client.host`
(`middleware/audit.py:82`), so a rotating spoofed XFF evades per-IP limits and poisons audit
attribution. (Partially mitigated by nginx edge `limit-rps`.)
**Fix:** set `--forwarded-allow-ips` to the ingress pod CIDR; have nginx overwrite (not append) XFF.

### M-5. Defense-in-depth resting solely on NetworkPolicy
- **code-server runs `auth: none`** (`images/hopper-vm/config/code-server-config.yaml:14`); the
  NodePort also exposes :8080. Only the `api-gateway-to-user-vms` CNI policy stands between the
  internet and an unauthenticated browser root shell. If the policy is misapplied or the CNI degrades → unauth RCE on every VM.
- **Orchestrator gRPC is unauthenticated plaintext** (`orchestrator_client.py:60` `insecure_channel`;
  `pod_service.go` has no authn) — any platform-pod foothold can `CreatePod(user_id=…)`/`TerminatePod`
  as anyone. Contained today only by `allow-platform-internal`.
- **User VMs run in the `hopper` platform namespace with no Pod Security Admission** — co-located
  with Postgres/Keycloak/gateway + their Secrets. The `restricted` PSA label is on the unused
  `hopper-pods` namespace (`k8s/base/namespaces.yaml`).
**Fix:** keep a per-pod code-server token; add mTLS + a caller-identity check on gRPC; schedule
user VMs into a dedicated PSA-enforced namespace (`enforce: baseline`).

### M-6. `sshpass -p <password>` exposes the password in process args — `files.py:101-105,165-168,201-205`
On the gateway pod the password is visible in `ps auxww`/`/proc/<pid>/cmdline` to any co-process
for the SCP/SSH duration.
**Fix:** use `sshpass -e` (env) or reuse the asyncssh path the terminal already uses.

---

## LOW

- **L-1. No CSRF token; mutating routes rely solely on `SameSite=Lax`** — `X-CSRF-Token` is
  allow-listed (`main.py:67`) but never validated. `SameSite=Lax` *does* block cross-site POSTs so
  this is acceptable, but the advertised header is misleading and there's no double-submit
  defense-in-depth. *(Clickjacking is separately covered: SvelteKit SSR + nginx both set `X-Frame-Options`.)*
- **L-2. No Content-Security-Policy** anywhere (gateway/SSR/ingress). For an app embedding code-server
  in an iframe and proxying untrusted HTML, a CSP would cut XSS blast radius.
- **L-3. `HOPPER_DEBUG=true` in prod + public `/docs` `/openapi.json`** (`02-apps.yaml:111-112`;
  `main.py` never disables docs). Recon aid. Fix: `debug=false`, `docs_url=None` in prod.
- **L-4. OIDC `nonce` generated but never validated** — `auth.py:391` reads `expected_nonce` from the
  cookie but never compares it to the ID-token claim (CSRF still covered by `state`).
- **L-5. `dest_path`/`file.filename` unsanitized on upload** — `files.upload_file` skips `_safe_path`
  and builds `f"{dest_path}/{file.filename}"`. Confined to the caller's own pod (already root), so
  low impact, but an input-validation inconsistency (also a temp-file suffix robustness issue).
- **L-6. Platform egress not IMDS-restricted (asymmetry)** — `platform-egress-internet`
  (`04-network-policies.yaml:215-241`) lets api-gateway/keycloak reach `0.0.0.0/0:443` **without**
  excluding 169.254.169.254, unlike `user-vm-egress`. No current SSRF sink in the gateway (vscode proxy
  is loopback), so defense-in-depth only. Also: IPv6 IMDS (`fd00:ec2::/64`) is named in a comment but
  not in the IPv4-only `except` list — moot on the IPv4 Azure deploy.
- **L-7. Audit gaps** — `POST /auth/login` (direct grant) isn't in the audit action map (`audit.py:23-35`);
  fire-and-forget logging can silently drop on error (`except: pass`); attribution IP is spoofable (M-4).
- **L-8. Dead `routers/terminal.py`** (unregistered kubectl-exec PTY, no idle/input caps) — delete to remove latent risk.
- **L-9. `add_credits` takes no advisory lock** (`credit_service.py:76`) — a concurrent admin-grant +
  billing-deduct can race the denormalized `current_balance`. Admin-triggered, low likelihood.

---

## Couldn't fully verify (flagged for follow-up)

- Whether `scripts/keycloak-harden.sh` (brute-force protection, refresh rotation, 12-char policy,
  PKCE S256, `fullScopeAllowed=false`, `aud` mapper) was actually applied to the live realm. The
  JWT `audience=hopper-api` check *depends* on that mapper (fails closed otherwise). The script does
  **not** rotate the `admin/admin` master password (see H-1).
- Whether Cilium enforces the `except: 10.43.0.0/16` ClusterIP block (the manifest itself warns
  standard-NetworkPolicy `ipBlock` may not restrict ClusterIPs under Cilium). Lateral movement is
  independently contained by the platform-services ingress rules.

---

## Recommended remediation order (student/admin priority)

1. **H-1** rotate + de-commit credentials (fastest, highest impact).
2. **H-2** signup verification bypass (identity integrity).
3. **H-3** lock the `image` field to admins/allowlist.
4. **H-4** split the gateway SA (least privilege).
5. **M-1** consolidate VM password handling (per-pod Secret; prefer SSH-key injection).
6. **M-2 / M-3 / M-4** fail-closed email, `/usage` ownership (branch), trusted client IP.
7. **M-5** PSA namespace + gRPC authz + code-server token; then LOW hardening.

*Several MEDIUM items (M-3 usage authz, possibly M-4/H-4 via `02-apps.yaml`) are partially
addressed on `origin/security/hopper-audit-remediation` — reconcile that branch before re-fixing.*
