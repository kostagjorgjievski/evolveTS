"""Run validation or explicitly frozen final GIFT-Eval scoring."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from evaluator import METRIC_NAMES, gpu_turn, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True, type=Path)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--frozen-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.program.read_bytes()
    if args.test:
        actual = hashlib.sha256(source).hexdigest()
        if actual != args.frozen_sha256 or args.output is None:
            parser.error("Test requires --frozen-sha256 matching program and a fresh --output directory")
    if args.full and not args.test:
        parser.error("--full is reserved for frozen final test evaluation")
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        args.program = args.output / "program.py"
        args.program.write_bytes(source)
    with gpu_turn():
        result = run(args.program, "test" if args.test else "validation", args.full)
    if args.output:
        (args.output / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
        fields = ["dataset", "model"] + ["eval_metrics/" + key for key in METRIC_NAMES] + ["domain", "num_variates"]
        with (args.output / "all_results.csv").open("w") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(dict(row, model=args.output.name) for row in result["rows"])
    print(json.dumps(result))


if __name__ == "__main__":
    main()
