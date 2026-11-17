# shellcheck shell=bash
# Upstream launch-script settings with tsf_fleet_cap_v1 added as a task.
# launch.sh places this file next to verbatim copies of the pinned upstream
# run_*.sh scripts, which source it instead of upstream's common.sh.
source "$DRSI_UPSTREAM/scripts/common.sh"

# Evaluations run on host (no Docker on this deployment); a dev evaluation
# leases one GPU for its train phase and finishes well inside 30 minutes, so
# the explore eval timeout is 45 minutes including queueing.
select_task() {
  TASK="$1"
  [ "$TASK" = tsf_fleet_cap_v1 ] || die "this launcher runs tsf_fleet_cap_v1 only (got '$TASK')"
  TASK_KIND=forecasting ROUNDS_DEFAULT=10 EVAL_TIMEOUT_DEFAULT=2700
  TASK_DIR="$DRSI_FORECAST_TASK"
  PROBLEM="$TASK_DIR/fleet.txt"
  INIT_PROGRAM="$TASK_DIR/init_program.py"
  EVALUATOR="$TASK_DIR/evaluator.py"
  EXPLORE_PROMPT="$REPO_ROOT/dream_rsi/prompts/explore.txt"
}

preflight() {
  local f
  for f in "$PROBLEM" "$EVALUATOR" "$INIT_PROGRAM" "$EXPLORE_PROMPT"; do
    [ -f "$f" ] || die "missing file: $f"
  done
  [ "$AGENT" = claude ] || die "the configured backends run through AGENT=claude (got '$AGENT')"
  "$PYTHON" -c "import claude_agent_sdk" 2>/dev/null || die "claude-agent-sdk is not installed"
  [ -x "$DRSI_CLAUDE_CLI" ] || die "Claude CLI not found: $DRSI_CLAUDE_CLI"
  [ -x "$DRSI_PROJECT/.tsf-venv/bin/python" ] || die "missing .tsf-venv (run tasks/tsf_fleet_cap_v1/setup.sh)"
  "$DRSI_PROJECT/.tsf-venv/bin/python" -c "import numpy, torch" 2>/dev/null \
    || die ".tsf-venv cannot import numpy/torch (run tasks/tsf_fleet_cap_v1/setup.sh)"
  [ -f "$TASK_DIR/reference_starter.json" ] || die "missing reference (run make_reference.py)"
  # The pinned reference must match the current starter and protocol.
  "$DRSI_PROJECT/.tsf-venv/bin/python" - "$TASK_DIR" <<'PY' || die "stale task reference"
import hashlib, json, sys
from pathlib import Path
task = Path(sys.argv[1])
protocol = json.loads((task / "protocol.json").read_text())
reference = json.loads((task / protocol["reference_file"]).read_text())
assert reference["program_sha256"] == hashlib.sha256((task / "init_program.py").read_bytes()).hexdigest(), "stale seed reference"
assert reference["development_params"] == protocol["development"], "stale development parameters"
assert set(reference["groups"]) >= {"smooth", "diurnal", "spiky", "episodic", "volatile", "coldstart"}, "incomplete reference groups"
PY
  command -v nvidia-smi >/dev/null 2>&1 || die "nvidia-smi not found; the train phase needs a GPU"
  [ "$(nvidia-smi -L 2>/dev/null | grep -c '^GPU ')" -ge 1 ] || die "no GPUs visible"
}
