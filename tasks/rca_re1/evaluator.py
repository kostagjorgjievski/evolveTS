"""Dream-RSI evaluator for RCAEval RE1: official preprocessing and metrics."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
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
DATA = ROOT / "data/rcaeval"
RCAEVAL = ROOT / "upstream/rcaeval"
METRIC_NAMES = PROTOCOL["reported_metrics"]
_OFFICIAL = None
_DOCKER = None


def docker_cli():
    """Docker command prefix. Some hosts expose the daemon only through
    passwordless sudo; the worker itself still runs as the invoking user."""
    global _DOCKER
    if _DOCKER is None:
        if shutil.which("docker") is None:
            raise RuntimeError("docker is not installed")
        probe = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if subprocess.run(["docker", "info"], **probe).returncode == 0:
            _DOCKER = ["docker"]
        elif subprocess.run(["sudo", "-n", "docker", "info"], **probe).returncode == 0:
            _DOCKER = ["sudo", "-n", "docker"]
        else:
            raise RuntimeError("docker daemon is not accessible")
    return _DOCKER


def gpu_slots():
    """Physical GPUs that may run candidates: host profile's physical_gpus,
    else its single physical_gpu, else the one visible device."""
    runtime = host_runtime()
    return [str(gpu) for gpu in runtime.get("physical_gpus") or [runtime.get("physical_gpu", "0")]]


@contextmanager
def gpu_turn():
    """Hold one GPU slot for a whole evaluation, sharing the locks used by the
    anomaly and forecasting tasks so concurrent campaigns never overlap."""
    if os.environ.get("GIFT_EVAL_GPU"):
        yield os.environ["GIFT_EVAL_GPU"]
        return
    locks = (ROOT / ".rca-venv").resolve().parent
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
    if runtime.get("rca_worker_image"):
        if not override.exists():
            raise RuntimeError("RCA worker image is not installed on this host; run setup.sh")
        runtime.update(json.loads(override.read_text()))
    return runtime


def load_official():
    """Import the pinned benchmark's own metric implementation."""
    global _OFFICIAL
    if _OFFICIAL is None:
        if not (RCAEVAL / "RCAEval/benchmark/evaluation.py").exists():
            raise RuntimeError("missing upstream/rcaeval; run scripts/bootstrap.sh")
        if str(RCAEVAL) not in sys.path:
            sys.path.insert(0, str(RCAEVAL))
        from RCAEval.benchmark.evaluation import Evaluator
        from RCAEval.classes.graph import Node
        _OFFICIAL = (Evaluator, Node)
    return _OFFICIAL


def service_order(ranks):
    """Official service-level ranking: first occurrence of each entity prefix."""
    order = []
    for name in ranks:
        entity = name.split("_")[0].replace("-db", "")
        if entity not in order:
            order.append(entity)
    return order


def metric_pairs(ranks):
    """Official fine-grained ranking: (entity, metric) for each returned series."""
    return [(name.split("_")[0], name.split("_")[1] if "_" in name else "unknown")
            for name in ranks]


def expected_metric(fault):
    return PROTOCOL["fault_to_metric"][fault]


def read_case(row):
    """Read one case and apply the official main.py preprocessing verbatim."""
    import numpy as np
    import pandas as pd
    data = pd.read_parquet(DATA / row["case"] / "metrics.parquet")
    if "time.1" in data:
        data = data.drop(columns=["time.1"])
    data = data.loc[:, ~data.columns.str.endswith("_latency-50")]
    data = data.replace([np.inf, -np.inf], np.nan)
    data = data.ffill()
    data = data.fillna(0)
    if not data["time"].is_monotonic_increasing:
        raise ValueError("case time column is not sorted: " + row["case"])
    inject_time = int(row["inject_time"])
    length = PROTOCOL["window_rows_per_side"]
    normal = data[data["time"] < inject_time].tail(length)
    anomal = data[data["time"] >= inject_time].head(length)
    data = pd.concat([normal, anomal], ignore_index=True)
    data = data.rename(columns={c: c.replace("_latency-90", "_latency")
                                for c in data.columns if c.endswith("_latency-90")})
    return data, inject_time


def sli_column(data, system):
    preferred = PROTOCOL["sli"][system]
    if preferred in data:
        return preferred
    for column in data.columns:
        if column.endswith("_latency"):
            return column
    for column in data.columns:
        if column != "time":
            return column
    raise ValueError("case has no metric columns")


def candidate_counts(data):
    """Candidate-set sizes after the official drop-time/drop-constant step."""
    kept = [c for c in data.columns if c != "time" and data[c].nunique(dropna=True) > 1]
    return len({c.split("_")[0].replace("-db", "") for c in kept}), len(kept)


def candidate_ranks(program, data, inject_time, metadata, timeout=None):
    """Run the candidate in the isolated worker and return its ranking."""
    import numpy as np
    columns = [c for c in data.columns if c != "time"]
    with tempfile.TemporaryDirectory(prefix="rca-candidate-") as directory:
        temp = Path(directory)
        candidate = temp / "program.py"
        candidate.write_bytes(Path(program).read_bytes())
        np.savez(temp / "inputs.npz", values=data.to_numpy(dtype=np.float64))
        (temp / "inputs.json").write_text(json.dumps({
            "columns": list(data.columns), "inject_time": inject_time, "metadata": metadata,
        }))
        output = temp / "output"
        output.mkdir()
        runtime = host_runtime()
        if not runtime.get("rca_worker_image"):
            raise RuntimeError("no rca_worker_image in the host profile; run setup.sh")
        env = {"PATH": "/usr/bin:/bin", "HOME": str(output), "TMPDIR": "/tmp",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
               "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
               "NUMBA_CACHE_DIR": "/output/numba", "MPLCONFIGDIR": "/output/matplotlib",
               "RCA_CONTAINER_WORKER": "1", "CUDA_VISIBLE_DEVICES": "0"}
        container_name = "rca-candidate-" + uuid.uuid4().hex
        command = docker_cli() + ["run", "--rm", "--name", container_name,
                   "--network", "none", "--read-only", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
                   "--gpus", "device=" + os.environ.get("GIFT_EVAL_GPU", runtime["physical_gpu"]),
                   "--memory", str(PROTOCOL["candidate_memory_gib"]) + "g",
                   "--memory-swap", str(PROTOCOL["candidate_memory_gib"]) + "g",
                   "--cpus", str(PROTOCOL["candidate_threads"]),
                   "--pids-limit", "128", "--tmpfs", "/tmp:rw,size=256m"]
        for source, target in [(candidate, "/job/program.py"), (temp / "inputs.npz", "/job/inputs.npz"),
                               (temp / "inputs.json", "/job/inputs.json")]:
            command += ["--mount", f"type=bind,src={source},dst={target},readonly"]
        command += ["--mount", f"type=bind,src={output},dst=/output"]
        for key, value in env.items():
            command += ["--env", key + "=" + value]
        command += [runtime["rca_worker_image"], "/usr/local/bin/python", "/opt/rca/worker.py",
                    "/job/program.py", "/job/inputs.npz", "/job/inputs.json",
                    "/output/ranks.json"]
        with (temp / "worker.log").open("w+") as log:
            process = subprocess.Popen(command, env=env, cwd=temp, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic() + (timeout or PROTOCOL["candidate_seconds_per_case"])
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired(process.args, timeout)
                    time.sleep(0.1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise RuntimeError("Candidate exceeded per-case wall time")
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                subprocess.run(docker_cli() + ["rm", "-f", container_name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=20, check=False)
            if process.returncode:
                log.seek(0)
                raise RuntimeError(f"Candidate failed ({process.returncode}): {log.read()[-1500:]}")
        ranks = json.loads((output / "ranks.json").read_text())
    if not isinstance(ranks, list) or isinstance(ranks, str):
        raise ValueError("rank must return a list of series names")
    if not all(isinstance(name, str) for name in ranks):
        raise ValueError("rank must return only strings")
    if len(ranks) != len(set(ranks)) or set(ranks) != set(columns) or "time" in ranks:
        raise ValueError("rank must return every metric column exactly once, time excluded")
    return ranks


def case_metric(ranks, row, n_service, n_metric):
    """Per-case official AC@1/3/5 and Avg@5 at service and metric level."""
    Evaluator, Node = load_official()
    s_evaluator, f_evaluator = Evaluator(max_k=5), Evaluator(max_k=5)
    s_evaluator.add_case([Node(entity, "unknown") for entity in service_order(ranks)],
                         Node(row["root_cause_service"], "unknown"), n_candidates=n_service)
    f_evaluator.add_case([Node(entity, metric) for entity, metric in metric_pairs(ranks)],
                         Node(row["root_cause_service"], expected_metric(row["fault"])),
                         n_candidates=n_metric)
    result = {}
    for level, evaluator in (("service", s_evaluator), ("metric", f_evaluator)):
        for k in (1, 3, 5):
            result[f"AC@{k}_{level}"] = evaluator.accuracy(k)
        result[f"Avg@5_{level}"] = evaluator.average(5)
    return result


def run(program, split_name="development"):
    from prepare_data import split_cases, verify_case_files, verify_source
    import numpy as np
    verify_source()
    cases = split_cases(split_name)
    verify_case_files(split_name, cases)
    Evaluator, Node = load_official()
    s_total, f_total = Evaluator(max_k=5), Evaluator(max_k=5)
    started = time.monotonic()
    rows = []
    for _, row in cases.iterrows():
        begin = time.monotonic()
        data, inject_time = read_case(row)
        n_service, n_metric = candidate_counts(data)
        metadata = {"seed": PROTOCOL["selection_seed"], "device": PROTOCOL["device"],
                    "system": row["system"], "sli": sli_column(data, row["system"]),
                    "memory_gib": PROTOCOL["candidate_memory_gib"]}
        identity = "dev-" + hashlib.sha256(row["case"].encode()).hexdigest()[:16] \
            if split_name == "development" else row["case"]
        progress_path = os.environ.get("RCA_EVAL_PROGRESS")
        if progress_path:
            with Path(progress_path).open("a") as progress:
                progress.write(json.dumps({"case": identity, "completed": len(rows),
                                           "phase": "started"}) + "\n")
        ranks = candidate_ranks(program, data, inject_time, metadata)
        candidate_seconds = time.monotonic() - begin
        metrics = case_metric(ranks, row, n_service, n_metric)
        print(f"[rca-re1] {len(rows)+1}/{len(cases)} {identity} "
              f"Avg@5_service={metrics['Avg@5_service']:.6f}", file=sys.stderr, flush=True)
        rows.append({"case": identity, "system": row["system"], "fault": row["fault"],
                     "length": len(data), "metrics": n_metric, "services": n_service,
                     "candidate_seconds": candidate_seconds, **metrics})
        s_total.add_case([Node(entity, "unknown") for entity in service_order(ranks)],
                         Node(row["root_cause_service"], "unknown"), n_candidates=n_service)
        f_total.add_case([Node(entity, metric) for entity, metric in metric_pairs(ranks)],
                         Node(row["root_cause_service"], expected_metric(row["fault"])),
                         n_candidates=n_metric)
        if progress_path:
            with Path(progress_path).open("a") as progress:
                progress.write(json.dumps({"case": identity, "completed": len(rows),
                                           "phase": "done",
                                           "Avg@5_service": metrics["Avg@5_service"]}) + "\n")
    objective = float(s_total.average(5))
    return {"combined_score": objective, "mean_avg5_service": objective,
            "split": split_name, "cases": len(rows),
            "mean_metrics": {name: float(np.mean([row[name] for row in rows]))
                             for name in METRIC_NAMES},
            "program_sha256": hashlib.sha256(Path(program).read_bytes()).hexdigest(),
            "protocol_sha256": hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
            "benchmark_commit": PROTOCOL["benchmark_commit"],
            "data_revision": PROTOCOL["data_revision"],
            "host": socket.gethostname(), "runtime": host_runtime(),
            "physical_gpu": os.environ.get("GIFT_EVAL_GPU"),
            "seconds": time.monotonic() - started, "rows": rows}


def evaluate(program_path):
    """Upstream's evaluate(program_path) entry point: development split only."""
    try:
        with gpu_turn():
            process = subprocess.run(
                [str(ROOT / ".rca-venv/bin/python"), str(HERE / "evaluate_cli.py"),
                 "--program", str(Path(program_path).resolve())],
                capture_output=True, text=True,
                timeout=PROTOCOL["development_evaluation_timeout_seconds"])
        if process.returncode:
            raise RuntimeError(process.stderr[-2000:])
        return json.loads(process.stdout)
    except Exception as exc:
        return {"combined_score": 0.0, "error": str(exc)}
