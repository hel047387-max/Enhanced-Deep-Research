import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command

from deep_research.config import ResearchBudgets
from deep_research.domain.plan import (
    CoverageLevel,
    GapAssessment,
    ResearchBrief,
    ResearchTask,
    TaskStatus,
)
from deep_research.domain.review import ReviewVerdict
from deep_research.graph.builder import (
    WorkflowDependencies,
    build_research_graph,
    build_researcher_graph,
    build_supervisor_graph,
)
from deep_research.tools.search import SearchHit
from tests.fakes import (
    AdaptiveGapModel,
    FakeSearchProvider,
    NeverCancelled,
    RecordingEventSink,
    RecordingReviewerModel,
    RecordingWriterModel,
    ScriptedStructuredModel,
)


def _brief() -> ResearchBrief:
    return ResearchBrief(main_question="What happened?", scope="Three dimensions")


def _task(task_id: str = "task-1", query: str = "initial query") -> ResearchTask:
    return ResearchTask(
        task_id=task_id,
        title=f"Task {task_id}",
        objective=f"Research {task_id}",
        completion_criteria=["Find evidence"],
        search_queries=[query],
    )


def _hit(url: str = "https://example.com/result") -> SearchHit:
    return SearchHit(
        title="Official result",
        url=url,
        content="RAW_PAGE_SECRET Supported result",
    )


def _evidence_output() -> dict[str, object]:
    return {
        "items": [
            {
                "claim": "The result is supported.",
                "excerpt": "Supported result",
                "context": "Official result",
                "relevance": "high",
            }
        ]
    }


class ToggleCancellation:
    def __init__(self) -> None:
        self.cancelled = False
        self.checks = 0

    def raise_if_cancelled(self) -> None:
        self.checks += 1
        if self.cancelled:
            raise RuntimeError("cancelled")


class CancelAfterGapModel:
    def __init__(self, checker: ToggleCancellation) -> None:
        self.checker = checker

    async def ainvoke(self, _input):
        self.checker.cancelled = True
        return GapAssessment(
            task_id="task-1",
            coverage=CoverageLevel.PARTIAL,
            missing_questions=["next fact"],
            next_queries=["targeted query"],
            should_continue=True,
            reason="One fact remains",
        )


class RaisingModel:
    async def ainvoke(self, _input):
        raise RuntimeError("model failed with SECRET_MODEL_TOKEN")


class SelectiveFailSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        self.queries.append(query)
        if query == "query 2":
            raise RuntimeError("provider leaked SECRET_SEARCH_TOKEN")
        return [_hit()][:max_results]


@pytest.mark.asyncio
async def test_cancellation_between_rounds_stops_before_second_search() -> None:
    checker = ToggleCancellation()
    search = FakeSearchProvider(
        {"initial query": [_hit()], "targeted query": [_hit()]}
    )
    graph = build_researcher_graph(
        search_provider=search,
        evidence_model=ScriptedStructuredModel([_evidence_output()]),
        gap_model=CancelAfterGapModel(checker),
        budgets=ResearchBudgets(),
        event_sink=RecordingEventSink(),
        cancellation_checker=checker,
    )

    with pytest.raises(RuntimeError, match="cancelled"):
        await graph.ainvoke(
            {"task": _task(), "research_brief": _brief(), "total_queries": 0}
        )

    assert search.queries == ["initial query"]
    assert checker.checks >= 4


@pytest.mark.asyncio
async def test_researcher_emits_sanitized_agent_core_event_sequence() -> None:
    sink = RecordingEventSink()
    graph = build_researcher_graph(
        search_provider=FakeSearchProvider({"initial query": [_hit()]}),
        evidence_model=ScriptedStructuredModel([_evidence_output()]),
        gap_model=ScriptedStructuredModel(
            [
                GapAssessment(
                    task_id="task-1",
                    coverage=CoverageLevel.SUFFICIENT,
                    should_continue=False,
                    reason="Covered",
                )
            ]
        ),
        budgets=ResearchBudgets(),
        event_sink=sink,
        cancellation_checker=NeverCancelled(),
    )

    await graph.ainvoke(
        {"task": _task(), "research_brief": _brief(), "total_queries": 0}
    )

    assert [event_type for event_type, _ in sink.events] == [
        "task_started",
        "search_started",
        "search_completed",
        "evidence_added",
        "gap_assessed",
        "task_completed",
    ]
    serialized = json.dumps(sink.events)
    assert "RAW_PAGE_SECRET" not in serialized
    assert "initial query" not in serialized
    assert "raw_content" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage", "expected_code"),
    [
        ("search", "search_failed"),
        ("normalization", "source_normalization_failed"),
        ("evidence", "evidence_extraction_failed"),
        ("gap", "gap_analysis_failed"),
    ],
)
async def test_researcher_stage_failures_become_terminal_sanitized_tasks(
    stage,
    expected_code,
) -> None:
    search = (
        SelectiveFailSearch()
        if stage == "search"
        else FakeSearchProvider(
            {
                "initial query": [
                    _hit("http://localhost/private")
                    if stage == "normalization"
                    else _hit()
                ]
            }
        )
    )
    evidence_model = (
        RaisingModel()
        if stage == "evidence"
        else ScriptedStructuredModel([_evidence_output()])
    )
    gap_model = (
        RaisingModel()
        if stage == "gap"
        else ScriptedStructuredModel(
            [
                GapAssessment(
                    task_id="task-1",
                    coverage=CoverageLevel.SUFFICIENT,
                    should_continue=False,
                    reason="Covered",
                )
            ]
        )
    )
    sink = RecordingEventSink()
    graph = build_researcher_graph(
        search_provider=search,
        evidence_model=evidence_model,
        gap_model=gap_model,
        budgets=ResearchBudgets(),
        event_sink=sink,
        cancellation_checker=NeverCancelled(),
    )

    result = await graph.ainvoke(
        {
            "task": _task(query="query 2" if stage == "search" else "initial query"),
            "research_brief": _brief(),
            "total_queries": 0,
        }
    )

    assert result["updated_task"].status is TaskStatus.FAILED
    assert result["gap_assessment"].coverage is CoverageLevel.INSUFFICIENT
    assert result["gap_assessment"].should_continue is False
    assert result["errors"][-1].error_code == expected_code
    serialized = json.dumps(result, default=str) + json.dumps(sink.events)
    assert "SECRET_" not in serialized
    assert sink.events[-1][0] == "task_failed"


@pytest.mark.asyncio
async def test_one_failing_parallel_researcher_preserves_successful_siblings() -> None:
    sink = RecordingEventSink()
    researcher = build_researcher_graph(
        search_provider=SelectiveFailSearch(),
        evidence_model=ScriptedStructuredModel([_evidence_output(), _evidence_output()]),
        gap_model=AdaptiveGapModel(),
        budgets=ResearchBudgets(),
        event_sink=sink,
        cancellation_checker=NeverCancelled(),
    )
    supervisor = build_supervisor_graph(
        researcher_runner=researcher.ainvoke,
        coverage_model=AdaptiveGapModel(),
        budgets=ResearchBudgets(),
    )
    tasks = {
        f"task-{index}": _task(f"task-{index}", f"query {index}")
        for index in range(1, 4)
    }

    result = await supervisor.ainvoke(
        {
            "research_brief": _brief(),
            "tasks": tasks,
            "sources": {},
            "evidence": {},
            "gap_assessments": {},
            "total_queries": 0,
            "coverage_checked": False,
            "supervisor_added_tasks": 0,
            "errors": [],
        }
    )

    assert result["tasks"]["task-2"].status is TaskStatus.FAILED
    assert result["tasks"]["task-1"].status is TaskStatus.COMPLETED
    assert result["tasks"]["task-3"].status is TaskStatus.COMPLETED
    assert {item.task_id for item in result["evidence"].values()} == {
        "task-1",
        "task-3",
    }
    assert "SECRET_SEARCH_TOKEN" not in json.dumps(result, default=str)


@pytest.mark.asyncio
async def test_checkpointer_clarification_resumes_same_thread_and_plans_once() -> None:
    clarifier = ScriptedStructuredModel(
        [
            {
                "needs_clarification": True,
                "question": "Which time range?",
                "reason": "Missing time range",
            },
            ResearchBrief(
                main_question="What happened from 2020 to 2025?",
                scope="Three dimensions",
                time_range="2020-2025",
            ),
        ]
    )
    planner = ScriptedStructuredModel(
        [
            {
                "strategy_summary": "Three dimensions",
                "tasks": [
                    _task(f"task-{index}", f"query {index}").model_dump()
                    for index in range(1, 4)
                ],
            }
        ]
    )
    hit = _hit()
    deps = WorkflowDependencies(
        clarifier_model=clarifier,
        planner_model=planner,
        evidence_model=ScriptedStructuredModel(
            [_evidence_output(), _evidence_output(), _evidence_output()]
        ),
        gap_model=AdaptiveGapModel(),
        writer_model=RecordingWriterModel(),
        reviewer_model=RecordingReviewerModel(ReviewVerdict.PASS),
        search_provider=FakeSearchProvider(
            {f"query {index}": [hit] for index in range(1, 4)}
        ),
        budgets=ResearchBudgets(),
        event_sink=RecordingEventSink(),
        cancellation_checker=NeverCancelled(),
    )
    graph = build_research_graph(
        deps,
        checkpointer=InMemorySaver(
            serde=JsonPlusSerializer(pickle_fallback=True)
        ),
    )
    config = {"configurable": {"thread_id": "thread-clarification"}}
    initial = await graph.ainvoke(
        {
            "run_id": "run-1",
            "thread_id": "thread-clarification",
            "messages": ["Research this market"],
            "clarification_count": 0,
            "tasks": {},
            "sources": {},
            "evidence": {},
            "gap_assessments": {},
            "supervisor_added_tasks": 0,
            "coverage_checked": False,
            "total_queries": 0,
            "review_action_count": 0,
            "errors": [],
            "status": "created",
        },
        config=config,
    )
    assert len(initial["__interrupt__"]) == 1

    result = await graph.ainvoke(Command(resume="2020-2025"), config=config)

    assert result["thread_id"] == "thread-clarification"
    assert result["clarification_count"] == 1
    assert result.get("interrupt_question") is None
    assert len(planner.calls) == 1
    assert len(clarifier.calls) == 2
    assert result["status"] == "completed"
