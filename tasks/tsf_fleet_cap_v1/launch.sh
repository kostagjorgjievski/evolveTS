#!/usr/bin/env bash
# DREAM-RSI launcher for tsf_fleet_cap_v1: runs the pinned upstream
# run_e0.sh, run_dream_rsi.sh or run_baseline.sh verbatim, with this task
# added, the selected backend (BACKEND=glm|deepseek|minimax) and per-call
# accounting. Settings are the upstream environment variables (ROUNDS,
# BRANCHES, REFINE, MAX_WORKERS, E0_WORKSPACE, RESUME, DRY_RUN, ...).
#
#   bash tasks/tsf_fleet_cap_v1/launch.sh e0
#   E0_WORKSPACE=runs/tsf_fleet_cap_v1/e0/<ws> \
#     bash tasks/tsf_fleet_cap_v1/launch.sh dream_rsi
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK="$ROOT/tasks/tsf_fleet_cap_v1"
UPSTREAM="$ROOT/upstream/dream-rsi"
case "${1:-}" in
  e0 | dream_rsi | baseline) METHOD="$1" ;;
  *) echo "usage: bash tasks/tsf_fleet_cap_v1/launch.sh e0|dream_rsi|baseline" >&2; exit 2 ;;
esac
HOST="$(hostname -s)"

test "$(git -C "$UPSTREAM" rev-parse HEAD)" = 8ec35bd2538220517ce1bfca4282db21b8c518db
test -z "$(git -C "$UPSTREAM" status --porcelain -- scripts dream_rsi/prompts)"

source "$ROOT/configs/tsf_fleet_cap_v1.env"
HOST_PROFILE="$ROOT/configs/hosts/$HOST.json"
if [ -f "$HOST_PROFILE" ]; then
  export DRSI_CLAUDE_CLI="$("$ROOT/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["claude_cli"])' "$HOST_PROFILE")"
fi
BACKEND="${BACKEND:-minimax}"
case "$BACKEND" in
  glm)
    source "$ROOT/.credentials/glm.env"
    export CLAUDE_CONFIG_DIR="$ROOT/.credentials/claude-glm"
    SUFFIX=-glm
    ;;
  minimax)
    unset DRSI_KEY_POOL_FILE
    if [ "${DRY_RUN:-0}" != 1 ]; then
      test -f "$ROOT/.credentials/minimax.env" || { echo "Copy configs/provider.env.example to .credentials/minimax.env and set your own credentials" >&2; exit 2; }
      source "$ROOT/.credentials/minimax.env"
    fi
    export CLAUDE_CONFIG_DIR="$ROOT/.credentials/claude-minimax"
    (umask 077; mkdir -p "$CLAUDE_CONFIG_DIR")
    export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-}"
    export ANTHROPIC_SMALL_FAST_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_HAIKU_MODEL="$ANTHROPIC_MODEL" \
      ANTHROPIC_DEFAULT_SONNET_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_OPUS_MODEL="$ANTHROPIC_MODEL"
    SUFFIX=-minimax
    ;;
  deepseek)
    source "$ROOT/.credentials/deepseek.env"
    ANTHROPIC_BASE_URL="${DEEPSEEK_BASE_URL:-https://llmapi.paratera.com}"
    ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"
    ANTHROPIC_MODEL="${DEEPSEEK_MODEL:-DeepSeek-V4.1-Flash-1017}"
    export ANTHROPIC_SMALL_FAST_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_HAIKU_MODEL="$ANTHROPIC_MODEL" \
      ANTHROPIC_DEFAULT_SONNET_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_OPUS_MODEL="$ANTHROPIC_MODEL"
    export CLAUDE_CONFIG_DIR="$ROOT/.credentials/claude-deepseek"
    (umask 077; mkdir -p "$CLAUDE_CONFIG_DIR")
    SUFFIX=-deepseek
    ;;
  *) echo "BACKEND must be glm, deepseek or minimax (got '$BACKEND')" >&2; exit 2 ;;
esac
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-}" ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-}" ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-}"
export DRSI_BACKEND="${BACKEND}_cli"
if [ -f "$ROOT/.credentials/$BACKEND-keys.txt" ]; then
  export DRSI_KEY_POOL_FILE="$ROOT/.credentials/$BACKEND-keys.txt"
  export DRSI_KEY_MAX_SESSIONS="${DRSI_KEY_MAX_SESSIONS:-3}"
fi
unset ANTHROPIC_API_KEY HTTP_PROXY HTTPS_PROXY ALL_PROXY
export PATH="$ROOT/.venv/bin:$ROOT/tools/node_modules/.bin:$PATH"
export DRSI_AGENT_BUDGET_FILE="$ROOT/runs/tsf_fleet_cap_v1-accounting/budget.json"
unset DRSI_KEY_POOL_STATE
export DRSI_PROJECT="$ROOT" DRSI_UPSTREAM="$UPSTREAM" DRSI_FORECAST_TASK="$TASK"
export DRSI_REAL_PYTHON="$ROOT/.venv/bin/python"
export PYTHON="$TASK/drsi/python"
# Fresh workspaces are independent per host and task.
export WORKSPACE="${WORKSPACE:-$ROOT/runs/tsf_fleet_cap_v1/$METHOD/tsf_fleet_cap_v1-$HOST$SUFFIX}"

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/tsf-drsi-launch.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
cp "$UPSTREAM/scripts/run_$METHOD.sh" "$STAGE/"
cp "$TASK/drsi/common.sh" "$STAGE/common.sh"

if [ "${DRY_RUN:-0}" != 1 ]; then
  "$ROOT/.venv/bin/python" "$ROOT/scripts/preflight_keys.py" || { echo "error: no usable $BACKEND key" >&2; exit 2; }
  MARKER="$(dirname "$DRSI_AGENT_BUDGET_FILE")/ACCESS_ERROR.json"
  if [ -f "$MARKER" ]; then
    mv "$MARKER" "$MARKER.resolved-$(date -u +%Y%m%dT%H%M%SZ)"
    echo "[launch] $BACKEND access works again; earlier access stop marked resolved"
  fi

  CONFIG="$WORKSPACE.config/$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$CONFIG"
  cp "$TASK/protocol.json" "$TASK/fleet.txt" "$TASK/init_program.py" \
     "$TASK/evaluator.py" "$TASK/evaluator_core.py" "$TASK/runner.py" \
     "$TASK/audits.py" "$TASK/generator.py" "$TASK/evaluate_cli.py" \
     "$TASK/make_reference.py" "$TASK/launch.sh" \
     "$TASK/drsi/common.sh" "$ROOT/configs/tsf_fleet_cap_v1.env" "$CONFIG/"
  cp "$TASK/reference_starter.json" "$CONFIG/" 2>/dev/null || true
  if [ -f "$HOST_PROFILE" ]; then cp "$HOST_PROFILE" "$CONFIG/host.json"; fi
  git -C "$UPSTREAM" rev-parse HEAD > "$CONFIG/dream-rsi-commit"
  printf '%s\n' "$HOST" > "$CONFIG/hostname"
  printf '%s\n' "$ANTHROPIC_MODEL" > "$CONFIG/coding-model"
  printf '%s\n' "$BACKEND" > "$CONFIG/backend"
  env | grep -E '^(ROUNDS|BRANCHES|REFINE|MAX_WORKERS|EVAL_TIMEOUT|DISCOVER_[A-Z_]+|E0_WORKSPACE|RESUME|GUIDANCE)=' \
    > "$CONFIG/overrides.env" || true
fi
bash "$STAGE/run_$METHOD.sh" tsf_fleet_cap_v1
