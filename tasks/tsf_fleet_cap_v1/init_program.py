"""Next-Hour Fleet Capacity starting program: seasonal naive + EWMA blend with
a rolling-residual conformal layer. The pipeline architecture is yours to
design; only the interface and the declared DAG contract are fixed."""

# EVOLVE-BLOCK-START
import pickle

import numpy as np

HORIZON = 6
QUANTILES = (0.025, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.975)
SEASON = 24


def declare_dag():
    """Declare the pipeline structure (contract metadata, validated by the grader)."""
    return {
        "nodes": [
            {"name": "ingest", "kind": "source", "paths": ["train", "update", "forecast"]},
            {"name": "scaler", "kind": "scaler", "paths": ["train", "update", "forecast"]},
            {"name": "seasonal_naive", "kind": "model", "paths": ["train", "forecast"]},
            {"name": "ewma", "kind": "model", "paths": ["train", "update", "forecast"]},
            {"name": "blend", "kind": "ensemble", "paths": ["train", "update", "forecast"]},
            {"name": "conformal", "kind": "output", "paths": ["update", "forecast"]},
        ],
        "edges": [
            ["ingest", "scaler"],
            ["scaler", "seasonal_naive"],
            ["scaler", "ewma"],
            ["seasonal_naive", "blend"],
            ["ewma", "blend"],
            ["blend", "conformal"],
        ],
    }


class Forecaster:
    """Stateful streaming forecaster. Replace the internals freely."""

    def __init__(self, metadata=None):
        md = metadata or {}
        self.n = int(md.get("n_services", 0))
        self.horizon = int(md.get("horizon", HORIZON))
        self.quantiles = list(md.get("quantiles", QUANTILES))
        self.ewma = np.zeros(self.n)            # smoothed level
        self.buf = np.zeros((self.n, SEASON))   # ring buffer of last 24 values
        self.pos = 0                            # write position in the ring
        self.seen = np.zeros(self.n, dtype=bool)
        self.resid = None                       # rolling recent blend residuals
        self.resid_cap = 336

    def _push(self, values):
        self.buf[:, self.pos] = values
        self.pos = (self.pos + 1) % SEASON

    def _seasonal(self, horizon):
        """Seasonal-naive path: value 24h before each target hour."""
        # buf columns hold hours t-24 .. t-1 in ring order starting at pos.
        ordered = np.concatenate([self.buf[:, self.pos:], self.buf[:, :self.pos]], axis=1)
        # ordered[:, j] is hour t-24+j; the seasonal value for target hour
        # t+h (h = 1..horizon) is y(t+h-24), i.e. column h.
        return np.stack([ordered[:, h] for h in range(1, horizon + 1)], axis=1)

    # ---- lifecycle ---------------------------------------------------------
    def train(self, history, metadata):
        """One offline pass over the pre-replay history [N, T0] (NaN allowed)."""
        h = np.asarray(history, dtype=np.float64)
        self.n = h.shape[0]
        self.ewma = np.zeros(self.n)
        self.buf = np.zeros((self.n, SEASON))
        self.pos = 0
        self.seen = np.zeros(self.n, dtype=bool)
        alpha = 0.25
        for i in range(self.n):
            x = h[i]
            valid = np.isfinite(x)
            if not valid.any():
                continue
            self.seen[i] = True
            xs = x[valid]
            self.ewma[i] = xs[-1]
            e = xs[-1]
            for v in xs[-336:][::-1][1:]:
                e = (1 - alpha) * e + alpha * v
            self.ewma[i] = e
            tail = xs[-SEASON:]
            self.buf[i, SEASON - len(tail):] = tail
        self.resid = np.full(self.resid_cap, np.nan)

    def update(self, batch, metadata):
        """Hourly ingestion of the full-fleet batch [N] (NaN = missing/absent)."""
        b = np.asarray(batch, dtype=np.float64)
        fill = np.where(np.isfinite(b), b, self.buf[:, (self.pos - 1) % SEASON])
        prev_blend = 0.5 * self._seasonal(1)[:, 0] + 0.5 * self.ewma
        err = np.where(self.seen & np.isfinite(b), b - prev_blend, np.nan)
        if np.any(np.isfinite(err)):
            self.resid = np.roll(self.resid, -1)
            self.resid[-1] = np.nanmedian(err)
        self.ewma = np.where(np.isfinite(b), 0.8 * self.ewma + 0.2 * b, self.ewma)
        self._push(fill)
        self.seen |= np.isfinite(b)

    def forecast(self, ids, horizon, metadata):
        """Forecast requested ids for `horizon` hours ahead."""
        H = int(horizon)
        idx = np.asarray(ids, dtype=int)
        seen = self.seen[idx]
        seasonal = self._seasonal(H)[idx]                     # [B, H]
        mu = 0.5 * seasonal + 0.5 * self.ewma[idx][:, None]
        mu = np.where(seen[:, None], mu, 0.0)
        r = self.resid[np.isfinite(self.resid)]
        if r.size >= 12:
            inner = np.quantile(r, self.quantiles[1:-1])
            spread = float(np.std(r))
        else:
            inner = np.linspace(-1.0, 1.0, 9)
            spread = 1.0
        q = np.concatenate([[inner[0] - 1.5 * spread], inner,
                            [inner[-1] + 1.5 * spread]])
        q = np.maximum.accumulate(q)
        out = np.repeat(mu[:, None, :], len(self.quantiles), axis=1)
        out[:, 1:-1, :] += q[1:-1][None, :, None]
        out[:, 0, :] += q[0]
        out[:, -1, :] += q[-1]
        if (~seen).any():
            out[~seen] = 0.0
            out[~seen, 0, :] = -2.0
            out[~seen, -1, :] = 2.0
            out[~seen, 1:-1, :] = np.linspace(-1.0, 1.0, 9)[None, :, None]
        return {"mean": mu, "quantiles": out}

    # ---- persistence -------------------------------------------------------
    def save_state(self):
        return pickle.dumps(
            {"ewma": self.ewma, "buf": self.buf, "pos": self.pos,
             "seen": self.seen, "resid": self.resid, "n": self.n}, protocol=4)

    def load_state(self, blob):
        s = pickle.loads(blob)
        self.ewma = s["ewma"]
        self.buf = s["buf"]
        self.pos = s["pos"]
        self.seen = s["seen"]
        self.resid = s["resid"]
        self.n = s["n"]
        return self
# EVOLVE-BLOCK-END
