# Source upstream unchanged; register this task only.
source "$DRSI_UPSTREAM/scripts/common.sh"
select_task() {
  TASK="$1"
  [ "$TASK" = rca_re1 ] || die "this launcher runs rca_re1 only"
  TASK_KIND=root_cause ROUNDS_DEFAULT=10 EVAL_TIMEOUT_DEFAULT=14400
  TASK_DIR="$DRSI_RCA_TASK"
  PROBLEM="${DRSI_RCA_PROBLEM:-$TASK_DIR/rca.txt}"
  INIT_PROGRAM="${DRSI_RCA_INIT_PROGRAM:-$TASK_DIR/init_program.py}"
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
  [ -x "$DRSI_PROJECT/.rca-venv/bin/python" ] || die "run tasks/rca_re1/setup.sh"
  [ -f "$DRSI_PROJECT/data/rcaeval/prepared-development.json" ] || die "RE1 data not prepared"
  "$DRSI_PROJECT/.rca-venv/bin/python" - "$TASK_DIR" <<'PY' || die "benchmark source/splits failed verification"
import sys
sys.path.insert(0, sys.argv[1])
from prepare_data import verify_source, split_cases, verify_case_files
verify_source()
for kind in ("development", "evaluation", "full"):
    verify_case_files(kind, split_cases(kind))
PY
  "$DRSI_PROJECT/.rca-venv/bin/python" -c "import numpy, pandas, scipy, sklearn, networkx, pyarrow" \
    || die "missing RCA dependencies"
  "$DRSI_PROJECT/.rca-venv/bin/python" -c "import sys; sys.path.insert(0, '$DRSI_PROJECT/upstream/rcaeval'); from RCAEval.benchmark.evaluation import Evaluator" \
    || die "pinned RCAEval evaluator cannot be imported"
  local image docker_cmd
  image="$("$DRSI_PROJECT/.rca-venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["rca_worker_image"])' "$DRSI_PROJECT/tasks/rca_re1/runtime-$(hostname -s).json" 2>/dev/null)" \
    || die "RCA worker image is not installed on this host; run setup.sh"
  if docker info >/dev/null 2>&1; then docker_cmd=docker; else docker_cmd="sudo -n docker"; fi
  $docker_cmd image inspect "$image" >/dev/null 2>&1 || die "RCA worker image missing: $image"
}
