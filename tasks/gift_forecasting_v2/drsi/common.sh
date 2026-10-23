# shellcheck shell=bash
# Upstream launch-script settings with gift_forecasting_v2 added as a task.
# launch.sh places this file next to verbatim copies of the pinned upstream
# run_*.sh scripts, which source it instead of upstream's common.sh.
source "$DRSI_UPSTREAM/scripts/common.sh"

# Evaluations queue for a GPU slot (shared with tasks/gift_forecasting), and one
# v2 evaluation may take up to protocol.json evaluation_seconds (3600) once it has
# a slot, so the explore eval timeout, which includes waiting, is three times that.
select_task() {
  TASK="$1"
  [ "$TASK" = gift_forecasting_v2 ] || die "this launcher runs gift_forecasting_v2 only (got '$TASK')"
  TASK_KIND=forecasting ROUNDS_DEFAULT=10 EVAL_TIMEOUT_DEFAULT=10800
  TASK_DIR="$DRSI_FORECAST_TASK"
  PROBLEM="$TASK_DIR/forecasting.txt"
  INIT_PROGRAM="$TASK_DIR/init_program.py"
  EVALUATOR="$TASK_DIR/evaluator.py"
  EXPLORE_PROMPT="$REPO_ROOT/dream_rsi/prompts/explore.txt"
}

preflight() {
  local f
  for f in "$PROBLEM" "$EVALUATOR" "$INIT_PROGRAM" "$EXPLORE_PROMPT"; do
    [ -f "$f" ] || die "missing file: $f"
  done
  [ "$AGENT" = claude ] || die "the forecasting backends run through AGENT=claude (got '$AGENT')"
  "$PYTHON" -c "import claude_agent_sdk" 2>/dev/null || die "claude-agent-sdk is not installed"
  [ -x "$DRSI_CLAUDE_CLI" ] || die "Claude CLI not found: $DRSI_CLAUDE_CLI"
  [ -x "$DRSI_PROJECT/.gift-venv/bin/python" ] || die "missing .gift-venv (run scripts/setup_forecasting.sh)"
  [ -f "$DRSI_PROJECT/data/gift-eval/prepared-full.json" ] || die "full GIFT-Eval data not prepared"
  [ -f "$TASK_DIR/reference_seasonal_naive.json" ] || die "missing reference (run make_reference.py)"
  # Candidates run in the host profile's v2 worker image, with the checkpoints mounted.
  local profile="$DRSI_PROJECT/configs/hosts/$(hostname -s).json" image models
  image="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("gift_v2_worker_image",""))' "$profile")"
  [ -n "$image" ] || die "no gift_v2_worker_image in $profile"
  docker image inspect "$image" >/dev/null 2>&1 || die "the v2 worker image is missing: $image"
  models="$("$PYTHON" -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]).resolve(); print((p.parents[2]/json.load(open(p))["models_host_dir"]).resolve())' "$TASK_DIR/protocol.json")"
  [ -d "$models" ] || die "missing checkpoints: $models"
  "$DRSI_PROJECT/.gift-venv/bin/python" - "$TASK_DIR" <<'PY' || die "v2 reference/checkpoints failed verification"
import hashlib, json, sys
from pathlib import Path
task = Path(sys.argv[1])
protocol = json.loads((task / "protocol.json").read_text())
reference = json.loads((task / protocol["reference_file"]).read_text())
assert reference["program_sha256"] == hashlib.sha256((task / "init_program.py").read_bytes()).hexdigest(), "stale seed reference"
assert reference["data_revision"] == protocol["data_revision"], "stale data reference"
assert reference["development"] == protocol["development"], "stale development reference"
assert sorted(row["dataset"] for row in reference["rows"]) == sorted(row["key"] for row in protocol["development"]), "incomplete reference"
for name, model in protocol["models"].items():
    directory = (task.parents[1] / protocol["models_host_dir"]).resolve() / Path(model["path"]).name
    assert directory.is_dir(), f"missing checkpoint: {name}"
    assert any(f.is_file() and f.stat().st_size > 1024**2 for f in directory.rglob("*")), f"empty checkpoint: {name}"
PY
  "$DRSI_PROJECT/.gift-venv/bin/python" -c "import gluonts" 2>/dev/null || die ".gift-venv cannot import gluonts"
}
