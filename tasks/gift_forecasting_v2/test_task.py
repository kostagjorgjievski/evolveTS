"""Protocol and access-boundary checks; no LLM calls or official test scoring."""
import importlib.util
from pathlib import Path
import sys
import subprocess
import uuid
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluator import (HERE, PROTOCOL, candidate_predictions, development_data, development_reference,
                       load_official, official_configurations, relative_scores, window_groups, host_runtime)


def metadata(horizon=4):
    return {"horizon": horizon, "frequency": "D", "seasonality": 2,
            "quantiles": PROTOCOL["quantiles"], "seed": 0}


def test_seed_repeats_seasonal_pattern():
    entries = [{"target": np.array([1., 2., 3., 4.])}]
    mean, quantiles = candidate_predictions(HERE / "init_program.py", entries, entries, metadata())
    np.testing.assert_equal(mean, [[3., 4., 3., 4.]])
    assert quantiles.shape == (1, 11, 4)


def test_cuda_computation_inside_candidate_boundary(tmp_path):
    candidate = tmp_path / "cuda_probe.py"
    candidate.write_text('''import numpy as np
import torch
def forecast(histories, horizon, metadata, state):
    assert torch.cuda.is_available()
    assert torch.cuda.device_count() == 1
    value = float((torch.tensor([1.,2.], device=metadata["device"]) * 2).sum().item())
    return {"mean": np.full((1,horizon),value), "quantiles": np.full((1,11,horizon),value)}
''')
    mean, _ = candidate_predictions(candidate, [{"target": np.arange(20.)}], [], metadata())
    np.testing.assert_equal(mean, np.full((1,4),6.))


@pytest.mark.skipif(not host_runtime().get("gift_v2_worker_image"), reason="Docker host only")
def test_timeout_removes_its_container(tmp_path, monkeypatch):
    import evaluator
    identity = uuid.uuid4().hex
    monkeypatch.setattr(evaluator.uuid, "uuid4", lambda: SimpleNamespace(hex=identity))
    candidate = tmp_path / "slow.py"
    candidate.write_text("import time\ntime.sleep(999)\n")
    with pytest.raises(RuntimeError, match="wall time"):
        candidate_predictions(candidate, [{"target": np.arange(20.)}], [], metadata(), timeout=2)
    check = subprocess.run(["docker", "inspect", "gift-candidate-" + identity], capture_output=True)
    assert check.returncode != 0


def test_validation_precedes_every_official_test_target():
    from gluonts.dataset.split import split
    # Test loader's split geometry, rather than rebuilding benchmark splits.
    from gluonts.dataset.common import ListDataset
    class Dataset:
        prediction_length = 4
        validation_dataset = ListDataset([{"target": np.arange(32.), "start": "2000-01-01"}], freq="D")
    context, label = next(iter(development_data(Dataset())))
    assert len(context["target"]) == 28
    np.testing.assert_equal(label["target"], [28, 29, 30, 31])
    assert label["start"] + len(label["target"]) == pd.Period("2000-02-02", freq="D")


def test_full_configuration_identity_and_development_coverage():
    load_official()
    configs = official_configurations()
    assert len(configs) == 97
    assert len({c["key"] for c in configs}) == 97
    selected = {c["key"] for c in PROTOCOL["development"]}
    assert selected <= {c["key"] for c in configs}
    assert len({c["domain"] for c in configs if c["key"] in selected}) == 7
    assert len(selected) == 24 and {key.split("/")[2] for key in selected} == {"short", "medium", "long"}


def test_reference_matches_protocol_and_seed_scores_one():
    reference = development_reference()
    assert sorted(reference) == sorted(item["key"] for item in PROTOCOL["development"])
    scores = relative_scores(list(reference.values()), reference)
    assert scores == {"relative_crps": 1.0, "relative_mase": 1.0, "weighted_relative": 1.0}


def test_objective_ranking_does_not_depend_on_the_reference():
    def rows(scale):
        return [{"dataset": key, "eval_metrics/mean_weighted_sum_quantile_loss": c * scale,
                 "eval_metrics/MASE[0.5]": m * scale} for key, c, m in [("a", 1., 2.), ("b", 3., .5)]]
    def as_reference(rows):
        return {row["dataset"]: row for row in rows}
    better, worse = rows(0.8), rows(0.9)
    for reference in (as_reference(rows(1.0)), as_reference(rows(7.0))):
        assert (relative_scores(better, reference)["weighted_relative"]
                < relative_scores(worse, reference)["weighted_relative"])
    ratio = (relative_scores(better, as_reference(rows(1.0)))["weighted_relative"]
             / relative_scores(better, as_reference(rows(7.0)))["weighted_relative"])
    assert ratio == pytest.approx(7.0)


def test_crps_only_objective_ignores_mase_tradeoffs():
    assert PROTOCOL["objective_weights"] == {"crps": 1.0, "mase": 0.0}
    def row(crps, mase):
        return {"dataset": "a", "eval_metrics/mean_weighted_sum_quantile_loss": crps,
                "eval_metrics/MASE[0.5]": mase}
    reference = {"a": row(1.0, 1.0)}
    accurate_distribution = relative_scores([row(0.5, 100.0)], reference)
    accurate_median = relative_scores([row(0.6, 0.01)], reference)
    assert accurate_distribution["weighted_relative"] == pytest.approx(0.5)
    assert accurate_distribution["weighted_relative"] < accurate_median["weighted_relative"]
    assert relative_scores([row(0.5, 0.01)], reference)["weighted_relative"] == pytest.approx(0.5)


@pytest.mark.skipif(not host_runtime().get("gift_v2_worker_image"), reason="Docker host only")
def test_checkpoints_are_mounted_read_only(tmp_path):
    candidate = tmp_path / "models_probe.py"
    candidate.write_text('''import os
import numpy as np
def forecast(histories, horizon, metadata, state):
    paths = metadata["models"]
    assert sorted(paths) == sorted(%r)
    for path in paths.values():
        assert os.listdir(path), path
        try:
            open(os.path.join(path, "probe"), "w")
            raise AssertionError("checkpoint mount writable")
        except OSError:
            pass
    return {"mean": np.zeros((1,horizon)), "quantiles": np.zeros((1,11,horizon))}
''' % sorted(PROTOCOL["models"]))
    meta = dict(metadata(), models={name: m["path"] for name, m in PROTOCOL["models"].items()})
    candidate_predictions(candidate, [{"target": np.arange(20.)}], [], meta)


def test_rolling_windows_do_not_expose_later_history():
    entries = [{"item_id": item} for item in ["a", "a", "a", "b", "b", "b"]]
    assert window_groups(entries) == [[0, 3], [1, 4], [2, 5]]


def test_official_metrics_on_known_forecast():
    from gluonts.ev.metrics import MASE, MeanWeightedSumQuantileLoss
    from gluonts.model import evaluate_model
    from gluonts.model.forecast import QuantileForecast
    start = pd.Period("2000-01-01", freq="D")
    class Data:
        input = [{"target": np.arange(20.), "start": start}]
        label = [{"target": np.arange(20., 24.), "start": start + 20}]
    class Predictor:
        def predict(self, data):
            for _ in data:
                yield QuantileForecast(np.tile([18.,19.,18.,19.], (11,1)),
                                       start_date=start+20, forecast_keys=list(map(str,PROTOCOL["quantiles"])))
    res = evaluate_model(Predictor(), test_data=Data(), metrics=[MASE(), MeanWeightedSumQuantileLoss(
        quantile_levels=[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9])],
        axis=None, mask_invalid_label=True, allow_nan_forecast=False, seasonality=2)
    assert res["MASE[0.5]"].iloc[0] == pytest.approx(1.5)
    assert res["mean_weighted_sum_quantile_loss"].iloc[0] == pytest.approx(3 / 21.5)


def test_candidate_cannot_read_labels_or_use_network(tmp_path):
    secret = tmp_path / "held_out_labels.txt"
    secret.write_text("DO_NOT_READ")
    candidate = tmp_path / "probe.py"
    candidate.write_text('''import socket
import numpy as np
def forecast(histories, horizon, metadata, state):
    try:
        open(''' + repr(str(secret)) + ''').read()
        raise AssertionError("labels readable")
    except (PermissionError, FileNotFoundError):
        pass
    try:
        socket.socket()
        raise AssertionError("network available")
    except PermissionError:
        pass
    return {"mean": np.zeros((1,horizon)), "quantiles": np.zeros((1,11,horizon))}
''')
    entries = [{"target": np.arange(20.)}]
    candidate_predictions(candidate, entries, entries, metadata())


@pytest.mark.parametrize("value", ["float('nan')", "float('inf')"])
def test_nonfinite_predictions_fail(tmp_path, value):
    candidate = tmp_path / "bad.py"
    candidate.write_text('''import numpy as np
def forecast(histories, horizon, metadata, state):
    return {"mean": np.full((1,horizon), ''' + value + '''), "quantiles": np.zeros((1,11,horizon))}
''')
    with pytest.raises(ValueError, match="NaN/Inf"):
        candidate_predictions(candidate, [{"target": np.arange(20.)}], [], metadata())
