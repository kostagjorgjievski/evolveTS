"""Seasonal-naive starting program. The forecasting method is yours to choose."""

# EVOLVE-BLOCK-START
import numpy as np


def fit(training_series, metadata):
    """Optional shared fitting; training_series contains historical targets only."""
    return None


def forecast(histories, horizon, metadata, state):
    """Return mean [N,H] and quantiles [N,11,H], in metadata quantile order."""
    means = []
    for history in histories:
        x = np.asarray(history, dtype=np.float64)
        valid = x[np.isfinite(x)]
        fallback = float(valid[-1]) if len(valid) else 0.0
        # Fill missing history without using any future observations.
        x = np.where(np.isfinite(x), x, fallback)
        season = min(int(metadata["seasonality"]), len(x))
        means.append(np.resize(x[-season:], horizon) if season else np.zeros(horizon))
    mean = np.asarray(means)
    # A deliberately minimal point-mass distribution; improve it if useful.
    quantiles = np.repeat(mean[:, None, :], len(metadata["quantiles"]), axis=1)
    return {"mean": mean, "quantiles": quantiles}
# EVOLVE-BLOCK-END
