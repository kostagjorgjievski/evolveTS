"""Load one mounted checkpoint and forecast synthetic series inside the v2 worker.

    python model_smoke.py MODEL [--restricted]   # inside the worker image, /models mounted

Prints one JSON line: load and forecast seconds, peak CUDA memory, output shapes,
and the median forecast's MAE relative to seasonal naive (a plausibility check on
noisy seasonal data, not a benchmark). Run by smoke_models.sh with the
evaluator's container limits.
"""
import json
import sys
import time

import numpy as np
import torch

MODELS = "/models"
SERIES, LENGTH, HORIZON, SEASON = 32, 2048, 48, 24
LEVELS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def synthetic():
    rng = np.random.default_rng(0)
    t = np.arange(LENGTH + HORIZON)
    rows = [10 + i + (2 + i % 5) * np.sin(2 * np.pi * t / SEASON + i) + 0.01 * i * t / SEASON
            + rng.normal(0, 0.5, t.size) for i in range(SERIES)]
    data = np.stack(rows).astype(np.float32)
    return data[:, :LENGTH], data[:, LENGTH:]


def chronos_2(histories):
    from chronos import BaseChronosPipeline
    pipe = BaseChronosPipeline.from_pretrained(f"{MODELS}/amazon__chronos-2", device_map="cuda")
    loaded = time.monotonic()
    q, _ = pipe.predict_quantiles([h[None] for h in histories], prediction_length=HORIZON,
                                  quantile_levels=LEVELS)
    return loaded, torch.stack(q)[:, 0].permute(0, 2, 1).float().cpu().numpy()   # [B, Q, H]


def timesfm_2p5(histories):
    from timesfm import configs
    from timesfm.timesfm_2p5 import timesfm_2p5_torch
    model = timesfm_2p5_torch.TimesFM_2p5_200M_torch()
    model.load_checkpoint(f"{MODELS}/google__timesfm-2.5-200m-pytorch/model.safetensors")
    model.compile(configs.ForecastConfig(max_context=LENGTH, max_horizon=HORIZON, normalize_inputs=True,
                                         use_continuous_quantile_head=True, fix_quantile_crossing=True,
                                         per_core_batch_size=32))
    loaded = time.monotonic()
    _, full = model.forecast(horizon=HORIZON, inputs=list(histories))
    return loaded, np.transpose(full[:, :HORIZON, 1:], (0, 2, 1))


def timesfm_3(histories):
    from timesfm3 import ModelConfig, TimesFM3Evaluator
    model = TimesFM3Evaluator(ModelConfig(checkpoint_path=f"{MODELS}/google__timesfm-3.0-pytorch",
                                          per_core_batch_size=32, device="cuda", local_files_only=True))
    loaded = time.monotonic()
    out = list(model.predict_batch(contexts=list(histories), horizon=HORIZON, return_quantiles=True))
    return loaded, np.stack([o.quantiles[:HORIZON, :].T for o in out])


def tirex_2(histories):
    from tirex2 import load_model
    from tirex2.model.types import TimeseriesType
    # Built on CPU, the sLSTM uses flashrnn's pure-PyTorch backend; on "cuda" it would
    # JIT-compile a CUDA kernel, which needs nvcc (not in the worker).
    model = load_model(f"{MODELS}/NX-AI__TiRex-2-gifteval-zs", device="cpu")
    model.model.to("cuda")
    loaded = time.monotonic()
    out = model.forecast([TimeseriesType(torch.from_numpy(h)[None], None, None) for h in histories],
                         prediction_length=HORIZON, output_type="numpy")
    return loaded, np.stack([o[0] for o in out])   # one [V=1, Q, H] array per series


def toto_2(histories):
    from toto2 import Toto2Model
    model = Toto2Model.from_pretrained(f"{MODELS}/Datadog__Toto-2.0-313m").to("cuda").eval()
    loaded = time.monotonic()
    target = torch.from_numpy(histories)[:, None].cuda()
    q = model.forecast({"target": target, "target_mask": torch.ones_like(target, dtype=torch.bool),
                        "series_ids": torch.zeros(len(histories), 1, dtype=torch.long, device="cuda")},
                       horizon=HORIZON, decode_block_size=768, has_missing_values=False)
    return loaded, q[:, :, 0].permute(1, 0, 2).float().cpu().numpy()


def flowstate(histories):
    from tsfm_public import FlowStateForPrediction
    from tsfm_public.models.flowstate.utils.utils import get_fixed_factor
    model = FlowStateForPrediction.from_pretrained(f"{MODELS}/ibm-research__flowstate").to("cuda").eval()
    loaded = time.monotonic()
    scale = get_fixed_factor("H", None)
    context = int(model.config.context_length / scale)
    batch = torch.from_numpy(histories[:, -context:]).T[:, :, None].cuda()   # [T, B, 1]
    with torch.no_grad():
        out = model(past_values=batch, scale_factor=scale, prediction_length=HORIZON,
                    batch_first=False).quantile_outputs
    return loaded, out.squeeze(-1).float().cpu().numpy()   # [B, Q, H]


def timestral(histories):
    from timestral import TimestralForecaster
    model = TimestralForecaster.from_pretrained(f"{MODELS}/mistralai__Timestral-209M", device="cuda")
    loaded = time.monotonic()
    out = model.forecast(torch.from_numpy(histories)[:, None], HORIZON)
    levels = list(model.quantile_levels)
    q = out.quantiles[:, 0][..., [levels.index(level) for level in LEVELS]]
    return loaded, q.permute(0, 2, 1).float().cpu().numpy()


RUNNERS = {"chronos-2": chronos_2, "timesfm-2.5": timesfm_2p5, "timesfm-3": timesfm_3,
           "tirex-2": tirex_2, "toto-2.0-313m": toto_2, "flowstate-r1.1": flowstate,
           "timestral-209m": timestral}


def main():
    name = sys.argv[1]
    if "--restricted" in sys.argv[2:]:
        sys.path.insert(0, "/opt/gift")
        from sandbox import restrict_network
        restrict_network()   # exactly what worker.py applies inside the container
        torch.set_num_threads(1)
    histories, future = synthetic()
    started = time.monotonic()
    loaded, quantiles = RUNNERS[name](histories)
    torch.cuda.synchronize()
    finished = time.monotonic()
    quantiles = np.asarray(quantiles, dtype=np.float64)
    if quantiles.shape != (SERIES, len(LEVELS), HORIZON) or not np.isfinite(quantiles).all():
        raise ValueError(f"Invalid model quantiles: shape={quantiles.shape}, finite={np.isfinite(quantiles).all()}")
    median = quantiles[:, LEVELS.index(0.5)]
    naive = np.tile(histories[:, -SEASON:], HORIZON // SEASON)
    print(json.dumps({
        "model": name, "torch": torch.__version__, "device": torch.cuda.get_device_name(0),
        "load_seconds": round(loaded - started, 2), "forecast_seconds": round(finished - loaded, 2),
        "peak_cuda_gib": round(torch.cuda.max_memory_allocated() / 1024**3, 2),
        "quantiles_shape": list(quantiles.shape), "finite": bool(np.isfinite(quantiles).all()),
        "ordered": bool((np.diff(quantiles, axis=1) >= -1e-6).all()),
        "mae_relative_to_seasonal_naive": round(float(np.abs(median - future).mean()
                                                      / np.abs(naive - future).mean()), 3),
    }), flush=True)


if __name__ == "__main__":
    main()
