# Source upstream unchanged; register this task only.
source "$DRSI_UPSTREAM/scripts/common.sh"
select_task() {
  TASK="$1"
  [ "$TASK" = tsb_ad_u ] || die "this launcher runs tsb_ad_u only"
  TASK_KIND=anomaly_detection ROUNDS_DEFAULT=10 EVAL_TIMEOUT_DEFAULT=14400
  TASK_DIR="$DRSI_TSB_TASK"
  PROBLEM="${DRSI_TSB_PROBLEM:-$TASK_DIR/anomaly_detection.txt}"
  INIT_PROGRAM="${DRSI_TSB_INIT_PROGRAM:-$TASK_DIR/init_program.py}"
  EVALUATOR="$TASK_DIR/evaluator.py"
  EXPLORE_PROMPT="$REPO_ROOT/dream_rsi/prompts/explore.txt"
}
preflight() {
  local f
  for f in "$PROBLEM" "$EVALUATOR" "$INIT_PROGRAM" "$EXPLORE_PROMPT"; do
    [ -f "$f" ] || die "missing file: $f"
  done
  [ "$AGENT" = claude ] || die "the configured backends use AGENT=claude"
  "$PYTHON" -c "import claude_agent_sdk" 2>/dev/null || die "missing claude-agent-sdk"
  [ -x "$DRSI_CLAUDE_CLI" ] || die "Claude CLI missing"
  [ -x "$DRSI_PROJECT/.tsb-venv/bin/python" ] || die "run tasks/tsb_ad_u/setup.sh"
  [ -f "$DRSI_PROJECT/data/tsb-ad-u/prepared-development.json" ] || die "tuning data not prepared"
  "$DRSI_PROJECT/.tsb-venv/bin/python" - "$TASK_DIR" <<'PY' || die "benchmark source/splits failed verification"
import sys
sys.path.insert(0, sys.argv[1])
from prepare_data import verify_source, verify_splits
verify_source()
verify_splits()
PY
  "$DRSI_PROJECT/.tsb-venv/bin/python" -c "import numpy, pandas, scipy, sklearn, statsmodels, matplotlib" \
    || die "missing TSB dependencies"
  if [ -f "$TASK_DIR/runtime-$(hostname -s).json" ]; then
    local image
    image="$("$DRSI_PROJECT/.tsb-venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["worker_image"])' "$TASK_DIR/runtime-$(hostname -s).json")"
    docker image inspect "$image" >/dev/null 2>&1 || die "TSB worker image missing"
  else
    "$DRSI_PROJECT/.tsb-venv/bin/python" -c "import torch,sys; assert torch.backends.mps.is_available() if sys.platform == 'darwin' else torch.cuda.is_available()" || die "task accelerator unavailable"
  fi
  "$DRSI_PROJECT/.tsb-venv/bin/python" -c "import sktime,pyod,skchange,hmmlearn; assert sktime.__version__ == '0.40.1'" || die "LibraryTS toolbox missing"
}
