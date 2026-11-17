"""Engine-facing evaluator for tsf_fleet_cap_v1 (stdlib-only stub).

The upstream runner imports this module and calls evaluate(program_path) under
the project's engine python (which has no numpy). The stub re-executes the real
verifier (evaluator_core.py) under the task's .tsf-venv interpreter and relays
its JSON result. Set TSF_PYTHON to override the interpreter path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
DEFAULT_PY = TASK_DIR.parents[1] / ".tsf-venv" / "bin" / "python"


def evaluate(program_path: str) -> dict:
    python = os.environ.get("TSF_PYTHON") or str(DEFAULT_PY)
    if not Path(python).exists():
        return {"error": f"missing task interpreter: {python}", "combined_score": 0.0}
    program_path = str(Path(program_path).resolve())
    proc = subprocess.run(
        [python, str(TASK_DIR / "evaluator_core.py"),
         "--program", str(program_path), "--mode", "development"],
        capture_output=True, text=True, timeout=2400,
        cwd=str(TASK_DIR))
    result = None
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if result is None:
        return {"error": f"verifier produced no JSON (exit {proc.returncode}): "
                         f"{(proc.stderr or '')[-800:]}",
                "combined_score": 0.0}
    return result


if __name__ == "__main__":
    print("\n__DRSI_RESULT__ " + json.dumps(evaluate(sys.argv[1] if len(sys.argv) > 1 else "")))
