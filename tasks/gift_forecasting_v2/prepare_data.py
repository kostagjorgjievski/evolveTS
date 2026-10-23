"""Fetch exact data revision; default downloads only development datasets."""
import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download
from evaluator import PROTOCOL, ROOT, official_configurations

parser = argparse.ArgumentParser()
parser.add_argument("--full", action="store_true")
parser.add_argument("--destination", type=Path, default=ROOT / "data/gift-eval")
args = parser.parse_args()
all_configs = official_configurations()
keys = {row["key"] for row in PROTOCOL["development"]}
configs = all_configs if args.full else [row for row in all_configs if row["key"] in keys]
names = sorted({config["name"] for config in configs})
snapshot_download(repo_id=PROTOCOL["data_repo"], repo_type="dataset",
                  revision=PROTOCOL["data_revision"], local_dir=args.destination,
                  allow_patterns=[name + "/*" for name in names], max_workers=4)
(args.destination / "REVISION").write_text(PROTOCOL["data_revision"] + "\n")
(args.destination / ("prepared-full.json" if args.full else "prepared-development.json")).write_text(
    json.dumps({"revision": PROTOCOL["data_revision"], "datasets": names}, indent=2) + "\n")
