#!/usr/bin/env bash

set -euo pipefail

BASE_URL="${BASE_URL:-https://hopper.farefin.com}"

status() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$BASE_URL$1"
}

assert_status() {
  local path="$1" expected="$2" got
  got="$(status "$path")"
  if [[ "$got" != "$expected" ]]; then
    echo "FAIL $path: expected $expected, got $got" >&2
    exit 1
  fi
  echo "OK   $path -> $got"
}

assert_not_status() {
  local path="$1" forbidden="$2" got
  got="$(status "$path")"
  if [[ "$got" == "$forbidden" ]]; then
    echo "FAIL $path: got forbidden status $forbidden" >&2
    exit 1
  fi
  echo "OK   $path -> $got (not $forbidden)"
}

assert_status "/api/healthz" "200"
assert_status "/dev-login" "404"
assert_status "/api/auth/me" "401"
assert_not_status "/api/openapi.json" "200"
assert_not_status "/api/docs" "200"
assert_not_status "/admin/master/console/" "200"
