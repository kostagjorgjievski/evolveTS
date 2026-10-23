"""Meaningful checks of benchmark splits, metric identity, and candidate isolation."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluator import HERE, PROTOCOL, candidate_scores, load_official, read_series, gpu_turn, validate_metrics, official_metrics, host_runtime
from prepare_data import DATA, file_list, verify_splits


def metadata():
    return {"seed": 2024, "device": host_runtime().get("device", "cuda:0")}


@pytest.fixture
def resource_slot():
    with gpu_turn():
        yield


def test_official_splits_are_disjoint_and_complete():
    assert verify_splits() == (48, 350, 822)
    assert not set(file_list("tuning")) & set(file_list("full"))
    assert set(file_list("evaluation")) <= set(file_list("full"))


def test_loader_matches_official_prefix_and_does_not_extract_evaluation():
    manifest = json.loads((DATA / "prepared-development.json").read_text())
    for name in file_list("tuning"):
        data, labels, train_length = read_series(name, "tuning", manifest)
        assert data.shape == (len(labels), 1)
        assert train_length == int(Path(name).stem.split("_")[-3])
    assert len(list((DATA / "tuning").glob("*.csv"))) == 48
    assert not (DATA / "evaluation").exists()


def test_candidate_seed_and_cuda_and_no_label_access(tmp_path, resource_slot):
    secret = tmp_path / "labels.txt"
    secret.write_text("HIDDEN")
    candidate = tmp_path / "probe.py"
    candidate.write_text('''import numpy as np
import socket
import torch
from scipy.ndimage import uniform_filter1d
from sklearn.ensemble import IsolationForest
def detect(data, train_data, metadata):
    assert set(metadata) == {"seed", "device"}
    if metadata["device"] == "mps":
        assert torch.backends.mps.is_available()
    else:
        assert torch.cuda.device_count() == 1
    assert float(torch.tensor([2.], device=metadata["device"]).sum().item()) == 2.
    assert len(train_data) == 8
    try:
        open('''+repr(str(secret))+''').read()
        raise AssertionError("label file accessible")
    except (FileNotFoundError, PermissionError):
        pass
    try:
        with socket.socket() as connection:
            connection.settimeout(1)
            connection.connect(("1.1.1.1", 443))
        raise AssertionError("network available")
    except PermissionError:
        pass
    return np.arange(len(data), dtype=float)
''')
    x = np.arange(16.)[:, None]
    scores = candidate_scores(candidate, x, x[:8], metadata())
    np.testing.assert_array_equal(scores, np.arange(16.))
    seed = candidate_scores(HERE / "init_program.py", x, x[:8], metadata())
    assert seed.shape == (16,)
    assert seed[-1] > seed[7]


@pytest.mark.parametrize("expression,pattern", [
    ("np.zeros((len(data),1))", "shape"),
    ("np.full(len(data),np.nan)", "NaN/Inf"),
    ("np.full(len(data),np.inf)", "NaN/Inf")])
def test_invalid_scores_fail(tmp_path, expression, pattern, resource_slot):
    candidate = tmp_path / "bad.py"
    candidate.write_text("import numpy as np\ndef detect(data, train_data, metadata):\n    return "+expression+"\n")
    with pytest.raises(ValueError, match=pattern):
        candidate_scores(candidate, np.arange(20.)[:, None], np.arange(8.)[:, None], metadata())


def test_official_metric_identity_and_ordering():
    get_metrics, _ = load_official()
    labels = np.zeros(100, dtype=int)
    labels[40:50] = 1
    scores = labels.astype(float) + np.arange(100)*1e-8
    result = get_metrics(scores, labels, slidingWindow=10, version='opt', thre=250)
    bad = get_metrics(-scores, labels, slidingWindow=10, version='opt', thre=250)
    assert result['AUC-PR'] == pytest.approx(1.)
    assert result['VUS-PR'] > 0.95
    assert result['VUS-PR'] > bad['VUS-PR']
    primary = official_metrics(scores, labels, 10)
    assert primary == {key: result[key] for key in primary}


def test_undefined_secondary_f1_does_not_discard_valid_vus_pr():
    import warnings
    get_metrics, _ = load_official()
    labels = np.zeros(100, dtype=int)
    labels[40:50] = 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = get_metrics(np.zeros(100), labels, slidingWindow=10)
    clean = validate_metrics(raw)
    assert clean['VUS-PR'] == raw['VUS-PR']
    assert clean['VUS-PR'] > 0
    assert clean['Affiliation-F'] is None


def test_final_evaluation_requires_frozen_hash_and_fresh_output(tmp_path):
    command = [sys.executable, str(HERE / 'evaluate_cli.py'), '--program',
               str(HERE / 'init_program.py'), '--test', '--output', str(tmp_path/'result')]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 2
    assert 'frozen-sha256' in result.stderr
    assert not (tmp_path/'result').exists()
