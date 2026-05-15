#!/usr/bin/env bash
# Apply production-grade hardening to the Keycloak `hopper` realm and the
# `hopper-api` client. Idempotent — safe to re-run.
#
# Settings here implement the 2026 OAuth 2.0/OIDC best practices that the
# Keycloak default realm config does not enable automatically:
#
#   - sslRequired=external           force HTTPS for browser-facing flows
#   - bruteForceProtected=true       temp lockout after `failureFactor` failures
#   - failureFactor=5                lock after 5 bad attempts (default was 30)
#   - revokeRefreshToken=true        rotate refresh token on every use
#   - refreshTokenMaxReuse=0         any replay of an old RT revokes the family
#                                    (refresh-token reuse detection)
#   - passwordPolicy=length(12) + digits + lower + upper + notUsername + history(3)
#   - PKCE S256 enforced on the hopper-api client
#   - redirectUris locked to /api/auth/callback on prod + local dev
#   - fullScopeAllowed=false         the client gets only its declared scopes
#
# Usage: scripts/keycloak-harden.sh
#
# Skipped here (apply manually if your deployment can support them):
#   - Switching `hopper-api` from public to confidential. Requires generating
#     a client secret, storing it as a K8s Secret, and setting
#     HOPPER_KEYCLOAK_CLIENT_SECRET on the api-gateway. The current code
#     (services/api-gateway/app/routers/auth.py) already passes the secret
#     iff `settings.keycloak_client_secret` is set — flip both sides together.
#   - Adding WebAuthn as a required action for admins.

set -euo pipefail

KC_NS="${KC_NS:-hopper}"
KC_DEPLOY="${KC_DEPLOY:-deploy/keycloak}"
REALM="${REALM:-hopper}"
CLIENT_ID="${CLIENT_ID:-hopper-api}"
PUBLIC_HOST="${PUBLIC_HOST:-https://hopper.farefin.com}"
DEV_HOST="${DEV_HOST:-http://localhost:5173}"

kc() {
  kubectl exec -n "$KC_NS" "$KC_DEPLOY" -- /opt/keycloak/bin/kcadm.sh "$@"
}

echo "[+] Logging in to kcadm..."
kc config credentials --server http://localhost:8080 --realm master \
  --user "${KC_ADMIN:-admin}" --password "${KC_ADMIN_PASSWORD:-admin}" >/dev/null

echo "[+] Realm hardening (sslRequired, brute-force, refresh rotation, password policy)..."
kc update "realms/$REALM" \
  -s sslRequired=external \
  -s bruteForceProtected=true \
  -s permanentLockout=false \
  -s failureFactor=5 \
  -s waitIncrementSeconds=60 \
  -s maxFailureWaitSeconds=900 \
  -s minimumQuickLoginWaitSeconds=60 \
  -s quickLoginCheckMilliSeconds=1000 \
  -s maxDeltaTimeSeconds=43200 \
  -s revokeRefreshToken=true \
  -s refreshTokenMaxReuse=0 \
  -s 'passwordPolicy=length(12) and digits(1) and lowerCase(1) and upperCase(1) and notUsername(undefined) and passwordHistory(3)' \
  >/dev/null

echo "[+] Client hardening (PKCE S256, redirect URIs, scope)..."
CID=$(kc get clients -r "$REALM" -q "clientId=$CLIENT_ID" --fields id --format csv --noquotes | tail -1 | tr -d '\r')
if [[ -z "$CID" ]]; then
  echo "[!] client $CLIENT_ID not found — run README §5 first"
  exit 1
fi

kc update "clients/$CID" -r "$REALM" \
  -s 'attributes."pkce.code.challenge.method"=S256' \
  -s "redirectUris=[\"$PUBLIC_HOST/api/auth/callback\",\"$DEV_HOST/api/auth/callback\"]" \
  -s "webOrigins=[\"$PUBLIC_HOST\",\"$DEV_HOST\"]" \
  -s fullScopeAllowed=false \
  >/dev/null

echo "[+] Ensure realm roles flow through the client's scope-mappings..."
# With fullScopeAllowed=false (set above) the client only emits realm roles
# that are listed in its scope-mappings. Without these explicit additions,
# admin tokens come back without `realm_access.roles`, so the api-gateway
# sees every user as a default student and admin endpoints 403.
ROLES_JSON=$(kc get roles -r "$REALM" --fields id,name 2>/dev/null \
  | python3 -c "
import json, sys
keep = {'admin', 'professor', 'student'}
out = [r for r in json.load(sys.stdin) if r['name'] in keep]
print(json.dumps(out))")
EXISTING=$(kc get "clients/$CID/scope-mappings/realm" -r "$REALM" --fields name 2>/dev/null \
  | python3 -c "import json,sys;print(' '.join(r['name'] for r in json.load(sys.stdin)))" 2>/dev/null || echo "")
if [[ "$EXISTING" != *"admin"* || "$EXISTING" != *"student"* ]]; then
  echo "$ROLES_JSON" | kubectl exec -i -n "$KC_NS" "$KC_DEPLOY" -- \
    /opt/keycloak/bin/kcadm.sh create "clients/$CID/scope-mappings/realm" -r "$REALM" -f - >/dev/null
  echo "    scope-mappings added: admin, professor, student"
else
  echo "    scope-mappings already cover the three app roles"
fi

echo "[+] Ensure the access-token audience mapper exists (so aud includes $CLIENT_ID)..."
MAPPERS=$(kc get "clients/$CID/protocol-mappers/models" -r "$REALM" --fields name 2>/dev/null \
  | python3 -c "import sys,json;print(' '.join(m['name'] for m in json.load(sys.stdin)))" 2>/dev/null || echo "")
if [[ "$MAPPERS" != *"hopper-api-audience"* ]]; then
  kc create "clients/$CID/protocol-mappers/models" -r "$REALM" \
    -s name=hopper-api-audience \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-audience-mapper \
    -s "config.\"included.client.audience\"=$CLIENT_ID" \
    -s 'config."id.token.claim"=false' \
    -s 'config."access.token.claim"=true' >/dev/null
  echo "    audience mapper added"
else
  echo "    audience mapper already present"
fi

echo "[✓] Hardening applied. Verify with:"
echo "    kubectl exec -n $KC_NS $KC_DEPLOY -- /opt/keycloak/bin/kcadm.sh get realms/$REALM"
