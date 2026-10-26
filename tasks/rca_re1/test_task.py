"""Meaningful checks of RCAEval splits, preprocessing, metrics and isolation."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluator import (HERE, PROTOCOL, case_metric, candidate_counts, candidate_ranks,
                       gpu_turn, read_case, sli_column)
from prepare_data import DATA, cases_frame, sha256, split_cases, verify_case_files, verify_source


@pytest.fixture(scope="module")
def development():
    return split_cases("development")


def test_official_splits_are_disjoint_and_complete():
    development, evaluation, full = (split_cases(kind) for kind in
                                     ("development", "evaluation", "full"))
    assert (len(development), len(evaluation), len(full)) == (75, 300, 375)
    assert not set(development["case"]) & set(evaluation["case"])
    assert set(development["case"]) | set(evaluation["case"]) == set(full["case"])
    assert development["repetition"].eq(1).all()
    assert evaluation["repetition"].gt(1).all()
    assert (development.groupby(["system", "root_cause_service", "fault"]).size() == 1).all()
    assert development.groupby("system").size().eq(25).all()


def test_data_pins_and_manifest():
    verify_source()
    assert sha256(DATA / "cases.parquet") == PROTOCOL["cases_sha256"]
    for kind in ("development", "evaluation", "full"):
        verify_case_files(kind, split_cases(kind))


def test_official_preprocessing_per_system(development):
    for system in ("ob", "ss", "tt"):
        row = development[development["system"] == system].iloc[0]
        data, inject_time = read_case(row)
        assert 0 < len(data) <= 2 * PROTOCOL["window_rows_per_side"]
        assert data["time"].is_monotonic_increasing
        assert inject_time == int(row["inject_time"])
        assert not any(c.endswith("_latency-50") or c.endswith("_latency-90")
                       for c in data.columns)
        assert np.isfinite(data.drop(columns=["time"]).to_numpy(dtype=float)).all()
        assert sli_column(data, system) in data.columns
        services, metrics = candidate_counts(data)
        assert services >= 1 and 0 < metrics <= len(data.columns) - 1


def test_candidate_isolation_and_full_ranking(tmp_path, development):
    probe = tmp_path / "probe.py"
    probe.write_text('''
import socket
def rank(data, inject_time, metadata):
    assert set(metadata) == {"seed", "device", "system", "sli", "memory_gib"}
    try:
        connection = socket.socket()
        connection.settimeout(1)
        connection.connect(("1.1.1.1", 443))
        raise AssertionError("network available")
    except (PermissionError, OSError):
        pass
    columns = [c for c in data.columns if c != "time"]
    return list(reversed(columns))
''')
    row = development.iloc[0]
    data, inject_time = read_case(row)
    metadata = {"seed": PROTOCOL["selection_seed"], "device": PROTOCOL["device"],
                "system": row["system"], "sli": sli_column(data, row["system"]), "memory_gib": 8}
    with gpu_turn():
        ranks = candidate_ranks(probe, data, inject_time, metadata)
    assert ranks == list(reversed([c for c in data.columns if c != "time"]))


@pytest.mark.parametrize("expression,pattern", [
    ("return [c for c in data.columns if c != 'time'][:-1]", "exactly once"),
    ("return [c for c in data.columns if c != 'time'] + [data.columns[1]]", "exactly once"),
    ("return list(data.columns)", "exactly once"),
    ("return [1, 2]", "only strings"),
])
def test_invalid_rankings_fail(tmp_path, development, expression, pattern):
    candidate = tmp_path / "bad.py"
    candidate.write_text("def rank(data, inject_time, metadata):\n    " + expression + "\n")
    row = development.iloc[0]
    data, inject_time = read_case(row)
    metadata = {"seed": PROTOCOL["selection_seed"], "device": PROTOCOL["device"],
                "system": row["system"], "sli": sli_column(data, row["system"]), "memory_gib": 8}
    with gpu_turn():
        with pytest.raises(ValueError, match=pattern):
            candidate_ranks(candidate, data, inject_time, metadata)


def test_official_metrics_hand_computed():
    row = pd.Series({"case": "synthetic", "system": "ob",
                     "root_cause_service": "adservice", "fault": "cpu"})
    ranks = ["cartservice_cpu", "frontend_latency", "adservice_cpu", "redis_mem", "main_cpu"]
    metrics = case_metric(ranks, row, n_service=5, n_metric=5)
    assert metrics["AC@1_service"] == 0
    assert metrics["AC@3_service"] == 1
    assert metrics["Avg@5_service"] == pytest.approx(0.6)
    assert metrics["AC@1_metric"] == 0
    assert metrics["AC@3_metric"] == 1
    assert metrics["Avg@5_metric"] == pytest.approx(0.6)


def test_disk_fault_expects_latency_metric():
    row = pd.Series({"case": "synthetic", "system": "ss",
                     "root_cause_service": "carts", "fault": "disk"})
    ranks = ["carts_latency"] + ["x_cpu", "y_mem"]
    metrics = case_metric(ranks, row, n_service=3, n_metric=3)
    assert metrics["AC@1_metric"] == 1
    assert metrics["AC@1_service"] == 1


def test_final_evaluation_requires_frozen_hash_and_fresh_output(tmp_path):
    command = [sys.executable, str(HERE / "evaluate_cli.py"), "--program",
               str(HERE / "init_program.py"), "--test", "--output", str(tmp_path / "result")]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 2
    assert "frozen-sha256" in result.stderr
    assert not (tmp_path / "result").exists()
