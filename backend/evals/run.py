from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

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


class RubricItem(BaseModel, frozen=True):
    rubric_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    criterion: str = Field(min_length=1)


class EvidenceRequirements(BaseModel, frozen=True):
    min_sources: int = Field(ge=0, le=20)
    citation_required: bool
    require_primary_source: bool
    require_current_sources: bool
    expect_conflicting_sources: bool
    preferred_source_types: list[str]


class EvaluationCase(BaseModel, frozen=True):
    case_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    category: str = Field(min_length=1)
    requires_clarification: bool
    expected_initial_action: Literal["research", "clarify"]
    expected_outcome: Literal["report", "insufficient_evidence"]
    as_of_date: str | None
    expected_dimensions: list[str] = Field(min_length=1)
    required_facts: list[str]
    known_conflicts: list[str]
    required_limitations: list[str]
    rubric_items: list[RubricItem] = Field(min_length=3)
    evidence_requirements: EvidenceRequirements
    max_search_queries: int = Field(ge=1, le=20)
    fixture_refs: list[str]


def load_cases(path: Path = _DATASET_PATH) -> list[EvaluationCase]:
    """Load the fixed JSON Lines dataset in versioned file order."""

    return [
        EvaluationCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def select_live_cases(
    cases: Sequence[EvaluationCase],
    *,
    case_ids: Sequence[str],
    limit: int | None,
    run_all: bool,
) -> list[EvaluationCase]:
    """Select an explicitly bounded set of cases for provider-backed evaluation."""

    if not case_ids and limit is None and not run_all:
        raise SystemExit(
            "Live evaluation requires --case-id, --limit, or --all "
            "to make provider cost explicit."
        )
    if limit is not None:
        if limit < 1:
            raise SystemExit("--limit must be at least 1.")
        return list(cases[:limit])
    if run_all:
        return list(cases)

    cases_by_id = {case.case_id: case for case in cases}
    unknown_ids = [case_id for case_id in case_ids if case_id not in cases_by_id]
    if unknown_ids:
        raise SystemExit(f"Unknown evaluation case ID: {unknown_ids[0]}")
    return [cases_by_id[case_id] for case_id in case_ids]


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
        "dataset_version": "2026-10-06",
        "mode": "fake",
        "configuration": {
            "model": "scripted-structured-model-v1",
            "search": "scripted-search-v1",
        },
        "cases": results,
        "aggregate_metrics": aggregates,
    }


def _report_citation_validity(report: str | None, citation_required: bool) -> float:
    if report is None:
        return 0.0 if citation_required else 1.0
    body, separator, references = report.partition("\n## References")
    used_ids = set(re.findall(r"\[(\d+)\]", body))
    known_ids = (
        set(re.findall(r"(?m)^\[(\d+)\]", references))
        if separator
        else set()
    )
    return citation_validity(used_ids=used_ids, known_ids=known_ids)


def _serialize_live_case(
    case: EvaluationCase,
    handle: Any,
    snapshot: Any,
    events: Sequence[Any],
    latency_ms: float,
) -> dict[str, Any]:
    clarification_requested = any(
        str(event.type) == "clarification_required" for event in events
    )
    observed_initial_action = "clarify" if clarification_requested else "research"
    query_count = sum(
        int(event.payload["query_count"])
        for event in events
        if str(event.type) == "search_completed"
    )
    return {
        "case_id": case.case_id,
        "category": case.category,
        "run_id": handle.run_id,
        "thread_id": handle.thread_id,
        "status": str(snapshot.status),
        "expected_initial_action": case.expected_initial_action,
        "observed_initial_action": observed_initial_action,
        "initial_action_match": observed_initial_action == case.expected_initial_action,
        "expected_outcome": case.expected_outcome,
        "clarification": snapshot.clarification,
        "report": snapshot.report,
        "review_verdict": (
            str(snapshot.review.verdict) if snapshot.review is not None else None
        ),
        "errors": [
            dict(event.payload)
            for event in events
            if str(event.type) == "error"
        ],
        "trace": {
            "events": len(events),
            "tasks": len(snapshot.tasks),
            "queries": query_count,
            "sources": len(snapshot.sources),
            "evidence": len(snapshot.evidence),
        },
        "metrics": {
            "citation_validity": _report_citation_validity(
                snapshot.report,
                case.evidence_requirements.citation_required,
            ),
            "budget_compliance": float(query_count <= case.max_search_queries),
            "source_requirement": float(
                len(snapshot.sources) >= case.evidence_requirements.min_sources
            ),
            "latency_ms": latency_ms,
        },
        "rubric_items": [
            {**item.model_dump(), "status": "not_scored"}
            for item in case.rubric_items
        ],
    }


async def run_live_evaluation(
    cases: Sequence[EvaluationCase],
    runtime: Any,
    *,
    configuration: Mapping[str, str],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in cases:
        started = perf_counter()
        handle = await runtime.start(
            case.query,
            use_memory=case.category == "memory",
            use_literature=case.category == "literature_rag",
        )
        events = [event async for event in handle.events]
        snapshot = await runtime.snapshot(handle.thread_id)
        results.append(
            _serialize_live_case(
                case,
                handle,
                snapshot,
                events,
                (perf_counter() - started) * 1000,
            )
        )

    return {
        "dataset_version": "2026-10-06",
        "mode": "live",
        "configuration": dict(configuration),
        "cases": results,
        "aggregate_metrics": {
            "initial_action_accuracy": sum(
                result["initial_action_match"] for result in results
            )
            / len(results),
            "citation_validity": sum(
                result["metrics"]["citation_validity"] for result in results
            )
            / len(results),
            "budget_compliance": sum(
                result["metrics"]["budget_compliance"] for result in results
            )
            / len(results),
            "source_requirement": sum(
                result["metrics"]["source_requirement"] for result in results
            )
            / len(results),
        },
    }


async def _run_production_live_evaluation(
    cases: Sequence[EvaluationCase],
) -> dict[str, Any]:
    from deep_research.api.main import create_app
    from deep_research.config import get_settings

    settings = get_settings()
    application = create_app(settings=settings)
    async with application.router.lifespan_context(application):
        return await run_live_evaluation(
            cases,
            application.state.runtime,
            configuration={
                "model": f"{settings.llm_provider}:{settings.llm_model}",
                "search": "tavily",
            },
        )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Deep Research evaluations")
    parser.add_argument("--mode", choices=("fake", "live"), default="fake")
    parser.add_argument(
        "--live",
        action="store_true",
        help="explicitly request provider-backed live mode",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--case-id", action="append", default=[])
    selection.add_argument("--limit", type=int)
    selection.add_argument("--all", action="store_true", dest="run_all")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    mode = "live" if args.live else args.mode
    if mode == "live":
        selected = select_live_cases(
            load_cases(),
            case_ids=args.case_id,
            limit=args.limit,
            run_all=args.run_all,
        )
        result = asyncio.run(_run_production_live_evaluation(selected))
    else:
        result = run_fake_evaluation(load_cases())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"{mode} evaluation complete: {len(result['cases'])} cases -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
