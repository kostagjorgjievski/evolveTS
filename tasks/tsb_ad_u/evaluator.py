"""Standard Dream-RSI task adapter; official TSB-AD-U splits and metrics."""
from contextlib import contextmanager
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
METRIC_NAMES = ["AUC-PR", "AUC-ROC", "VUS-PR", "VUS-ROC"]
ALL_METRIC_NAMES = METRIC_NAMES + ["Standard-F1", "PA-F1", "Event-based-F1", "R-based-F1", "Affiliation-F"]


def gpu_slots():
    """Physical GPUs that may run candidates: the host profile's physical_gpus,
    else its single physical_gpu, else the one visible device."""
    runtime = host_runtime()
    return [str(gpu) for gpu in runtime.get("physical_gpus") or [runtime.get("physical_gpu", "0")]]


@contextmanager
def gpu_turn():
    """Hold one GPU slot for a whole evaluation, so concurrent agents never share
    a GPU or each other's time limits. Nested calls reuse the held slot."""
    if os.environ.get("GIFT_EVAL_GPU"):
        yield os.environ["GIFT_EVAL_GPU"]
        return
    # .venv resolves into host-local scratch, so each host has its own slots.
    locks = (ROOT / ".venv").resolve().parent
    if sys.platform == "darwin":
        locks = ROOT / "work/runtime-locks"
        locks.mkdir(parents=True, exist_ok=True)
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
    runtime = json.loads(path.read_text()) if path.exists() else {}
    override = HERE / ("runtime-" + socket.gethostname().split(".")[0] + ".json")
    if runtime.get("worker_image"):
        if not override.exists():
            raise RuntimeError("TSB-AD-U worker image is not installed on this host; run setup.sh")
        runtime.update(json.loads(override.read_text()))
    return runtime


def candidate_scores(program, data, train_data, metadata, timeout=None):
    import numpy as np
    with tempfile.TemporaryDirectory(prefix="tsb-candidate-") as directory:
        temp = Path(directory)
        # Copy only the submitted file, historical arrays, and metadata.
        candidate = temp / "program.py"
        candidate.write_bytes(Path(program).read_bytes())
        np.savez(temp / "inputs.npz", data=data, train_data=train_data)
        runtime = host_runtime()
        meta = dict(metadata, memory_gib=PROTOCOL["candidate_memory_gib"],
                    device=runtime.get("device", PROTOCOL["device"]))
        (temp / "inputs.json").write_text(json.dumps(meta))
        output = temp / "output"
        output.mkdir()
        env = {"PATH": "/usr/bin:/bin", "HOME": str(output), "TMPDIR": str(output),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
               "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
               "NUMBA_CACHE_DIR": str(output / "numba"),
               "MPLCONFIGDIR": str(output / "matplotlib"),
               "CUDA_VISIBLE_DEVICES": os.environ.get("GIFT_EVAL_GPU", "0")}
        container_name = None
        command = [sys.executable, str(HERE / "worker.py"), str(candidate),
                   str(temp / "inputs.npz"), str(output / "predictions.npz")]
        if sys.platform == "darwin":
            from macos_sandbox import profile
            sandbox = temp / "candidate.sb"
            sandbox.write_text(profile(candidate, output))
            env.update(TSB_MACOS_WORKER="1", PYTORCH_ENABLE_MPS_FALLBACK="1",
                       NUMBA_CACHE_DIR=str(output / "numba"),
                       MPLCONFIGDIR=str(output / "matplotlib"))
            command = ["/usr/bin/sandbox-exec", "-f", str(sandbox)] + command
        if runtime.get("worker_image"):
            container_name = "tsb-candidate-" + uuid.uuid4().hex
            command = ["docker", "run", "--rm", "--name", container_name,
                       "--network", "none", "--read-only", "--cap-drop", "ALL",
                       "--security-opt", "no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
                       "--gpus", "device=" + os.environ.get("GIFT_EVAL_GPU", runtime["physical_gpu"]),
                       "--memory", str(PROTOCOL["candidate_memory_gib"]) + "g",
                       "--memory-swap", str(PROTOCOL["candidate_memory_gib"]) + "g",
                       "--cpus", "1", "--pids-limit", "128", "--tmpfs", "/tmp:rw,size=256m"]
            for source, target in [(candidate, "/job/program.py"), (temp / "inputs.npz", "/job/inputs.npz"),
                                   (temp / "inputs.json", "/job/inputs.json")]:
                command += ["--mount", f"type=bind,src={source},dst={target},readonly"]
            command += ["--mount", f"type=bind,src={output},dst=/output"]
            for key, value in dict(env, HOME="/output", TMPDIR="/tmp", TSB_CONTAINER_WORKER="1",
                                    NUMBA_CACHE_DIR="/output/numba", MPLCONFIGDIR="/output/matplotlib",
                                    CUDA_VISIBLE_DEVICES="0").items():
                command += ["--env", key + "=" + value]
            command += [runtime["worker_image"], "/usr/local/bin/python", "/opt/tsb/worker.py",
                        "/job/program.py", "/job/inputs.npz", "/output/predictions.npz"]
        with (temp / "worker.log").open("w+") as log:
            process = subprocess.Popen(
                command,
                env=env, cwd=temp, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
            try:
                deadline = time.monotonic() + (timeout or PROTOCOL["candidate_seconds_per_series"])
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired(process.args, timeout)
                    # CUDA reserves large virtual ranges: bound resident memory,
                    # rather than imposing the CPU profile's address-space cap.
                    pending, resident = [process.pid], 0
                    if sys.platform == "darwin":
                        import psutil
                        try:
                            parent = psutil.Process(process.pid)
                            resident = sum(p.memory_info().rss for p in [parent] + parent.children(recursive=True)
                                           if p.is_running())
                        except psutil.NoSuchProcess:
                            resident = 0
                        pending = []
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
                raise RuntimeError("Candidate exceeded per-series wall time")
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
            scores = result["scores"].copy()
    if scores.shape != (len(data),):
        raise ValueError("detect must return exactly one score per timestamp, shape (N,)")
    if not np.isfinite(scores).all():
        raise ValueError("NaN/Inf anomaly scores are forbidden")
    return scores


def load_official():
    from prepare_data import REPO, verify_source, verify_splits
    verify_source()
    verify_splits()
    sys.path.insert(0, str(REPO))
    from TSB_AD.evaluation.metrics import get_metrics
    from TSB_AD.utils.slidingWindows import find_length_rank
    return get_metrics, find_length_rank


def read_series(name, split_name, manifest):
    import io
    import zipfile
    import numpy as np
    import pandas as pd
    from prepare_data import DATA
    if split_name == "tuning":
        payload = (DATA / "tuning" / name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != manifest["tuning_files"][name]:
            raise RuntimeError("Tuning file checksum mismatch")
    else:
        with zipfile.ZipFile(DATA / "TSB-AD-U.zip") as archive:
            payload = archive.read("TSB-AD-U/" + name)
    # Exactly the official loader: drop missing rows, last column is Label.
    df = pd.read_csv(io.BytesIO(payload)).dropna()
    if list(df.columns) != ["Data", "Label"]:
        raise ValueError("Unexpected univariate schema")
    data = df.iloc[:, 0:-1].values.astype(float)
    labels = df["Label"].astype(int).to_numpy()
    train_index = int(Path(name).stem.split("_")[-3])
    if not 0 < train_index <= len(data) or not np.isfinite(data).all():
        raise ValueError("Invalid training prefix or nonfinite input")
    if set(np.unique(labels)) != {0, 1}:
        raise ValueError("Series must contain both normal and anomaly labels")
    return data, labels, train_index


def validate_metrics(result):
    """Preserve undefined descriptive F1 values without changing the objective."""
    import math
    metrics = {}
    if not set(METRIC_NAMES) <= set(result):
        raise ValueError("Missing primary metrics")
    for key in result:
        value = float(result[key])
        if not math.isfinite(value):
            if key in METRIC_NAMES:
                raise ValueError("Official threshold-independent metric is nonfinite")
            metrics[key] = None
        elif not -1e-9 <= value <= 1+1e-9:
            raise ValueError("Official metric is outside [0,1]")
        else:
            metrics[key] = value
    return metrics


def official_metrics(scores, labels, window, all_metrics=False):
    """Use get_metrics' exact primary functions, avoiding unused oracle F1 work."""
    from TSB_AD.evaluation.basic_metrics import basic_metricor, generate_curve
    if all_metrics:
        from TSB_AD.evaluation.metrics import get_metrics
        return validate_metrics(get_metrics(scores, labels, slidingWindow=window,
            version=PROTOCOL["metric_version"], thre=PROTOCOL["metric_thresholds"]))
    grader = basic_metricor()
    curve = generate_curve(labels.astype(int), scores, window,
                           PROTOCOL["metric_version"], PROTOCOL["metric_thresholds"])
    return validate_metrics({"AUC-PR": grader.metric_PR(labels, scores),
                             "AUC-ROC": grader.metric_ROC(labels, scores),
                             "VUS-PR": curve[-1], "VUS-ROC": curve[-2]})


def run(program, split_name="tuning", all_metrics=False):
    import numpy as np
    from prepare_data import DATA, file_list, sha256
    started = time.monotonic()
    _, find_length_rank = load_official()
    metric_names = ALL_METRIC_NAMES if all_metrics else METRIC_NAMES
    manifest = json.loads((DATA / "prepared-development.json").read_text())
    if (manifest["archive_sha256"] != PROTOCOL["data_sha256"] or
            manifest["benchmark_commit"] != PROTOCOL["benchmark_commit"]):
        raise RuntimeError("Development manifest differs from protocol pin")
    # Check even the stored archive on every evaluation, including final runs.
    if sha256(DATA / "TSB-AD-U.zip") != PROTOCOL["data_sha256"]:
        raise RuntimeError("Data archive checksum mismatch")
    rows = []
    for name in file_list(split_name):
        identity = "tuning-" + hashlib.sha256(name.encode()).hexdigest()[:16] if split_name == "tuning" else name
        progress_path = os.environ.get("TSB_EVAL_PROGRESS")
        if progress_path:
            with Path(progress_path).open("a") as progress:
                progress.write(json.dumps({"series": identity, "completed": len(rows), "phase": "started"}) + "\n")
        data, labels, train_index = read_series(name, split_name, manifest)
        window = int(find_length_rank(data[:, 0].reshape(-1, 1), rank=1))
        begin = time.monotonic()
        # File names embed the first anomaly location: never expose them or
        # dataset identity to the submitted program.
        scores = candidate_scores(program, data, data[:train_index].copy(),
                                  {"seed": PROTOCOL["selection_seed"], "device": PROTOCOL["device"]})
        candidate_seconds = time.monotonic() - begin
        metric_started = time.monotonic()
        metrics = official_metrics(scores, labels, window, all_metrics)
        print(f"[tsb-ad-u] {len(rows)+1}/{len(file_list(split_name))} {identity} VUS-PR={metrics['VUS-PR']:.6f}",
              file=sys.stderr, flush=True)
        rows.append({"file": identity, "length": len(data), "train_length": train_index,
                     "sliding_window": window, "candidate_seconds": candidate_seconds,
                     "metric_seconds": time.monotonic()-metric_started, **metrics})
        if progress_path:
            with Path(progress_path).open("a") as progress:
                progress.write(json.dumps({"series": identity, "completed": len(rows),
                                           "phase": "done", "VUS-PR": metrics["VUS-PR"]}) + "\n")
    objective = float(np.mean([row["VUS-PR"] for row in rows]))
    return {"combined_score": objective, "mean_vus_pr": objective,
            "split": split_name, "series": len(rows),
            "mean_metrics": {key: (None if any(r[key] is None for r in rows)
                                   else float(np.mean([r[key] for r in rows]))) for key in metric_names},
            "program_sha256": hashlib.sha256(Path(program).read_bytes()).hexdigest(),
            "protocol_sha256": hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
            "benchmark_commit": PROTOCOL["benchmark_commit"], "data_sha256": PROTOCOL["data_sha256"],
            "host": socket.gethostname(), "runtime": host_runtime(),
            "physical_gpu": os.environ.get("GIFT_EVAL_GPU"),
            "seconds": time.monotonic()-started, "rows": rows}


def evaluate(program_path):
    """Upstream's evaluate(program_path) entry point: tuning only, higher is better."""
    try:
        with gpu_turn():
            process = subprocess.run(
                [str(ROOT / ".tsb-venv/bin/python"), str(HERE / "evaluate_cli.py"),
                 "--program", str(Path(program_path).resolve())],
                capture_output=True, text=True, timeout=PROTOCOL["development_evaluation_timeout_seconds"])
        if process.returncode:
            raise RuntimeError(process.stderr[-2000:])
        return json.loads(process.stdout)
    except Exception as exc:
        return {"combined_score": 0.0, "error": str(exc)}
