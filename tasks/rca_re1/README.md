# RCAEval RE1 root-cause task

See the [root setup guide](../../README.md). This adapter preserves the pinned
RCAEval RE1 metric corpus, its official preprocessing and its official
`Evaluator` (AC@1/3/5 and Avg@5 at service and metric level). Development uses
one repetition of every (system, root-cause service, fault) stratum: 75 cases
across Online Boutique, Sock Shop and TrainTicket. Any failed case fails the
entire candidate. The seed is a minimal robust-deviation ranker; method
selection remains open.

Interface: `rank(data, inject_time, metadata) -> list[str]`, a permutation of
every metric column, most suspicious first. Inputs are the official 600+600-row
window around `inject_time` after the official `time.1`/`latency-50`/inf/ffill/
fillna/`latency-90` preprocessing. Budget: 120 seconds per case including
container startup, one CPU thread, 8 GiB host RSS, and the configured CUDA
evaluation slot. Candidate network access is denied; case identity, root-cause
service and fault type are never exposed. The SLI column is the fixed
per-system indicator, not the ground-truth service's latency.

Install with `bash tasks/rca_re1/setup.sh` (Linux CUDA + Docker), then launch a
fresh E0 through `scripts/run_fresh.sh rca_re1`. Data is downloaded at the
pinned Hugging Face revision; set `HF_ENDPOINT` if `huggingface.co` is not
reachable (setup auto-selects `https://hf-mirror.com` when needed). The original
Dream-RSI prompt requires full historical proposal and score reading; the
path-index wrapper only fixes symlink discovery.

Final evaluation is explicit and cannot feed discovery:

```bash
PROGRAM=/absolute/path/to/selected/program.py
HASH=$(sha256sum "$PROGRAM" | cut -d ' ' -f 1)
.rca-venv/bin/python tasks/rca_re1/evaluate_cli.py \
  --program "$PROGRAM" --test --frozen-sha256 "$HASH" --output outputs/final-rca
```

`--test` scores the 300 held-out RE1 cases; add `--full` to score all 375.
Outputs must use a fresh directory. Development scores cannot establish
leaderboard rank or a controller improvement claim.
