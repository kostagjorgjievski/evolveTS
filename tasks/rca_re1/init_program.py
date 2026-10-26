"""Minimal robust-deviation starting ranker; first entry is most suspicious."""
import numpy as np

# EVOLVE-BLOCK-START
def rank(data, inject_time, metadata):
    """Rank metric series by their largest robust deviation after injection."""
    columns = [c for c in data.columns if c != "time"]
    normal = data.loc[data["time"] < inject_time, columns].to_numpy(dtype=np.float64)
    after = data.loc[data["time"] >= inject_time, columns].to_numpy(dtype=np.float64)
    if normal.shape[0] == 0 or after.shape[0] == 0:
        return columns
    center = np.median(normal, axis=0)
    scale = 1.4826 * np.median(np.abs(normal - center), axis=0)
    scale = np.where(scale > 1e-8, scale, 1e-8)
    score = np.max(np.abs(after - center) / scale, axis=0)
    order = np.argsort(-score, kind="stable")
    return [columns[index] for index in order]
# EVOLVE-BLOCK-END
