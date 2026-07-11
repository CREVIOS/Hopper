#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must point to the staging database}"

ledger_sum=$(psql "$DATABASE_URL" -Atc \
  "SELECT COALESCE(SUM(CASE WHEN direction = 1 THEN amount ELSE -amount END), 0) FROM ledger_entries;")
test "$ledger_sum" = "0.0000" || test "$ledger_sum" = "0"

negative_balances=$(psql "$DATABASE_URL" -Atc \
  "SELECT COUNT(*) FROM (SELECT DISTINCT ON (account_id) current_balance FROM ledger_entries ORDER BY account_id, created_at DESC) balances WHERE current_balance < 0;")
test "$negative_balances" = "0"

active_sessions=$(psql "$DATABASE_URL" -Atc \
  "SELECT COUNT(*) FROM pod_sessions WHERE state = 'running';")
running_pods=$(kubectl get pods -n hopper -l app.kubernetes.io/component=student-pod \
  --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
test "$running_pods" = "$active_sessions"

kubectl get namespaces -o name >/dev/null
nats stream report
