import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from deep_research.api.main import create_app
from deep_research.config import ResearchBudgets
from deep_research.domain.plan import (
    CoverageLevel,
    GapAssessment,
    ResearchBrief,
    ResearchPlan,
    ResearchTask,
)
from deep_research.domain.review import ReviewVerdict
from deep_research.graph.builder import WorkflowDependencies, build_research_graph
from deep_research.persistence.checkpoint import checkpoint_context
from deep_research.persistence.run_store import RunMetadata, RunStatus, RunStore
from deep_research.services.cancellation import CancellationRegistry
from deep_research.services.event_stream import EventPublisher
from deep_research.services.runtime import (
    ResearchRuntime,
    RuntimeCancellationChecker,
    RuntimeEventSink,
)
from deep_research.tools.search import SearchHit
from tests.fakes import (
    AdaptiveGapModel,
    FakeSearchProvider,
    GraphHarness,
    RecordingReviewerModel,
    RecordingWriterModel,
    ResearcherHarness,
    ScriptedStructuredModel,
    SupervisorHarness,
)


class RuntimeClarifierModel:
    async def ainvoke(self, input):
        prompt = input[0].content
        messages = " ".join(str(message.content) for message in input[1:])
        if "ClarificationDecision" in prompt:
            ambiguous = "Ambiguous topic" in messages
            return {
                "needs_clarification": ambiguous,
                "question": "Which market and time range?" if ambiguous else None,
                "reason": "Essential scope is missing" if ambiguous else "Scope is clear",
            }
        return ResearchBrief(
            main_question="What does the evidence show?",
            scope="EU market",
            time_range="2024-2026",
            source_preferences=["official sources"],
        )


class RuntimePlannerModel:
    async def ainvoke(self, _input):
        return {
            "strategy_summary": "Cover three independent dimensions.",
            "tasks": [
                {
                    "task_id": f"task-{index}",
                    "title": f"Dimension {index}",
                    "objective": f"Research dimension {index}",
                    "completion_criteria": ["Find grounded evidence"],
                    "search_queries": [f"query {index}"],
                }
                for index in range(1, 4)
            ],
        }


class RuntimeEvidenceModel:
    async def ainvoke(self, _input):
        return {
            "items": [
                {
                    "claim": "The official result supports the claim.",
                    "excerpt": "supports the claim",
                    "context": "Official result",
                    "relevance": "high",
                }
            ]
        }


@dataclass
class RuntimeHarness:
    runtime: ResearchRuntime
    store: RunStore

    async def wait_until(
        self,
        run_id: str,
        status: RunStatus,
    ) -> RunMetadata:
        async def wait() -> RunMetadata:
            while True:
                metadata = await self.store.get_run(run_id)
                if metadata is not None and metadata.status is status:
                    return metadata
                if metadata is not None and metadata.status in {
                    RunStatus.COMPLETED,
                    RunStatus.FAILED,
                    RunStatus.CANCELLED,
                    RunStatus.WAITING_FOR_USER,
                }:
                    raise AssertionError(
                        f"run reached {metadata.status.value}, expected {status.value}; "
                        f"last_error={metadata.last_error!r}"
                    )
                await asyncio.sleep(0.01)

        return await asyncio.wait_for(wait(), timeout=5)


def runtime_dependencies(
    publisher: EventPublisher,
    cancellation: CancellationRegistry,
) -> WorkflowDependencies:
    hit = SearchHit(
        title="Official result",
        url="https://example.com/result",
        content="The official result supports the claim.",
    )
    return WorkflowDependencies(
        clarifier_model=RuntimeClarifierModel(),
        planner_model=RuntimePlannerModel(),
        evidence_model=RuntimeEvidenceModel(),
        gap_model=AdaptiveGapModel(),
        writer_model=RecordingWriterModel(),
        reviewer_model=RecordingReviewerModel(ReviewVerdict.PASS),
        search_provider=FakeSearchProvider(
            {f"query {index}": [hit] for index in range(1, 4)}
        ),
        budgets=ResearchBudgets(),
        event_sink=RuntimeEventSink(publisher),
        cancellation_checker=RuntimeCancellationChecker(cancellation),
    )


@pytest.fixture
async def runtime_harness(tmp_path: Path):
    database = tmp_path / "research.sqlite"
    store = RunStore(database)
    await store.initialize()
    publisher = EventPublisher()
    cancellation = CancellationRegistry()
    async with checkpoint_context(database) as checkpointer:
        graph = build_research_graph(
            runtime_dependencies(publisher, cancellation),
            checkpointer=checkpointer,
        )
        runtime = ResearchRuntime(graph, store, publisher, cancellation)
        harness = RuntimeHarness(runtime, store)
        try:
            yield harness
        finally:
            await runtime.close()


@pytest.fixture
def api_app(runtime_harness):
    return create_app(
        runtime_harness.runtime,
        cors_origins=["https://allowed.example"],
    )


@pytest.fixture
async def async_client(api_app):
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
async def running_thread_id(runtime_harness):
    handle = await runtime_harness.runtime.start("Ambiguous topic")
    await runtime_harness.wait_until(handle.run_id, RunStatus.WAITING_FOR_USER)
    return handle.thread_id


@pytest.fixture
def brief() -> ResearchBrief:
    return ResearchBrief(
        main_question="How is the market growing?",
        scope="Global market fundamentals",
        time_range="2024-2026",
        comparison_dimensions=["growth", "competition"],
        source_preferences=["official sources"],
    )


@pytest.fixture
def three_task_plan() -> ResearchPlan:
    return ResearchPlan(
        strategy_summary="Cover scale, competition, and outlook independently.",
        tasks=[
            ResearchTask(
                task_id=f"task-{index}",
                title=title,
                objective=objective,
                completion_criteria=["Find one grounded answer"],
                search_queries=[query],
            )
            for index, (title, objective, query) in enumerate(
                [
                    ("Scale", "Measure market scale", "market scale"),
                    ("Competition", "Map competitors", "market competitors"),
                    ("Outlook", "Assess outlook", "market outlook"),
                ],
                start=1,
            )
        ],
    )


@pytest.fixture
def model_factory() -> Callable[[BaseModel | dict[str, object]], ScriptedStructuredModel]:
    return lambda result: ScriptedStructuredModel([result])


@pytest.fixture
def partial_gap() -> GapAssessment:
    return GapAssessment(
        task_id="task-1",
        coverage=CoverageLevel.PARTIAL,
        covered_questions=["market size"],
        missing_questions=["growth rate"],
        next_queries=["targeted query"],
        should_continue=True,
        reason="Growth rate remains missing",
    )


@pytest.fixture
def sufficient_gap() -> GapAssessment:
    return GapAssessment(
        task_id="task-1",
        coverage=CoverageLevel.SUFFICIENT,
        covered_questions=["market size", "growth rate"],
        should_continue=False,
        reason="Completion criteria are covered",
    )


@pytest.fixture
def researcher_factory() -> Callable[[list[GapAssessment], int], ResearcherHarness]:
    return lambda gaps, total_queries=0: ResearcherHarness(gaps, total_queries)


@pytest.fixture
def supervisor_harness() -> SupervisorHarness:
    return SupervisorHarness()


@pytest.fixture
def graph_harness() -> GraphHarness:
    return GraphHarness()
