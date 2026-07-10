#!/usr/bin/env bash
#
# keycloak-bootstrap.sh — provision the `hopper` realm for LOCAL DEV so login works.
#
# Neither docker-compose nor deploy-local.sh creates the realm; they only start
# Keycloak as admin/admin. This script (idempotent) creates:
#   - realm `hopper` (sslRequired=NONE so http://localhost works)
#   - realm roles: admin, professor, student
#   - public client `hopper-api` (auth-code + direct-grant + PKCE) WITH an
#     audience mapper so access tokens carry aud=hopper-api (the gateway's JWT
#     check requires it)
#   - confidential service-account client `hopper-admin` (realm-admin) for the
#     gateway's admin ops (signup/create-user/set-role/logout)
#   - dev users: admin/admin123 (role admin), testuser/testuser123 (role student)
#
# It runs kcadm INSIDE the Keycloak container (no local kcadm needed).
#
# Usage:  ./scripts/keycloak-bootstrap.sh
# After:  export HOPPER_KEYCLOAK_ADMIN_CLIENT_SECRET=<printed secret>  (for signup/admin)
#         then log in via the frontend, or hit /dev-login?as=admin | ?as=user
set -euo pipefail

REALM="hopper"
ADMIN_SECRET="${HOPPER_ADMIN_CLIENT_SECRET:-hopper-admin-dev-secret}"
FRONTEND="http://localhost:5173"
GATEWAY="http://localhost:8000"

# --- locate the Keycloak container -------------------------------------------
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT_DIR"
KC="$(docker compose ps -q keycloak 2>/dev/null || true)"
[ -z "$KC" ] && KC="hopper-keycloak-1"
if ! docker inspect "$KC" >/dev/null 2>&1; then
  echo "ERROR: Keycloak container not found. Run 'docker compose up -d' first." >&2
  exit 1
fi
echo "Using Keycloak container: $KC"

kc() { docker exec -i "$KC" /opt/keycloak/bin/kcadm.sh "$@"; }

# --- wait for Keycloak + authenticate as the master admin --------------------
echo "Waiting for Keycloak to accept admin login..."
for i in $(seq 1 30); do
  if kc config credentials --server http://localhost:8080 --realm master \
       --user "${KEYCLOAK_ADMIN:-admin}" --password "${KEYCLOAK_ADMIN_PASSWORD:-admin}" >/dev/null 2>&1; then
    echo "  authenticated."; break
  fi
  sleep 3
  [ "$i" = 30 ] && { echo "ERROR: Keycloak not ready after 90s." >&2; exit 1; }
done

# --- realm (idempotent) ------------------------------------------------------
if kc get "realms/$REALM" >/dev/null 2>&1; then
  echo "Realm '$REALM' exists — updating settings."
  kc update "realms/$REALM" -s enabled=true -s sslRequired=NONE >/dev/null
else
  echo "Creating realm '$REALM'."
  kc create realms -s realm="$REALM" -s enabled=true -s sslRequired=NONE >/dev/null
fi

# --- realm roles -------------------------------------------------------------
for role in admin professor student; do
  kc get "roles/$role" -r "$REALM" >/dev/null 2>&1 \
    || { kc create roles -r "$REALM" -s name="$role" >/dev/null && echo "  role: $role"; }
done

# --- public client: hopper-api ----------------------------------------------
API_ID="$(kc get clients -r "$REALM" -q clientId=hopper-api --fields id --format csv --noquotes 2>/dev/null | tr -d '\r')"
if [ -z "$API_ID" ]; then
  echo "Creating public client 'hopper-api'."
  kc create clients -r "$REALM" \
    -s clientId=hopper-api -s enabled=true -s publicClient=true \
    -s standardFlowEnabled=true -s directAccessGrantsEnabled=true \
    -s fullScopeAllowed=true \
    -s "redirectUris=[\"$FRONTEND/*\",\"$GATEWAY/*\"]" \
    -s "webOrigins=[\"$FRONTEND\",\"$GATEWAY\"]" >/dev/null
  API_ID="$(kc get clients -r "$REALM" -q clientId=hopper-api --fields id --format csv --noquotes | tr -d '\r')"
else
  echo "Client 'hopper-api' exists (id=$API_ID)."
fi

# audience mapper → aud=hopper-api (gateway verifies audience=hopper-api).
# Create-or-ignore: kcadm errors "exists" on re-run, which is fine.
if kc create "clients/$API_ID/protocol-mappers/models" -r "$REALM" \
    -s name=aud-hopper-api -s protocol=openid-connect -s protocolMapper=oidc-audience-mapper \
    -s 'config."included.client.audience"=hopper-api' \
    -s 'config."access.token.claim"=true' \
    -s 'config."id.token.claim"=false' >/dev/null 2>&1; then
  echo "  added audience mapper (aud=hopper-api)."
else
  echo "  audience mapper already present."
fi

# --- confidential service-account client: hopper-admin -----------------------
ADM_ID="$(kc get clients -r "$REALM" -q clientId=hopper-admin --fields id --format csv --noquotes 2>/dev/null | tr -d '\r')"
if [ -z "$ADM_ID" ]; then
  echo "Creating confidential client 'hopper-admin'."
  kc create clients -r "$REALM" \
    -s clientId=hopper-admin -s enabled=true -s publicClient=false \
    -s serviceAccountsEnabled=true -s standardFlowEnabled=false \
    -s directAccessGrantsEnabled=false -s secret="$ADMIN_SECRET" >/dev/null
  ADM_ID="$(kc get clients -r "$REALM" -q clientId=hopper-admin --fields id --format csv --noquotes | tr -d '\r')"
else
  echo "Client 'hopper-admin' exists (id=$ADM_ID) — resetting secret."
  kc update "clients/$ADM_ID" -r "$REALM" -s secret="$ADMIN_SECRET" >/dev/null
fi
# grant the service account realm-admin (manage users, roles, sessions)
kc add-roles -r "$REALM" --uusername "service-account-hopper-admin" \
  --cclientid realm-management --rolename realm-admin >/dev/null 2>&1 || true

# --- dev users ---------------------------------------------------------------
create_user() {  # $1=username $2=password $3=realm-role $4=email
  local u="$1" p="$2" role="$3" email="$4"
  # Create (ignore "User exists"), then always (re)set password + role so the
  # step is idempotent and doesn't depend on parsing kcadm's list output.
  kc create users -r "$REALM" -s username="$u" -s enabled=true \
    -s emailVerified=true -s email="$email" -s firstName="$u" -s lastName=User >/dev/null 2>&1 || true
  kc set-password -r "$REALM" --username "$u" --new-password "$p" >/dev/null
  kc add-roles -r "$REALM" --uusername "$u" --rolename "$role" >/dev/null 2>&1 || true
  echo "  user: $u ($role)"
}
create_user admin    admin123    admin    admin@du.ac.bd
create_user testuser testuser123 student  testuser@du.ac.bd
create_user prof     prof123     professor prof@du.ac.bd

cat <<EOF

✅ Keycloak realm '$REALM' is ready.

  Dev users (realm role):
    admin    / admin123     (admin)
    testuser / testuser123  (student)
    prof     / prof123      (professor)

  For gateway admin ops (signup, role changes), run the gateway with:
    export HOPPER_KEYCLOAK_ADMIN_CLIENT_SECRET="$ADMIN_SECRET"

  Log in via the frontend login page, or the dev shortcut:
    http://localhost:5173/dev-login?as=admin
    http://localhost:5173/dev-login?as=user
EOF
