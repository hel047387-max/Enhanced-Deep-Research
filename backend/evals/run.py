from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evals.metrics import (
    budget_compliance,
    citation_validity,
    dimension_coverage,
    task_overlap,
)

_DATASET_PATH = Path(__file__).with_name("cases.jsonl")
_BUDGET_LIMITS = {
    "initial_tasks": 5,
    "supervisor_tasks": 2,
    "reviewer_tasks": 1,
    "concurrency": 3,
    "queries": 20,
    "rounds": 2,
    "queries_per_round": 2,
}


class EvaluationCase(BaseModel, frozen=True):
    case_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    category: str = Field(min_length=1)
    requires_clarification: bool
    expected_dimensions: list[str] = Field(min_length=1)


def load_cases(path: Path = _DATASET_PATH) -> list[EvaluationCase]:
    """Load the fixed JSON Lines dataset in versioned file order."""

    return [
        EvaluationCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _fake_case_result(case: EvaluationCase) -> dict[str, Any]:
    task_queries = [[f"{case.case_id} {dimension}"] for dimension in case.expected_dimensions]
    known_ids = {f"{case.case_id}-ev-{index}" for index in range(len(task_queries))}
    counters = {
        "initial_tasks": min(5, max(3, len(task_queries))),
        "supervisor_tasks": 0,
        "reviewer_tasks": 0,
        "concurrency": min(3, len(task_queries)),
        "queries": len(task_queries),
        "rounds": 1,
        "queries_per_round": 1,
    }
    return {
        "case_id": case.case_id,
        "category": case.category,
        "status": (
            "completed_after_clarification"
            if case.requires_clarification
            else "completed"
        ),
        "requires_clarification": case.requires_clarification,
        "trace": counters,
        "metrics": {
            "plan_coverage": dimension_coverage(
                set(case.expected_dimensions), set(case.expected_dimensions)
            ),
            "task_overlap": task_overlap(task_queries),
            "citation_validity": citation_validity(
                used_ids=known_ids,
                known_ids=known_ids,
            ),
            "evidence_grounding": 1.0,
            "source_diversity": float(len(task_queries)),
            "budget_compliance": budget_compliance(counters, _BUDGET_LIMITS),
            "latency_ms": 0.0,
            "recovery_success": 1.0,
            "failure_transparency": 1.0,
        },
    }


def run_fake_evaluation(cases: Sequence[EvaluationCase]) -> dict[str, Any]:
    """Evaluate fixed scripted outcomes without calling a model or network."""

    results = [_fake_case_result(case) for case in cases]
    metric_names = tuple(results[0]["metrics"]) if results else ()
    aggregates = {
        name: sum(result["metrics"][name] for result in results) / len(results)
        for name in metric_names
    } if results else {}
    return {
        "dataset_version": "2026-08-26",
        "mode": "fake",
        "configuration": {
            "model": "scripted-structured-model-v1",
            "search": "scripted-search-v1",
        },
        "cases": results,
        "aggregate_metrics": aggregates,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Deep Research evaluations")
    parser.add_argument("--mode", choices=("fake", "live"), default="fake")
    parser.add_argument(
        "--live",
        action="store_true",
        help="explicitly request live mode (requires an application-supplied runner)",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    mode = "live" if args.live else args.mode
    if mode == "live":
        raise SystemExit(
            "Live evaluation requires an application-supplied runner and provider "
            "credentials; it is never enabled by default."
        )

    result = run_fake_evaluation(load_cases())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"fake evaluation complete: {len(result['cases'])} cases -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
