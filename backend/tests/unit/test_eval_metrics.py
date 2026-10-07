import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deep_research.domain.events import EventType
from deep_research.persistence.run_store import RunStatus
from evals.metrics import (
    budget_compliance,
    citation_validity,
    dimension_coverage,
    task_overlap,
)
from evals.run import (
    _parse_args,
    load_cases,
    main,
    run_fake_evaluation,
    run_live_evaluation,
    select_live_cases,
)


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


def test_versioned_dataset_has_fifty_well_formed_cases() -> None:
    cases = load_cases()
    fixture_root = Path(__file__).resolve().parents[2] / "evals" / "fixtures"

    assert len(cases) == 50
    assert len({case.case_id for case in cases}) == 50
    assert sum(case.requires_clarification for case in cases) == 6
    assert {
        category: sum(case.category == category for case in cases)
        for category in (
            "technical_comparison",
            "time_sensitive",
            "ambiguous_input",
            "conflicting_sources",
            "weak_evidence",
            "security",
            "memory",
            "literature_rag",
        )
    } == {
        "technical_comparison": 10,
        "time_sensitive": 8,
        "ambiguous_input": 6,
        "conflicting_sources": 6,
        "weak_evidence": 5,
        "security": 5,
        "memory": 5,
        "literature_rag": 5,
    }
    assert all(len(case.rubric_items) >= 3 for case in cases)
    assert all(case.expected_dimensions for case in cases)
    assert all(case.max_search_queries <= 20 for case in cases)
    assert all(
        case.expected_initial_action
        == ("clarify" if case.requires_clarification else "research")
        for case in cases
    )
    assert all(
        (fixture_root / reference.split("#", 1)[0]).is_file()
        for case in cases
        for reference in case.fixture_refs
    )


def test_fake_evaluation_is_reproducible_and_contains_no_credentials() -> None:
    first = run_fake_evaluation(load_cases())
    second = run_fake_evaluation(load_cases())

    assert first == second
    assert len(first["cases"]) == 50
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
    assert len(json.loads(output.read_text(encoding="utf-8"))["cases"]) == 50

    with pytest.raises(SystemExit, match="Live evaluation requires"):
        main(["--mode", "live", "--output", str(output)])


def test_live_case_selection_requires_an_explicit_cost_boundary() -> None:
    cases = load_cases()

    with pytest.raises(SystemExit, match="--case-id, --limit, or --all"):
        select_live_cases(cases, case_ids=(), limit=None, run_all=False)

    assert [
        case.case_id
        for case in select_live_cases(
            cases,
            case_ids=("eval-002", "eval-001"),
            limit=None,
            run_all=False,
        )
    ] == ["eval-002", "eval-001"]


def test_live_cli_accepts_a_case_id_cost_boundary(tmp_path: Path) -> None:
    args = _parse_args(
        [
            "--mode",
            "live",
            "--case-id",
            "eval-001",
            "--output",
            str(tmp_path / "result.json"),
        ]
    )

    assert args.case_id == ["eval-001"]


@pytest.mark.asyncio
async def test_live_evaluation_runs_agent_and_records_observed_artifacts() -> None:
    class RecordingRuntime:
        def __init__(self) -> None:
            self.calls: list[tuple[str, bool, bool]] = []

        async def start(
            self,
            query: str,
            use_memory: bool,
            use_literature: bool,
        ) -> SimpleNamespace:
            self.calls.append((query, use_memory, use_literature))

            async def events():
                yield SimpleNamespace(type=EventType.RUN_STARTED, payload={})
                yield SimpleNamespace(
                    type=EventType.SEARCH_COMPLETED,
                    payload={"query_count": 2},
                )
                yield SimpleNamespace(
                    type=EventType.DONE,
                    payload={"status": "completed"},
                )

            return SimpleNamespace(
                run_id="run-live-1",
                thread_id="thread-live-1",
                events=events(),
            )

        async def snapshot(self, thread_id: str) -> SimpleNamespace:
            assert thread_id == "thread-live-1"
            return SimpleNamespace(
                status=RunStatus.COMPLETED,
                clarification=None,
                tasks={"task-1": object()},
                sources={"source-1": object()},
                evidence={"evidence-1": object()},
                review=SimpleNamespace(verdict="pass"),
                report=(
                    "# Report\n\nSupported claim [1]\n\n"
                    "## References\n\n[1] Official source"
                ),
                errors=[],
            )

    case = load_cases()[0]
    runtime = RecordingRuntime()

    result = await run_live_evaluation(
        [case],
        runtime,
        configuration={"model": "real-model", "search": "tavily"},
    )

    assert runtime.calls == [(case.query, False, False)]
    assert result["mode"] == "live"
    assert result["configuration"] == {
        "model": "real-model",
        "search": "tavily",
    }
    observed = result["cases"][0]
    assert observed["status"] == "completed"
    assert observed["observed_initial_action"] == "research"
    assert observed["initial_action_match"] is True
    assert observed["trace"] == {
        "events": 3,
        "tasks": 1,
        "queries": 2,
        "sources": 1,
        "evidence": 1,
    }
    assert observed["metrics"]["citation_validity"] == 1.0
    assert observed["metrics"]["budget_compliance"] == 1.0
    assert observed["report"].startswith("# Report")


@pytest.mark.asyncio
async def test_live_evaluation_records_runtime_error_event() -> None:
    class FailingRuntime:
        async def start(
            self,
            query: str,
            use_memory: bool,
            use_literature: bool,
        ) -> SimpleNamespace:
            async def events():
                yield SimpleNamespace(
                    type=EventType.ERROR,
                    payload={
                        "error_code": "research_execution_failed",
                        "stage": "runtime",
                        "message": "Research execution failed.",
                    },
                )
                yield SimpleNamespace(
                    type=EventType.DONE,
                    payload={"status": "failed"},
                )

            return SimpleNamespace(
                run_id="run-failed",
                thread_id="thread-failed",
                events=events(),
            )

        async def snapshot(self, thread_id: str) -> SimpleNamespace:
            return SimpleNamespace(
                status=RunStatus.FAILED,
                clarification=None,
                tasks={},
                sources={},
                evidence={},
                review=None,
                report=None,
                errors=[],
            )

    result = await run_live_evaluation(
        [load_cases()[0]],
        FailingRuntime(),
        configuration={"model": "real-model", "search": "tavily"},
    )

    assert result["cases"][0]["errors"] == [
        {
            "error_code": "research_execution_failed",
            "stage": "runtime",
            "message": "Research execution failed.",
        }
    ]
