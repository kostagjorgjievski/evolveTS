"""Isolated candidate worker: receives values and training prefix, never labels."""
import importlib.util
import json
import os
from pathlib import Path
import random
import resource
import sys

import numpy as np
from sandbox import restrict, restrict_network


def main():
    program, input_path, output_path = map(Path, sys.argv[1:])
    meta = json.loads(input_path.with_suffix(".json").read_text())
    with np.load(input_path, allow_pickle=False) as inputs:
        data, train_data = inputs["data"].copy(), inputs["train_data"].copy()
    memory = meta.pop("memory_gib") * 1024**3
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
    import torch
    torch.set_num_threads(1)
    devices = [str(p) for p in Path("/dev").glob("nvidia*") if not p.is_dir()]
    if os.environ.get("TSB_MACOS_WORKER") == "1":
        pass  # Filesystem and network restricted before startup by sandbox-exec.
    elif os.environ.get("TSB_CONTAINER_WORKER") == "1":
        restrict_network()
    else:
        root = Path(__file__).resolve().parents[2]
        restrict(
            ["/usr", "/lib", "/lib64", "/etc/ld.so.cache", "/etc/localtime",
             sys.prefix, (root / ".gift-venv").resolve(), program,
             "/dev/null", "/dev/urandom", "/proc/self", "/proc/driver/nvidia",
             "/proc/cpuinfo", "/proc/meminfo", "/proc/modules", "/proc/devices",
             "/proc/sys/vm/mmap_min_addr", "/etc/nvidia", "/sys"],
            [output_path.parent, "/proc/self/task"] + devices,
        )
    os.chdir(output_path.parent)
    if meta["device"] == "mps":
        if not torch.backends.mps.is_available():
            raise RuntimeError("Mac profile requires working PyTorch MPS")
        torch.mps.set_per_process_memory_fraction(
            min(1.0, memory / torch.mps.recommended_max_memory()))
    else:
        if not torch.cuda.is_available():
            raise RuntimeError("GPU profile requires working CUDA PyTorch")
        torch.cuda.set_per_process_memory_fraction(
            min(1.0, memory / torch.cuda.get_device_properties(0).total_memory))
    random.seed(meta["seed"])
    np.random.seed(meta["seed"])
    torch.manual_seed(meta["seed"])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    spec = importlib.util.spec_from_file_location("candidate", program)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scores = np.asarray(module.detect(data, train_data, meta), dtype=np.float64)
    np.savez(output_path, scores=scores)


if __name__ == "__main__":
    main()
