#!/usr/bin/env bash
# Run E0 then the original Dream-RSI continuation in new independent workspaces.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
case "${1:-}" in tsb_ad_u|gift_forecasting_v2|rca_re1) TASK="$1";; *) echo 'usage: scripts/run_fresh.sh tsb_ad_u|gift_forecasting_v2|rca_re1' >&2; exit 2;; esac
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
export BACKEND="${BACKEND:-minimax}"
E0="$ROOT/runs/$TASK/e0/$STAMP"
NEXT="$ROOT/runs/$TASK/dream_rsi/$STAMP"
WORKSPACE="$E0" bash "tasks/$TASK/launch.sh" e0
E0_WORKSPACE="$E0" WORKSPACE="$NEXT" bash "tasks/$TASK/launch.sh" dream_rsi
