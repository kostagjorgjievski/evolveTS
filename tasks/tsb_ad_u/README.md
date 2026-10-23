# TSB-AD-U anomaly task

See the [root setup guide](../../README.md). This adapter preserves the pinned
TSB-AD loader, split lists and primary VUS/AUC calculations. Development uses
all 48 tuning series; any failed series fails the entire candidate. Full
unlabelled offline input and the official normal training prefix are permitted.
The seed is a minimal median/MAD detector. Method selection remains open.
LibraryTS is an optional installed toolbox, not a replacement evaluator.

Interface: `detect(data, train_data, metadata) -> scores[N]`, finite real scores,
larger meaning more anomalous. Budget: 120 seconds per series, one numerical
thread, 8 GiB host RSS, and the configured CUDA/MPS evaluation slot. Model fit
and inference both count; candidate network access is denied.

Install with `bash tasks/tsb_ad_u/setup.sh`, then launch a fresh E0 through
`scripts/run_fresh.sh tsb_ad_u`. No campaigns or discovered detector programs
are shipped. The original Dream-RSI prompt requires full historical proposal
and score reading; the path-index wrapper only fixes symlink discovery.

Final evaluation is explicit and cannot feed discovery:

```bash
PROGRAM=/absolute/path/to/selected/program.py
HASH=$(shasum -a 256 "$PROGRAM" | cut -d ' ' -f 1)
.tsb-venv/bin/python tasks/tsb_ad_u/evaluate_cli.py \
  --program "$PROGRAM" --test --frozen-sha256 "$HASH" --output outputs/final-anomaly
```

Check `evaluate_cli.py --help` for the optional full822 list and secondary
metrics. Outputs must use a fresh directory. Hardware-specific runtime profiles
are generated locally and excluded from Git.
