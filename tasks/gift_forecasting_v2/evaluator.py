"""Dream-RSI evaluate(program_path) adapter using pinned official GIFT-Eval (v2).

v2 differs from tasks/gift_forecasting: a CRPS-only objective (geometric
mean of relative CRPS, with MASE reported separately), 24 development
configurations, and leakage-free pretrained checkpoints mounted read-only.
"""
from contextlib import contextmanager
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL = json.loads((HERE / "protocol.json").read_text())
PROTOCOL["models_host_dir"] = str((ROOT / PROTOCOL["models_host_dir"]).resolve())
METRIC_NAMES = ["MSE[mean]", "MSE[0.5]", "MAE[0.5]", "MASE[0.5]",
                "MAPE[0.5]", "sMAPE[0.5]", "MSIS", "RMSE[mean]",
                "NRMSE[mean]", "ND[0.5]", "mean_weighted_sum_quantile_loss"]


def gpu_slots():
    """Physical GPUs that may run candidates: the host profile's gift_v2_physical_gpus,
    else its physical_gpus, else its single physical_gpu, else the one visible device.
    Lock files are shared with tasks/gift_forecasting, so the two never share a GPU."""
    runtime = host_runtime()
    gpus = (runtime.get("gift_v2_physical_gpus") or runtime.get("physical_gpus")
            or [runtime.get("physical_gpu", "0")])
    return [str(gpu) for gpu in gpus]


@contextmanager
def gpu_turn():
    """Hold one GPU slot for a whole evaluation, so concurrent agents never share
    a GPU or each other's time limits. Nested calls reuse the held slot."""
    if os.environ.get("GIFT_EVAL_GPU"):
        yield os.environ["GIFT_EVAL_GPU"]
        return
    # .venv resolves into host-local scratch, so each host has its own slots.
    locks = (ROOT / ".venv").resolve().parent
    handles = {gpu: (locks / f"gift-eval-gpu-{gpu}.lock").open("a") for gpu in gpu_slots()}
    try:
        while True:
            for gpu, handle in handles.items():
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                os.environ["GIFT_EVAL_GPU"] = gpu
                try:
                    yield gpu
                finally:
                    del os.environ["GIFT_EVAL_GPU"]
                return
            time.sleep(1)
    finally:
        for handle in handles.values():
            handle.close()


def host_runtime():
    path = ROOT / "configs/hosts" / (socket.gethostname().split(".")[0] + ".json")
    return json.loads(path.read_text()) if path.exists() else {}


def load_official():
    repo = ROOT / "upstream/gift-eval"
    actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if actual != PROTOCOL["gift_commit"]:
        raise RuntimeError("GIFT-Eval checkout differs from protocol pin")
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip():
        raise RuntimeError("GIFT-Eval source must remain clean")
    sys.path.insert(0, str(repo / "src"))
    from gift_eval.data import Dataset
    return Dataset


def official_configurations():
    aliases = {"saugeen": "saugeenday", "temperature_rain": "temperature_rain_with_missing",
               "kdd_cup_2018": "kdd_cup_2018_with_missing", "car_parts": "car_parts_with_missing",
               "loop_seattle": "LOOP_SEATTLE", "sz_taxi": "SZ_TAXI", "m_dense": "M_DENSE"}
    single = {"hospital", "covid_deaths", "restaurant", "temperature_rain", "car_parts",
              "bizitobs_application", "bizitobs_service"}
    rows = []
    with (ROOT / "upstream/gift-eval/scripts/dataset_configurations.csv").open() as handle:
        for row in csv.DictReader(handle):
            key, freq, term = row["dataset"].split("/")
            name = aliases.get(key, key)
            if key not in single and not key.startswith("m4_"):
                name += "/" + freq
            rows.append({"name": name, "term": term, "key": row["dataset"],
                         "domain": row["domain"], "num_variates": int(row["num_variates"])})
    return rows


def development_data(dataset):
    """One horizon before first official test origin; no official test labels."""
    from gluonts.dataset.split import split
    _, template = split(dataset.validation_dataset, offset=-dataset.prediction_length)
    return template.generate_instances(prediction_length=dataset.prediction_length, windows=1)


def chosen_ids(dataset):
    seed = PROTOCOL["selection_seed"]
    ids = [str(item["item_id"]) for item in dataset.training_dataset]
    ordered = sorted(ids, key=lambda item: hashlib.sha256(f"{seed}:{item}".encode()).digest())
    return set(ordered[:PROTOCOL["development_series_per_configuration"]])


def candidate_predictions(program, entries, training, metadata, timeout=None):
    import numpy as np
    with tempfile.TemporaryDirectory(prefix="gift-candidate-") as directory:
        temp = Path(directory)
        # Copy only the submitted file, historical arrays, and metadata.
        candidate = temp / "program.py"
        candidate.write_bytes(Path(program).read_bytes())
        inputs = {f"h{i}": np.asarray(item["target"]) for i, item in enumerate(entries)}
        inputs.update({f"t{i}": np.asarray(item["target"]) for i, item in enumerate(training)})
        np.savez(temp / "inputs.npz", **inputs)
        meta = dict(metadata, count=len(entries), training_count=len(training),
                    memory_gib=PROTOCOL["candidate_memory_gib"], device=PROTOCOL["device"])
        (temp / "inputs.json").write_text(json.dumps(meta))
        output = temp / "output"
        output.mkdir()
        runtime = host_runtime()
        image = runtime.get("gift_v2_worker_image")
        env = {"PATH": "/usr/bin:/bin", "HOME": str(output), "TMPDIR": str(output),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
               "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
               "CUDA_VISIBLE_DEVICES": os.environ.get("GIFT_EVAL_GPU", "0")}
        container_name = None
        command = [sys.executable, str(HERE / "worker.py"), str(candidate),
                   str(temp / "inputs.npz"), str(output / "predictions.npz")]
        if image:
            container_name = "gift-candidate-" + uuid.uuid4().hex
            command = ["docker", "run", "--rm", "--name", container_name,
                       "--network", "none", "--read-only", "--cap-drop", "ALL",
                       "--security-opt", "no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
                       "--gpus", "device=" + os.environ.get("GIFT_EVAL_GPU", gpu_slots()[0]),
                       "--memory", str(PROTOCOL["candidate_memory_gib"]) + "g",
                       "--memory-swap", str(PROTOCOL["candidate_memory_gib"]) + "g",
                       "--cpus", "1", "--pids-limit", "128", "--tmpfs", "/tmp:rw,size=256m"]
            for source, target in [(candidate, "/job/program.py"), (temp / "inputs.npz", "/job/inputs.npz"),
                                   (temp / "inputs.json", "/job/inputs.json")]:
                command += ["--mount", f"type=bind,src={source},dst={target},readonly"]
            command += ["--mount", f"type=bind,src={output},dst=/output",
                        "--mount", f"type=bind,src={PROTOCOL['models_host_dir']},dst=/models,readonly"]
            for key, value in dict(env, HOME="/output", TMPDIR="/tmp", GIFT_CONTAINER_WORKER="1",
                                    CUDA_VISIBLE_DEVICES="0").items():
                command += ["--env", key + "=" + value]
            command += [image, "/usr/local/bin/python", "/opt/gift/worker.py",
                        "/job/program.py", "/job/inputs.npz", "/output/predictions.npz"]
        with (temp / "worker.log").open("w+") as log:
            process = subprocess.Popen(
                command,
                env=env, cwd=temp, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
            try:
                deadline = time.monotonic() + (timeout or PROTOCOL["candidate_seconds_per_configuration"])
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired(process.args, timeout)
                    # CUDA reserves large virtual ranges: bound resident memory,
                    # rather than imposing the CPU profile's address-space cap.
                    pending, resident = [process.pid], 0
                    while pending:
                        pid = pending.pop()
                        try:
                            resident += int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
                            pending.extend(map(int, Path(f"/proc/{pid}/task/{pid}/children").read_text().split()))
                        except (FileNotFoundError, ProcessLookupError):
                            pass
                    if resident > PROTOCOL["candidate_memory_gib"] * 1024**3:
                        raise RuntimeError("Candidate exceeded host resident-memory budget")
                    time.sleep(0.1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise RuntimeError("Candidate exceeded per-configuration wall time")
            finally:
                # Also terminate child processes left behind by a completed candidate.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                if container_name:
                    subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=20, check=False)
            if process.returncode:
                log.seek(0)
                raise RuntimeError(f"Candidate failed ({process.returncode}): {log.read()[-1500:]}")
        with np.load(output / "predictions.npz", allow_pickle=False) as result:
            mean, quantiles = result["mean"].copy(), result["quantiles"].copy()
    expected = (len(entries), metadata["horizon"])
    if mean.shape != expected or quantiles.shape != (expected[0], len(PROTOCOL["quantiles"]), expected[1]):
        raise ValueError("Incorrect mean or quantile shape")
    if not np.isfinite(mean).all() or not np.isfinite(quantiles).all():
        raise ValueError("NaN/Inf forecasts are forbidden")
    if (np.diff(quantiles, axis=1) < -1e-10).any():
        raise ValueError("Quantiles must be ordered")
    return mean, quantiles


def window_groups(entries):
    """Never expose later windows of an item while forecasting earlier ones."""
    occurrences, groups = {}, {}
    for index, entry in enumerate(entries):
        item = str(entry["item_id"])
        window = occurrences.get(item, 0)
        occurrences[item] = window + 1
        groups.setdefault(window, []).append(index)
    return list(groups.values())


def score_configuration(program, config, split_name, Dataset):
    import numpy as np
    from gluonts.ev.metrics import MAE, MAPE, MASE, MSE, MSIS, ND, NRMSE, RMSE, SMAPE, MeanWeightedSumQuantileLoss
    from gluonts.model import evaluate_model
    from gluonts.model.forecast import QuantileForecast
    from gluonts.time_feature import get_seasonality

    started = time.monotonic()
    dataset = Dataset(name=config["name"], term=config["term"], to_univariate=False)
    if dataset.target_dim > 1:
        dataset = Dataset(name=config["name"], term=config["term"], to_univariate=True)
    pairs = development_data(dataset) if split_name == "validation" else dataset.test_data
    selected = chosen_ids(dataset) if split_name == "validation" else None
    pairs = [(a, b) for a, b in pairs if selected is None or str(a["item_id"]) in selected]
    entries, labels = map(list, zip(*pairs))
    training = [item for item in dataset.training_dataset
                if selected is None or str(item["item_id"]) in selected]
    seasonality = get_seasonality(dataset.freq)
    metadata = {"frequency": dataset.freq, "horizon": dataset.prediction_length,
                "seasonality": seasonality, "quantiles": PROTOCOL["quantiles"],
                "device": PROTOCOL["device"],
                "seed": PROTOCOL["selection_seed"],
                "models": {name: model["path"] for name, model in PROTOCOL["models"].items()},
                "training_item_ids": [str(item["item_id"]) for item in training],
                "training_starts": [str(item["start"]) for item in training]}
    mean = np.empty((len(entries), dataset.prediction_length))
    quantiles = np.empty((len(entries), len(PROTOCOL["quantiles"]), dataset.prediction_length))
    prediction_started = time.monotonic()
    budget = PROTOCOL["final_seconds_per_configuration" if split_name == "test" else
                      "candidate_seconds_per_configuration"]
    for indices in window_groups(entries):
        remaining = budget - (time.monotonic() - prediction_started)
        if remaining <= 0:
            raise RuntimeError("Candidate exceeded per-configuration wall time")
        batch = [entries[i] for i in indices]
        batch_metadata = dict(metadata, history_item_ids=[str(item["item_id"]) for item in batch],
                              history_starts=[str(item["start"]) for item in batch])
        m, q = candidate_predictions(program, batch, training, batch_metadata, remaining)
        mean[indices], quantiles[indices] = m, q

    class Predictor:
        def predict(self, data):
            for index, item in enumerate(data):
                yield QuantileForecast(
                    forecast_arrays=np.concatenate([mean[index:index+1], quantiles[index]], axis=0),
                    forecast_keys=["mean"] + list(map(str, PROTOCOL["quantiles"])),
                    start_date=item["start"] + len(item["target"]), item_id=item.get("item_id"),
                )

    metrics = [MSE(forecast_type="mean"), MSE(forecast_type=0.5), MAE(), MASE(), MAPE(),
               SMAPE(), MSIS(), RMSE(), NRMSE(), ND(),
               MeanWeightedSumQuantileLoss(quantile_levels=[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9])]
    # Official evaluate_model only needs the .input and .label iterables here.
    class Data:
        input = entries
        label = labels

    res = evaluate_model(Predictor(), test_data=Data(), metrics=metrics,
                         batch_size=512, axis=None, mask_invalid_label=True,
                         allow_nan_forecast=False, seasonality=seasonality)
    row = {"dataset": config["key"]}
    row.update({"eval_metrics/" + key: float(res[key].iloc[0]) for key in METRIC_NAMES})
    row.update(domain=config["domain"], num_variates=config["num_variates"])
    detail = {"dataset": config["key"], "horizon": dataset.prediction_length,
              "official_test_windows": dataset.windows, "evaluated_forecasts": len(entries),
              "selected_item_ids": sorted(selected) if selected is not None else "all",
              "seconds": time.monotonic() - started}
    return row, detail


def development_reference():
    """Seasonal-naive seed metrics on the development windows (make_reference.py)."""
    data = json.loads((HERE / PROTOCOL["reference_file"]).read_text())
    if data["data_revision"] != PROTOCOL["data_revision"] or data["development"] != PROTOCOL["development"]:
        raise RuntimeError("Reference file does not match the development protocol")
    return {row["dataset"]: row for row in data["rows"]}


def leaderboard_reference():
    """The leaderboard's own Seasonal_Naive results, for full final-test scoring."""
    path = next((ROOT / PROTOCOL["leaderboard_reference"]).glob("*.csv"))
    with path.open() as handle:
        return {row["dataset"]: {key: float(value) if key.startswith("eval_metrics/") else value
                                 for key, value in row.items()} for row in csv.DictReader(handle)}


def relative_scores(rows, reference):
    """Geometric means of per-configuration CRPS (wQL) and MASE relative to the reference,
    as the GIFT-Eval leaderboard aggregates them; lower is better, the reference is 1."""
    import math
    logs = {"crps": [], "mase": []}
    for row in rows:
        ref = reference[row["dataset"]]
        for name, metric in [("crps", "mean_weighted_sum_quantile_loss"), ("mase", "MASE[0.5]")]:
            value, base = row["eval_metrics/" + metric], ref["eval_metrics/" + metric]
            if not (math.isfinite(value) and value > 0 and math.isfinite(base) and base > 0):
                raise ValueError(f"Invalid {metric} for {row['dataset']}: {value} vs reference {base}")
            logs[name].append(math.log(value / base))
    weights = PROTOCOL["objective_weights"]
    mean = {name: sum(values) / len(values) for name, values in logs.items()}
    return {"relative_crps": math.exp(mean["crps"]), "relative_mase": math.exp(mean["mase"]),
            "weighted_relative": math.exp(weights["crps"] * mean["crps"] + weights["mase"] * mean["mase"])}


def run(program, split_name="validation", full=False, score=True):
    import math
    import numpy as np
    started = time.monotonic()
    Dataset = load_official()
    data = Path(os.environ.get("GIFT_EVAL", ROOT / "data/gift-eval"))
    if (data / "REVISION").read_text().strip() != PROTOCOL["data_revision"]:
        raise RuntimeError("Data revision marker differs from pinned protocol")
    os.environ["GIFT_EVAL"] = str(data)
    all_configs = official_configurations()
    indexed = {config["key"]: config for config in all_configs}
    configs = all_configs if full else [indexed[item["key"]] for item in PROTOCOL["development"]]
    rows, details = [], []
    for config in configs:
        row, detail = score_configuration(program, config, split_name, Dataset)
        rows.append(row)
        details.append(detail)
    # make_reference.py runs the seed with score=False to produce the reference itself.
    relative = {}
    if score:
        relative = relative_scores(rows, leaderboard_reference() if full else development_reference())
    combined = 1.0 / relative["weighted_relative"] if relative else None
    if relative and (not math.isfinite(combined) or combined <= 0):
        raise ValueError("Invalid objective; evaluation fails without dropping configurations")
    return {"combined_score": combined, **relative,
            "split": split_name, "scope": "official-full" if full else "development-subset",
            "program_sha256": hashlib.sha256(Path(program).read_bytes()).hexdigest(),
            "gift_commit": PROTOCOL["gift_commit"], "data_revision": PROTOCOL["data_revision"],
            "host": socket.gethostname(), "runtime": host_runtime(),
            "physical_gpu": os.environ.get("GIFT_EVAL_GPU"),
            "seconds": time.monotonic() - started, "rows": rows, "details": details}


def evaluate(program_path):
    """Standard upstream task entry point. Always validation, never test."""
    python = ROOT / ".gift-venv/bin/python"
    try:
        # The outer limit starts once this evaluation has a GPU slot.
        with gpu_turn():
            process = subprocess.run([str(python), str(HERE / "evaluate_cli.py"),
                                      "--program", str(Path(program_path).resolve())],
                                     capture_output=True, text=True,
                                     timeout=PROTOCOL["evaluation_seconds"])
        if process.returncode:
            raise RuntimeError(process.stderr[-2000:])
        return json.loads(process.stdout)
    except Exception as exc:
        return {"combined_score": 0.0, "error": str(exc)}
