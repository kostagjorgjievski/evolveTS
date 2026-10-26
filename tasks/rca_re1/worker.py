"""Isolated candidate worker: receives a metric window, never case identity or labels."""
import importlib.util
import json
import os
from pathlib import Path
import random
import resource
import sys

import numpy as np
import pandas as pd


def main():
    program, input_path, input_meta_path, output_path = map(Path, sys.argv[1:])
    meta = json.loads(input_meta_path.read_text())
    with np.load(input_path, allow_pickle=False) as inputs:
        values = inputs["values"].copy()
    frame = pd.DataFrame(values, columns=meta["columns"])
    frame["time"] = frame["time"].astype(np.int64)
    metadata = dict(meta["metadata"])
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
    import torch
    torch.set_num_threads(1)
    devices = [str(p) for p in Path("/dev").glob("nvidia*") if not p.is_dir()]
    if os.environ.get("RCA_CONTAINER_WORKER") == "1":
        from sandbox import restrict_network
        restrict_network()
    else:
        from sandbox import restrict
        root = Path(__file__).resolve().parents[2]
        restrict(
            ["/usr", "/lib", "/lib64", "/etc/ld.so.cache", "/etc/localtime",
             sys.prefix, (root / ".rca-venv").resolve(), program,
             "/dev/null", "/dev/urandom", "/proc/self", "/proc/driver/nvidia",
             "/proc/cpuinfo", "/proc/meminfo", "/proc/modules", "/proc/devices",
             "/proc/sys/vm/mmap_min_addr", "/etc/nvidia", "/sys"],
            [output_path.parent, "/proc/self/task"] + devices,
        )
    os.chdir(output_path.parent)
    if not torch.cuda.is_available():
        raise RuntimeError("GPU profile requires working CUDA PyTorch")
    memory = metadata.get("memory_gib")
    if memory:
        torch.cuda.set_per_process_memory_fraction(
            min(1.0, memory * 1024**3 / torch.cuda.get_device_properties(0).total_memory))
    random.seed(metadata["seed"])
    np.random.seed(metadata["seed"])
    torch.manual_seed(metadata["seed"])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    spec = importlib.util.spec_from_file_location("candidate", program)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ranks = module.rank(frame, int(meta["inject_time"]), metadata)
    if isinstance(ranks, np.ndarray):
        ranks = ranks.tolist()
    output_path.write_text(json.dumps(list(ranks)))


if __name__ == "__main__":
    main()
