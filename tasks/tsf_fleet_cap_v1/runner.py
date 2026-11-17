"""Sandboxed child runner for tsf_fleet_cap_v1.

Executes ONE phase (train, or one replay day) of the candidate program in a
fresh process, with cwd pinned to a scratch directory that also holds the
canary decoy file. The candidate only ever receives the current day's batch;
future days are structurally invisible. Every replay hour runs update() then
forecast() on the full fleet in chunks, so per-call budgets bind exactly as
they would in deployment. All timing gates are also enforced from outside by
the parent (wall clock, CPU rlimits, RSS polling).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path

import numpy as np

TASK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK_DIR))

import audits  # noqa: E402

ALLOWED_KINDS = ("source", "scaler", "feature", "router", "model",
                 "ensemble", "calibrator", "output")
ALLOWED_PATHS = ("train", "update", "forecast")


def _fail(reason: str) -> None:
    Path("error.json").write_text(
        json.dumps({"error": reason, "traceback": traceback.format_exc()}))
    print(f"[runner] error: {reason}", file=sys.stderr)
    sys.exit(3)


def load_program(program_path: str):
    spec = importlib.util.spec_from_file_location("candidate", program_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_forecaster(mod, meta: dict):
    dag_fn = getattr(mod, "declare_dag", None)
    dag = dag_fn() if callable(dag_fn) else None
    dag_violations = audits.audit_dag(dag, allowed_kinds=ALLOWED_KINDS,
                                      allowed_paths=ALLOWED_PATHS,
                                      min_nodes=4, min_kinds=2)
    if dag_violations:
        _fail("; ".join(dag_violations))
    cls = getattr(mod, "Forecaster", None)
    if cls is None:
        _fail("program does not define class Forecaster")
    f = cls(dict(meta))
    for m in ("train", "update", "forecast", "save_state", "load_state"):
        if not callable(getattr(f, m, None)):
            _fail(f"Forecaster missing method {m}")
    return f, dag


def program_metadata(meta: dict, hour: int | None, device: str) -> dict:
    md = {
        "freq": "h",
        "horizon": meta["horizon"],
        "quantiles": meta["quantiles"],
        "n_services": meta["n_services"],
        "service_classes": meta["service_classes"],
        "device": device,
    }
    if hour is not None:
        md["hour_index"] = hour
    return md


def phase_train(args, meta):
    mod = load_program(args.program)
    f, dag = make_forecaster(mod, meta)
    history = np.load(args.history)["history"]
    t0 = time.perf_counter()
    f.train(history, program_metadata(meta, None, "cuda:0"))
    train_seconds = time.perf_counter() - t0
    blob = f.save_state()
    Path(args.state_out).write_bytes(blob)
    json.dump({"phase": "train", "train_seconds": train_seconds,
               "state_bytes": len(blob), "dag": dag},
              open(args.timings, "w"))


def _check_outputs(out, n_ids, horizon, n_q):
    mean, q = out.get("mean"), out.get("quantiles")
    if mean is None or q is None:
        _fail("forecast must return dict with mean and quantiles")
    m = np.asarray(mean, dtype=np.float64)
    qs = np.asarray(q, dtype=np.float64)
    if m.shape != (n_ids, horizon):
        _fail(f"mean shape {m.shape} != ({n_ids}, {horizon})")
    if qs.shape != (n_ids, n_q, horizon):
        _fail(f"quantiles shape {qs.shape} != ({n_ids}, {n_q}, {horizon})")
    if not (np.all(np.isfinite(m)) and np.all(np.isfinite(qs))):
        _fail("non-finite forecast values")
    if np.any(np.diff(qs, axis=1) < -1e-9):
        _fail("quantiles not nondecreasing")
    return m, qs


def phase_replay(args, meta):
    mod = load_program(args.program)
    f, dag = make_forecaster(mod, meta)
    blob = Path(args.state_in).read_bytes()
    if len(blob) > int(os.environ.get("TSF_STATE_MAX", 10 ** 9)):
        _fail("state exceeds size cap")
    f.load_state(blob)

    day = np.load(args.day)["batch"]                       # [24, N]
    hours, n = day.shape
    horizon = meta["horizon"]
    n_q = len(meta["quantiles"])
    update_budget_ms = float(os.environ["TSF_UPDATE_BUDGET"]) * 1000.0
    forecast_budget_ms = float(os.environ["TSF_FORECAST_BUDGET"]) * 1000.0
    chunk = int(os.environ.get("TSF_FORECAST_CHUNK", "128"))
    probe_hour = int(os.environ.get("TSF_PROBE_HOUR", "-1"))
    update_ms, forecast_ms = [], []
    update_strikes = forecast_strikes = 0
    mean_all = np.zeros((hours, n, horizon), dtype=np.float32)
    q_all = np.zeros((hours, n, n_q, horizon), dtype=np.float32)

    for r in range(hours):
        hour = int(args.hour0) + r
        t0 = time.perf_counter()
        f.update(day[r], program_metadata(meta, hour, "cpu"))
        update_ms.append((time.perf_counter() - t0) * 1000.0)
        if update_ms[-1] > update_budget_ms:
            update_strikes += 1
        for s in range(0, n, chunk):
            ids = list(range(s, min(s + chunk, n)))
            t0 = time.perf_counter()
            out = f.forecast(ids, horizon, program_metadata(meta, hour, "cpu"))
            forecast_ms.append((time.perf_counter() - t0) * 1000.0)
            if forecast_ms[-1] > forecast_budget_ms:
                forecast_strikes += 1
            m, qs = _check_outputs(out, len(ids), horizon, n_q)
            mean_all[r, s:s + len(ids)] = m.astype(np.float32)
            q_all[r, s:s + len(ids)] = qs.astype(np.float32)

    probe_max_diff = None
    if int(args.hour0) + hours > probe_hour >= int(args.hour0):
        probe_ids = list(range(min(64, n)))
        md = program_metadata(meta, probe_hour, "cpu")
        a = np.asarray(f.forecast(probe_ids, horizon, md)["mean"], dtype=np.float64)
        b = np.asarray(f.forecast(probe_ids, horizon, md)["mean"], dtype=np.float64)
        probe_max_diff = float(np.max(np.abs(a - b)))

    blob = f.save_state()
    Path(args.state_out).write_bytes(blob)
    np.savez_compressed(args.out, mean=mean_all, quantiles=q_all)
    json.dump({
        "phase": "replay", "hour0": int(args.hour0),
        "update_ms": update_ms, "forecast_ms": forecast_ms,
        "update_strikes": update_strikes, "forecast_strikes": forecast_strikes,
        "probe_max_diff": probe_max_diff, "state_bytes": len(blob), "dag": dag,
    }, open(args.timings, "w"))


def phase_probe(args, meta):
    """Load a checkpoint, forecast twice, re-serialize. Used by checkpoint grading."""
    mod = load_program(args.program)
    f, dag = make_forecaster(mod, meta)
    blob = Path(args.state_in).read_bytes()
    f.load_state(blob)
    n = meta["n_services"]
    horizon = meta["horizon"]
    n_q = len(meta["quantiles"])
    ids = list(range(min(64, n)))
    md = program_metadata(meta, 0, "cpu")
    a = _check_outputs(f.forecast(ids, horizon, md), len(ids), horizon, n_q)
    b = _check_outputs(f.forecast(ids, horizon, md), len(ids), horizon, n_q)
    diff = float(np.max(np.abs(np.asarray(a[0]) - np.asarray(b[0]))))
    blob2 = f.save_state()
    json.dump({"phase": "probe", "state_bytes_in": len(blob),
               "state_bytes_out": len(blob2), "probe_max_diff": diff},
              open(args.timings, "w"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", required=True, choices=["train", "replay", "probe"])
    p.add_argument("--program", required=True)
    p.add_argument("--meta", required=True)
    p.add_argument("--history")
    p.add_argument("--day")
    p.add_argument("--hour0", type=int, default=0)
    p.add_argument("--state-in")
    p.add_argument("--state-out", required=True)
    p.add_argument("--out")
    p.add_argument("--timings", required=True)
    args = p.parse_args()
    meta = json.loads(Path(args.meta).read_text())
    try:
        if args.phase == "train":
            phase_train(args, meta)
        elif args.phase == "probe":
            phase_probe(args, meta)
        else:
            phase_replay(args, meta)
    except SystemExit:
        raise
    except BaseException:
        _fail(f"program raised during {args.phase}")


if __name__ == "__main__":
    main()
