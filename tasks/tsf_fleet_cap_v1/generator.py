"""Deterministic synthetic fleet generator for tsf_fleet_cap_v1.

Produces hourly per-service capacity demand with smooth/diurnal/spiky/episodic/
volatile regimes, slow drift, an incident window, cold-start injections, NaN
gaps and (development split only) unpredictable canary series used as leak
traps by the verifier. The final split draws its regime mix and parameters from
held-out ranges so that development tuning cannot memorise the private draw.
"""

from __future__ import annotations

import hashlib
import warnings

import numpy as np

REGIMES = ("smooth", "diurnal", "spiky", "episodic", "volatile")
CLASS_PRIORS = {
    "online": ("diurnal", "diurnal", "smooth", "volatile"),
    "batch": ("spiky", "spiky", "episodic", "volatile"),
    "db": ("smooth", "smooth", "episodic", "diurnal"),
    "misc": ("smooth", "diurnal", "spiky", "episodic"),
}


def _rng(master_seed: str, space: str) -> np.random.Generator:
    tag = hashlib.sha256(f"{master_seed}:{space}".encode()).digest()
    return np.random.default_rng(np.frombuffer(tag, dtype=np.uint32))


class Fleet:
    def __init__(self, history, replay, classes, regimes, cold_mask, scales, meta):
        self.history = history          # [N, T0] float32, NaN where absent
        self.replay = replay            # [N, Tr] float32
        self.classes = classes          # [N] service class strings
        self.regimes = regimes          # [N] regime strings (verifier-internal)
        self.cold_mask = cold_mask      # [N] bool: cold-start series
        self.scales = scales            # [N] history std used for CRPS normalisation
        self.meta = meta

    def scored_groups(self):
        """Regime group per series, canaries excluded from scoring."""
        out = {}
        for i, r in enumerate(self.regimes):
            if r == "canary":
                continue
            g = "coldstart" if self.cold_mask[i] else r
            out.setdefault(g, []).append(i)
        return out


def generate(split: str, *, n_services: int, history_hours: int, replay_hours: int,
             cold_start_hours, event_window, n_canaries: int, master_seed: str) -> Fleet:
    """Generate one fleet timeline. split='development' or 'final'."""
    holdout = split == "final"
    rng_p = _rng(master_seed, "params")
    rng_d = _rng(master_seed, "data")
    rng_ep = _rng(master_seed, "episodic")
    rng_ev = _rng(master_seed, "events")
    total = history_hours + replay_hours
    n_live = n_services - n_canaries

    classes = np.array([sorted(CLASS_PRIORS)[i % 4] for i in range(n_services)], dtype=object)
    regimes = np.empty(n_services, dtype=object)
    for i, c in enumerate(classes):
        regimes[i] = CLASS_PRIORS[c][rng_p.integers(len(CLASS_PRIORS[c]))]
    regimes[n_live:] = "canary"

    # Held-out split shifts parameter ranges so private regimes are novel mixes.
    shift = 1.0 if not holdout else 1.35

    level0 = np.exp(rng_p.normal(3.0, 1.0, n_services))
    noise_sd = np.clip(rng_p.uniform(0.03, 0.18, n_services) * shift, 0.02, 0.45)
    daily_amp = rng_p.uniform(0.05, 0.55, n_services)
    phase = rng_p.uniform(0, 2 * np.pi, n_services)
    drift_sd = rng_p.uniform(0.0005, 0.004, n_services) * shift
    burst_rate = rng_p.uniform(0.04, 0.28, n_services) * (1.6 if holdout else 1.0)
    burst_size = np.exp(rng_p.normal(0.6, 0.8, n_services))
    fail_rate = rng_p.uniform(0.002, 0.008, n_services) * (1.5 if holdout else 1.0)
    volatile = regimes == "volatile"
    noise_sd[volatile] = np.clip(noise_sd[volatile] * 3.0, 0.15, 0.6)
    daily_amp[regimes == "diurnal"] = np.clip(daily_amp[regimes == "diurnal"] * 1.6, 0.2, 0.9)
    daily_amp[regimes == "spiky"] *= 0.3
    daily_amp[regimes == "episodic"] *= 0.3

    # Cold starts: chosen live services have NaN history before injection.
    cold = np.zeros(n_services, dtype=bool)
    order = rng_p.permutation(n_live)
    per_cs = max(1, n_live // 64)
    pick = order[: per_cs * len(cold_start_hours)]
    for k, h in enumerate(cold_start_hours):
        ids = pick[k * per_cs:(k + 1) * per_cs]
        cold[ids] = True

    t = np.arange(total, dtype=np.float64)
    season = 1.0 + daily_amp[:, None] * np.sin(2 * np.pi * (t[None, :] / 24.0) + phase[:, None])
    season = season * (1.0 + 0.35 * daily_amp[:, None] * np.sin(2 * np.pi * (t[None, :] / 168.0) + phase[:, None]))

    # All timeline-length-dependent draws happen in fixed 24-hour blocks so
    # the timeline prefix is bit-stable when the replay is extended (NumPy
    # Generator draws are not prefix-stable across different array sizes).
    BLOCK = 24
    n_blocks = (total + BLOCK - 1) // BLOCK
    dwalk = np.empty((n_services, total))
    noise_mult = np.empty((n_live, total))
    gaps = np.zeros((n_services, total), dtype=bool)
    can_jump = np.zeros((n_canaries, total), dtype=bool)
    can_steps = np.empty((n_canaries, total))
    can_noise = np.empty((n_canaries, total))
    arrivals = {i: np.empty(total, dtype=np.int64) for i in np.where((regimes == "spiky") | volatile)[0]}
    mag = {i: np.empty(total) for i in arrivals}
    decay = {i: np.empty(total) for i in arrivals}
    for k in range(n_blocks):
        lo, hi = k * BLOCK, min((k + 1) * BLOCK, total)
        w = hi - lo
        dwalk[:, lo:hi] = rng_d.normal(size=(n_services, w))
        noise_mult[:, lo:hi] = np.exp(rng_d.normal(0.0, 1.0, (n_live, w)) * noise_sd[:n_live, None])
        gaps[:, lo:hi] = rng_d.random((n_services, w)) < 0.005
        for i in arrivals:
            arrivals[i][lo:hi] = rng_d.poisson(burst_rate[i], w)
            mag[i][lo:hi] = rng_d.exponential(burst_size[i], w)
            decay[i][lo:hi] = rng_d.uniform(0.3, 0.8, w)
        if n_canaries:
            can_jump[:, lo:hi] = rng_d.random((n_canaries, w)) < (1.0 / 120.0)
            can_steps[:, lo:hi] = rng_d.normal(0, 0.45, (n_canaries, w))
            can_noise[:, lo:hi] = rng_d.normal(0, 0.9, (n_canaries, w))

    lam = level0[:, None] * np.exp(drift_sd[:, None] * np.cumsum(dwalk, axis=1))
    y = lam * season

    # Spiky bursts: Poisson arrivals, exponential decay memory.
    for i in arrivals:
        burst = np.zeros(total)
        for h in np.where(arrivals[i] > 0)[0]:
            n = arrivals[i][h]
            burst[h] += mag[i][h] * n
            length = min(total - h - 1, int(6 * n))
            w = np.exp(-decay[i][h] * np.arange(1, length + 1))
            burst[h + 1:h + 1 + length] += mag[i][h] * n * w
        y[i] *= 1.0 + burst

    # Episodic failures: near-zero for a duration, then recovery ramp. The
    # loop runs a fixed number of iterations with unconditional draws
    # (application is conditional, consumption never is), so extending the
    # timeline preserves the prefix exactly (checkpoint continuation).
    for i in np.where(regimes == "episodic")[0]:
        events = rng_ep.poisson(fail_rate[i] * 240, 40)
        for k, n in enumerate(events):
            h = int(rng_ep.integers(0, 720))
            dur = int(rng_ep.uniform(4, 24))
            drop_mult = rng_ep.uniform(0.02, 0.15)
            rec_len = int(rng_ep.uniform(6, 24))
            if n == 0 or h >= total:
                continue
            y[i, h:min(total, h + dur)] *= drop_mult
            ramp = np.linspace(0.2, 1.0, rec_len)
            start = h + dur
            end = min(total, start + rec_len)
            if end > start:
                y[i, start:end] *= ramp[: end - start]

    # Incident window: level shock plus extra variance on live series.
    e0, e1 = event_window
    for i in range(n_live):
        if cold[i]:
            continue
        y[i, history_hours + e0:history_hours + e1] *= rng_ev.uniform(1.2, 2.6)
        y[i, history_hours + e0:history_hours + e1] *= np.exp(
            rng_ev.normal(0, 0.10, e1 - e0))

    # Observation noise on live series.
    y[:n_live] *= noise_mult

    # Canaries: pure innovation around a level that jumps rarely. Future
    # values are (by construction) independent of history; only reading
    # leaked labels can score well on them.
    for j in range(n_canaries):
        i = n_live + j
        walk = np.cumsum(can_steps[j] * can_jump[j])
        y[i] = level0[i] * np.exp(walk + can_noise[j])

    # NaN gaps on observed cells (never inside the first 48 history hours, so
    # every series has usable history).
    gaps[:, :48] = False
    y[gaps] = np.nan

    # Cold starts: mask pre-injection history.
    for k, h in enumerate(cold_start_hours):
        ids = pick[k * per_cs:(k + 1) * per_cs]
        y[np.ix_(ids, np.arange(history_hours + h))] = np.nan

    hist = y[:, :history_hours].astype(np.float32)
    repl = y[:, history_hours:].astype(np.float32)

    # Per-series normalisation scale from history std; cold-start rows have no
    # history, so fall back to a fraction of their (hidden) base level.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        s = np.nanstd(hist, axis=1)
        m = np.nanmean(np.abs(hist), axis=1)
    scales = np.where(np.isfinite(s) & (s > 0), s, 0.3 * level0)
    scales = np.maximum(scales, np.maximum(0.05 * np.where(np.isfinite(m), m, 0.0), 1e-6))

    meta = {
        "split": split, "master_seed": master_seed, "n_services": n_services,
        "history_hours": history_hours, "replay_hours": replay_hours,
        "cold_start_hours": list(cold_start_hours), "event_window": list(event_window),
        "n_canaries": n_canaries,
    }
    return Fleet(hist, repl, classes, regimes, cold, scales, meta)


def generate_development() -> Fleet:
    import json
    from pathlib import Path
    cfg = json.loads((Path(__file__).parent / "protocol.json").read_text())["development"]
    return generate("development", n_services=cfg["n_services"], history_hours=cfg["history_hours"],
                    replay_hours=cfg["replay_hours"], cold_start_hours=cfg["cold_start_hours"],
                    event_window=cfg["event_window"], n_canaries=cfg["n_canaries"],
                    master_seed=cfg["master_seed"])
