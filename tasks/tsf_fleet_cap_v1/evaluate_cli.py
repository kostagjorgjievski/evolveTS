"""CLI verifier for tsf_fleet_cap_v1.

  development (default): public verifier on the pinned development timeline;
  --final:               private verifier (secret seed, novel regime mix,
                         full budgets, full fleet, starter re-scored on the
                         same private timeline);
  --grade-checkpoints DIR: re-grade saved replay checkpoints on a held-out
                         continuation of the development timeline (detects
                         state that degrades silently or smuggles information).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK_DIR))

import evaluator_core  # noqa: E402


def cmd_final(args) -> int:
    result = evaluator_core.evaluate(args.program, mode="final", out_dir=args.out)
    print(json.dumps(result, indent=2, default=str))
    if "violation" in result:
        print(f"\nPRIVATE VERDICT: violation ({result['violation']})", file=sys.stderr)
        return 1
    print(f"\nPRIVATE VERDICT: combined_score={result['combined_score']:.6g}")
    return 0


def cmd_grade_checkpoints(args) -> int:
    ckpt_dir = Path(args.dir)
    states = sorted(ckpt_dir.glob("state_day_*.bin"))
    if not states:
        print("no checkpoints found", file=sys.stderr)
        return 2
    report = evaluator_core.grade_checkpoints(args.program, states,
                                              extra_hours=args.extra_hours)
    print(json.dumps(report, indent=2, default=str))
    bad = [r for r in report["items"] if r.get("flagged")]
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--grade-checkpoints", dest="dir", default=None)
    ap.add_argument("--extra-hours", type=int, default=24)
    args = ap.parse_args()
    if args.dir:
        return cmd_grade_checkpoints(args)
    if args.final:
        return cmd_final(args)
    result = evaluator_core.evaluate(args.program, mode="development", out_dir=args.out)
    print(json.dumps(result, indent=2, default=str))
    if "violation" in result:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
