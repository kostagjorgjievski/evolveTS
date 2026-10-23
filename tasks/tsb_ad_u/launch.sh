#!/usr/bin/env bash
# DREAM-RSI paper protocol on tsb_ad_u: runs the pinned upstream
# run_e0.sh, run_dream_rsi.sh or run_baseline.sh verbatim, with this task
# added, the selected backend (BACKEND=glm|deepseek|minimax) and per-call
# accounting. Settings are the upstream environment variables (ROUNDS,
# BRANCHES, REFINE, MAX_WORKERS, E0_WORKSPACE, RESUME, DRY_RUN, ...); their
# defaults are the paper's.
#
#   bash tasks/tsb_ad_u/launch.sh e0
#   E0_WORKSPACE=runs/anomaly_detection/tsb_ad_u/e0/tsb_ad_u-$(hostname -s) \
#     bash tasks/tsb_ad_u/launch.sh dream_rsi
#   E0_WORKSPACE=... bash tasks/tsb_ad_u/launch.sh baseline
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK="$ROOT/tasks/tsb_ad_u"
UPSTREAM="$ROOT/upstream/dream-rsi"
case "${1:-}" in
  e0 | dream_rsi | baseline) METHOD="$1" ;;
  *) echo "usage: bash tasks/tsb_ad_u/launch.sh e0|dream_rsi|baseline" >&2; exit 2 ;;
esac
HOST="$(hostname -s)"

test "$(git -C "$UPSTREAM" rev-parse HEAD)" = 8ec35bd2538220517ce1bfca4282db21b8c518db
test -z "$(git -C "$UPSTREAM" status --porcelain -- scripts dream_rsi/prompts)"

source "$ROOT/configs/tsb_ad_u.env"
HOST_PROFILE="$ROOT/configs/hosts/$HOST.json"
if [ -f "$HOST_PROFILE" ]; then
  export DRSI_CLAUDE_CLI="$("$ROOT/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["claude_cli"])' "$HOST_PROFILE")"
fi
# BACKEND selects the coding model behind the Claude CLI. Compared runs (E0,
# dream_rsi, baseline) must all use the same one.
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
    export ANTHROPIC_SMALL_FAST_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_HAIKU_MODEL="$ANTHROPIC_MODEL" \
      ANTHROPIC_DEFAULT_SONNET_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_OPUS_MODEL="$ANTHROPIC_MODEL"
    SUFFIX=-minimax
    ;;
  deepseek)
    # Paratera's Anthropic-compatible /v1/messages endpoint. The env file sets
    # DEEPSEEK_API_KEY and may override DEEPSEEK_BASE_URL and DEEPSEEK_MODEL.
    source "$ROOT/.credentials/deepseek.env"
    ANTHROPIC_BASE_URL="${DEEPSEEK_BASE_URL:-https://llmapi.paratera.com}"
    ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"
    ANTHROPIC_MODEL="${DEEPSEEK_MODEL:-DeepSeek-V4.1-Flash-1017}"
    # Background and subagent calls must not fall back to Claude model names.
    export ANTHROPIC_SMALL_FAST_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_HAIKU_MODEL="$ANTHROPIC_MODEL" \
      ANTHROPIC_DEFAULT_SONNET_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_OPUS_MODEL="$ANTHROPIC_MODEL"
    export CLAUDE_CONFIG_DIR="$ROOT/.credentials/claude-deepseek"
    (umask 077; mkdir -p "$CLAUDE_CONFIG_DIR")
    SUFFIX=-deepseek
    ;;
  *) echo "BACKEND must be glm, deepseek or minimax (got '$BACKEND')" >&2; exit 2 ;;
esac
export ANTHROPIC_BASE_URL ANTHROPIC_MODEL ANTHROPIC_AUTH_TOKEN
export DRSI_BACKEND="${BACKEND}_cli"
# Optional extra keys, one per line, from separate provider accounts (rate limits
# are per account); each key then serves at most DRSI_KEY_MAX_SESSIONS sessions.
if [ -f "$ROOT/.credentials/$BACKEND-keys.txt" ]; then
  export DRSI_KEY_POOL_FILE="$ROOT/.credentials/$BACKEND-keys.txt"
  export DRSI_KEY_MAX_SESSIONS="${DRSI_KEY_MAX_SESSIONS:-3}"
fi
unset ANTHROPIC_API_KEY HTTP_PROXY HTTPS_PROXY ALL_PROXY
export PATH="$ROOT/.venv/bin:$ROOT/tools/node_modules/.bin:$PATH"
export DRSI_AGENT_BUDGET_FILE="${DRSI_AGENT_BUDGET_FILE:-$ROOT/runs/anomaly_detection/tsb_ad_u-accounting/budget.json}"
if [ "$BACKEND" = minimax ] && [ "$DRSI_AGENT_BUDGET_FILE" = "$ROOT/runs/anomaly_detection/tsb_ad_u-accounting/budget.json" ]; then
  export DRSI_AGENT_BUDGET_FILE="${DRSI_AGENT_BUDGET_FILE%/budget.json}/minimax/budget.json"
fi
export DRSI_PROJECT="$ROOT" DRSI_UPSTREAM="$UPSTREAM" DRSI_TSB_TASK="$TASK"
export DRSI_REAL_PYTHON="$ROOT/.venv/bin/python"
export PYTHON="$TASK/drsi/python"
# Fresh workspaces are independent per host and task.
export WORKSPACE="${WORKSPACE:-$ROOT/runs/anomaly_detection/tsb_ad_u/$METHOD/tsb_ad_u-$HOST$SUFFIX}"

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/tsb-drsi-launch.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
cp "$UPSTREAM/scripts/run_$METHOD.sh" "$STAGE/"
cp "$TASK/drsi/common.sh" "$STAGE/common.sh"

if [ "${DRY_RUN:-0}" != 1 ]; then
  # One-token requests first, with every key: a refused key would otherwise only
  # stop the run at its first agent call. Once one works, an earlier access stop is resolved.
  "$ROOT/.venv/bin/python" "$ROOT/scripts/preflight_keys.py" || { echo "error: no usable $BACKEND key" >&2; exit 2; }
  MARKER="$(dirname "$DRSI_AGENT_BUDGET_FILE")/ACCESS_ERROR.json"
  if [ -f "$MARKER" ]; then
    mv "$MARKER" "$MARKER.resolved-$(date -u +%Y%m%dT%H%M%SZ)"
    echo "[launch] $BACKEND access works again; earlier access stop marked resolved"
  fi

  # Record the exact task, backend and launcher of every start or resume.
  CONFIG="$WORKSPACE.config/$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$CONFIG"
  cp "$TASK/protocol.json" "$TASK/anomaly_detection.txt" "$TASK/init_program.py" "$TASK/evaluator.py" \
     "$TASK/evaluate_cli.py" "$TASK/worker.py" "$TASK/sandbox.py" "$TASK/prepare_data.py" "$TASK/launch.sh" \
     "$TASK/drsi/common.sh" "$ROOT/configs/tsb_ad_u.env" "$CONFIG/"
  cp "$TASK/Dockerfile.sp1" "$TASK/setup.sh" "$CONFIG/"
  cp "$TASK/libraryts.json" "$TASK/requirements-libraryts.txt" "$TASK/macos_sandbox.py" "$CONFIG/"
  if [ -n "${DRSI_TSB_INIT_PROGRAM:-}" ]; then cp "$DRSI_TSB_INIT_PROGRAM" "$CONFIG/init_program.py"; fi
  if [ -n "${DRSI_TSB_PROBLEM:-}" ]; then cp "$DRSI_TSB_PROBLEM" "$CONFIG/anomaly_detection.txt"; fi
  if [ -f "$TASK/runtime-$HOST.json" ]; then cp "$TASK/runtime-$HOST.json" "$CONFIG/task-runtime.json"; fi
  if [ -f "$HOST_PROFILE" ]; then cp "$HOST_PROFILE" "$CONFIG/host.json"; fi
  git -C "$UPSTREAM" rev-parse HEAD > "$CONFIG/dream-rsi-commit"
  printf '%s\n' "$HOST" > "$CONFIG/hostname"
  printf '%s\n' "$ANTHROPIC_MODEL" > "$CONFIG/coding-model"
  printf '%s\n' "$BACKEND" > "$CONFIG/backend"
  env | grep -E '^(ROUNDS|BRANCHES|REFINE|MAX_WORKERS|EVAL_TIMEOUT|DISCOVER_[A-Z_]+|E0_WORKSPACE|RESUME|GUIDANCE)=' \
    > "$CONFIG/overrides.env" || true
fi
bash "$STAGE/run_$METHOD.sh" tsb_ad_u
