"""Compute and pin the development reference for tsf_fleet_cap_v1.

Runs the starter (init_program.py) through the exact development replay and
stores per-group CRPS plus the canary baseline. The evaluator refuses to score
against a reference whose program hash does not match the current starter.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK_DIR))

import evaluator_core  # noqa: E402


def main() -> int:
    starter = TASK_DIR / "init_program.py"
    protocol = json.loads((TASK_DIR / "protocol.json").read_text())
    result = evaluator_core.compute_reference(str(starter))
    reference = {
        "program": "init_program.py",
        "program_sha256": hashlib.sha256(starter.read_bytes()).hexdigest(),
        "mode": "development",
        "development_params": protocol["development"],
        "groups": result["groups"],
        "canary_crps": result["canary_crps"],
        "timings": result["timings"],
    }
    out = TASK_DIR / protocol["reference_file"]
    out.write_text(json.dumps(reference, indent=2))
    print(f"wrote {out}")
    print(json.dumps(reference["groups"], indent=2))
    print(f"canary_crps={reference['canary_crps']:.6g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
