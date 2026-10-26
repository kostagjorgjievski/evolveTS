import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rca_objective", ROOT / "tasks/rca_re1/evaluator.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_service_order_is_the_official_first_occurrence_ranking():
    ranks = ["carts-db_cpu", "carts_mem", "ts-auth-service_cpu",
             "frontend-external_error", "carts_cpu"]
    assert module.service_order(ranks) == ["carts", "ts-auth-service", "frontend-external"]


def test_metric_pairs_match_the_official_entity_metric_split():
    assert module.metric_pairs(["ts-auth-service_cpu", "frontend-external_error", "x"]) == [
        ("ts-auth-service", "cpu"), ("frontend-external", "error"), ("x", "unknown")]


def test_re1_fault_metric_answers_match_the_official_mapping():
    assert module.expected_metric("cpu") == "cpu"
    assert module.expected_metric("mem") == "mem"
    assert module.expected_metric("delay") == "latency"
    assert module.expected_metric("loss") == "latency"
    assert module.expected_metric("disk") == "latency"


def test_frozen_split_counts_are_consistent():
    protocol = module.PROTOCOL
    assert protocol["development_cases"] + protocol["evaluation_cases"] == \
        protocol["full_evaluation_cases"] == 375
    assert protocol["development_cases"] == 75
    assert "Avg@5" in protocol["objective"]


def test_window_rows_match_the_official_length_parameter():
    assert module.PROTOCOL["window_rows_per_side"] == \
        module.PROTOCOL["evaluation_length_minutes"] * 60 // 2 == 600
