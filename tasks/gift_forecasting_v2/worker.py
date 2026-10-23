"""Private evaluator worker. Receives historical inputs, never labels."""
import importlib.util
import json
import os
from pathlib import Path
import resource
import random
import sys

import numpy as np

from sandbox import restrict, restrict_network


def main():
    program, input_path, output_path = map(Path, sys.argv[1:])
    meta = json.loads(input_path.with_suffix(".json").read_text())
    with np.load(input_path, allow_pickle=False) as data:
        histories = [data[f"h{i}"].copy() for i in range(meta["count"])]
        training = [data[f"t{i}"].copy() for i in range(meta["training_count"])]
    memory = meta.pop("memory_gib") * 1024**3
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
    import torch
    torch.set_num_threads(1)
    devices = [str(path) for path in Path("/dev").glob("nvidia*") if not path.is_dir()]
    if os.environ.get("GIFT_CONTAINER_WORKER") == "1":
        # The parent mounts only historical inputs and scratch into the container.
        restrict_network()
    else:
        restrict(
            ["/usr", "/lib", "/lib64", "/etc/ld.so.cache", "/etc/localtime",
             sys.prefix, program, "/dev/null", "/dev/urandom", "/proc/self", "/proc/driver/nvidia",
             "/proc/cpuinfo", "/proc/meminfo", "/proc/modules", "/proc/devices", "/proc/sys/vm/mmap_min_addr",
             "/etc/nvidia", "/sys"],
            [output_path.parent, "/proc/self/task"] + devices,
        )
    os.chdir(output_path.parent)
    if not torch.cuda.is_available():
        raise RuntimeError("GPU profile requires a working CUDA PyTorch installation")
    torch.cuda.set_per_process_memory_fraction(min(1.0, memory / torch.cuda.get_device_properties(0).total_memory))
    random.seed(meta["seed"])
    np.random.seed(meta["seed"])
    torch.manual_seed(meta["seed"])
    spec = importlib.util.spec_from_file_location("candidate", program)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = module.fit(training, meta) if hasattr(module, "fit") else None
    result = module.forecast(histories, meta["horizon"], meta, state)
    # Object arrays/pickle are never accepted by the evaluator.
    mean = np.asarray(result["mean"], dtype=np.float64)
    quantiles = np.asarray(result["quantiles"], dtype=np.float64)
    np.savez(output_path, mean=mean, quantiles=quantiles)


if __name__ == "__main__":
    main()
