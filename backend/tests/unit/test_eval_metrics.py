import json
from pathlib import Path

import pytest

from evals.metrics import (
    budget_compliance,
    citation_validity,
    dimension_coverage,
    task_overlap,
)
from evals.run import load_cases, main, run_fake_evaluation


def test_citation_validity_counts_only_resolvable_ids() -> None:
    assert citation_validity(
        used_ids={"ev-1", "ev-missing"},
        known_ids={"ev-1", "ev-2"},
    ) == 0.5


def test_task_overlap_detects_duplicate_query_sets() -> None:
    tasks = [["langgraph checkpoint"], ["langgraph checkpoint"], ["sse cancellation"]]

    assert task_overlap(tasks) == 1 / 3


def test_coverage_and_budget_metrics_are_deterministic() -> None:
    assert dimension_coverage({"cost", "latency"}, {"cost", "latency", "quality"}) == 2 / 3
    assert budget_compliance(
        {"queries": 20, "concurrency": 3},
        {"queries": 20, "concurrency": 3},
    ) == 1.0
    assert budget_compliance(
        {"queries": 21, "concurrency": 3},
        {"queries": 20, "concurrency": 3},
    ) == 0.0


def test_versioned_dataset_has_exactly_fifteen_well_formed_cases() -> None:
    cases = load_cases()

    assert len(cases) == 15
    assert len({case.case_id for case in cases}) == 15
    assert sum(case.requires_clarification for case in cases) == 2
    assert all(case.expected_dimensions for case in cases)


def test_fake_evaluation_is_reproducible_and_contains_no_credentials() -> None:
    first = run_fake_evaluation(load_cases())
    second = run_fake_evaluation(load_cases())

    assert first == second
    assert len(first["cases"]) == 15
    assert first["configuration"] == {
        "model": "scripted-structured-model-v1",
        "search": "scripted-search-v1",
    }
    assert first["aggregate_metrics"]["budget_compliance"] == 1.0
    serialized = json.dumps(first)
    assert "api_key" not in serialized.casefold()
    assert "secret" not in serialized.casefold()


def test_cli_writes_fake_results_and_live_mode_requires_explicit_runner(
    tmp_path: Path,
) -> None:
    output = tmp_path / "eval.json"

    assert main(["--mode", "fake", "--output", str(output)]) == 0
    assert len(json.loads(output.read_text(encoding="utf-8"))["cases"]) == 15

    with pytest.raises(SystemExit, match="Live evaluation requires"):
        main(["--mode", "live", "--output", str(output)])
