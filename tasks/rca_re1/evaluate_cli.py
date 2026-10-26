"""Development scoring or explicitly frozen final RCAEval RE1 evaluation."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

# Apply before any scientific package imports, including direct CLI calls.
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

from evaluator import METRIC_NAMES, gpu_turn, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True, type=Path)
    parser.add_argument("--test", action="store_true",
                        help="score the held-out 300-case RE1 split")
    parser.add_argument("--full", action="store_true",
                        help="score all 375 RE1 cases (frozen final evaluation only)")
    parser.add_argument("--frozen-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.program.read_bytes()
    if args.test and (hashlib.sha256(source).hexdigest() != args.frozen_sha256 or args.output is None):
        parser.error("Test requires matching --frozen-sha256 and a fresh --output directory")
    if args.full and not args.test:
        parser.error("--full is reserved for frozen final evaluation")
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        args.program = args.output / "program.py"
        args.program.write_bytes(source)
    with gpu_turn():
        result = run(args.program, "full" if args.full else "evaluation" if args.test else "development")
    if args.output:
        (args.output / "protocol.json").write_bytes(Path(__file__).with_name("protocol.json").read_bytes())
        (args.output / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
        fields = ["case", "system", "fault", "length", "metrics", "services",
                  "candidate_seconds"] + METRIC_NAMES
        with (args.output / "all_results.csv").open("w") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(result["rows"])
    print(json.dumps(result))


if __name__ == "__main__":
    main()
