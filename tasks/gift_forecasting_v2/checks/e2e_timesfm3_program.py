"""End-to-end check program (not given to agents): TimesFM-3 on every configuration,
with the 0.025/0.975 levels extrapolated from 0.1/0.9 under a normal shape."""

# EVOLVE-BLOCK-START
import numpy as np


def fit(training_series, metadata):
    return None


def _clean(history):
    x = np.asarray(history, dtype=np.float32)
    valid = np.isfinite(x)
    if not valid.any():
        return np.zeros(8, dtype=np.float32)
    x = x[np.argmax(valid):]
    # Forward-fill missing values with the last observed value (history only).
    idx = np.where(np.isfinite(x), np.arange(len(x)), 0)
    return x[np.maximum.accumulate(idx)]


def forecast(histories, horizon, metadata, state):
    from timesfm3 import ModelConfig, TimesFM3Evaluator
    model = TimesFM3Evaluator(ModelConfig(checkpoint_path=metadata["models"]["timesfm-3"], device="cuda",
                                          local_files_only=True, per_core_batch_size=32))
    contexts = [_clean(h)[-4096:] for h in histories]
    outs = list(model.predict_batch(contexts=contexts, horizon=horizon, return_quantiles=True))
    q9 = np.stack([o.quantiles[:horizon, :].T for o in outs]).astype(np.float64)   # [N, 9, H]
    median = q9[:, 4]
    z = 1.959964 / 1.281552
    low = median - z * (median - q9[:, 0])
    high = median + z * (q9[:, 8] - median)
    quantiles = np.concatenate([low[:, None], q9, high[:, None]], axis=1)
    quantiles = np.maximum.accumulate(quantiles, axis=1)
    return {"mean": median, "quantiles": quantiles}
# EVOLVE-BLOCK-END
