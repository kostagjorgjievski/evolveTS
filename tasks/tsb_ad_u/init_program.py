"""Minimal robust statistical starting detector; higher scores mean anomalous."""
import numpy as np

# EVOLVE-BLOCK-START
def detect(data, train_data, metadata):
    """Score the complete unlabelled series, including its training prefix."""
    x = np.asarray(data, dtype=np.float64)[:, 0]
    reference = np.asarray(train_data, dtype=np.float64)[:, 0]
    if len(reference) == 0:
        reference = x
    center = np.median(reference)
    scale = max(1.4826 * np.median(np.abs(reference - center)), 1e-8)
    return np.abs(x - center) / scale
# EVOLVE-BLOCK-END
