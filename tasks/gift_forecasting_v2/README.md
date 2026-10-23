# GIFT-Eval forecasting v2

See the [root setup guide](../../README.md). This is the current CRPS-only
forecasting adapter. It provides a minimal seasonal-naive seed, 24 development
configurations from seven domains, a fixed evaluator and an optional pool of
seven pretrained models. Agents choose statistical, fitted, foundation-model
or combined approaches. Candidate network access is denied.

Interfaces: optional `fit(training_series, metadata) -> state`, followed by
`forecast(histories, horizon, metadata, state) -> {mean, quantiles}`. Shapes are
`[N,H]` and `[N,11,H]`. Quantiles must be finite and ordered. Metadata and
training inputs contain permitted past data only, never future target values.

The search objective is `1 / geometric_mean(relative_CRPS)` across the 24
configurations. MASE is diagnostic, with zero objective weight. Prepare your
own seasonal-naive reference using `make_reference.py`; no reference results
are included in this repository. Per-configuration budget: 120 seconds,
one CPU thread, 8 GiB host RSS, one leased CUDA GPU and the configured PyTorch
allocator allowance. Final configurations have a separate larger time budget.

Run `bash scripts/setup_forecasting.sh` on Linux with CUDA/Docker. Check model
licences in `protocol.json`. The optional model packages have intentional
unified dependency overrides; validate all model probes on your host. Source
commits are pinned in the worker-source fetcher. Most checkpoint repositories
are not pinned to immutable revisions, so capture downloaded revisions/hashes
for reproducibility. No API key, checkpoint, Docker image or prior search is
bundled.

For a fresh search: `bash scripts/run_fresh.sh gift_forecasting_v2`.
For final evaluation, freeze the program and explicitly request the complete
97-configuration test scope:

```bash
PROGRAM=/absolute/path/to/selected/program.py
HASH=$(shasum -a 256 "$PROGRAM" | cut -d ' ' -f 1)
.gift-venv/bin/python tasks/gift_forecasting_v2/evaluate_cli.py \
  --program "$PROGRAM" --test --full --frozen-sha256 "$HASH" \
  --output outputs/final-forecasting
```

The final split is not a source of discovery feedback. Development scores
cannot establish leaderboard rank or a controller improvement claim.
