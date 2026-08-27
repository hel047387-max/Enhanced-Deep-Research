import asyncio
import json
import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from deep_research.config import ResearchBudgets
from deep_research.domain.plan import (
    CoverageLevel,
    GapAssessment,
    ResearchBrief,
    ResearchTask,
    TaskStatus,
)
from deep_research.domain.review import ReviewResult, ReviewVerdict
from deep_research.graph.builder import (
    WorkflowDependencies,
    build_research_graph,
    build_researcher_graph,
    build_supervisor_graph,
)
from deep_research.tools.search import SearchHit


class FakeSearchProvider:
    def __init__(self, scripted_hits: dict[str, list[SearchHit]]) -> None:
        self.scripted_hits = scripted_hits
        self.queries: list[str] = []

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        self.queries.append(query)
        return self.scripted_hits.get(query, [])[:max_results]


class ScriptedStructuredModel:
    def __init__(self, scripted_outputs: Sequence[BaseModel | dict[str, object]]) -> None:
        self._scripted_outputs = list(scripted_outputs)
        self.calls: list[Any] = []

    async def ainvoke(self, input: Any) -> BaseModel | dict[str, object]:
        self.calls.append(input)
        if not self._scripted_outputs:
            raise AssertionError("No scripted structured output remains")
        return self._scripted_outputs.pop(0)


class ResearcherHarness:
    def __init__(
        self,
        gaps: list[GapAssessment],
        total_queries: int = 0,
    ) -> None:
        self.task = ResearchTask(
            task_id="task-1",
            title="Market scale",
            objective="Measure market scale",
            completion_criteria=["Find an official estimate"],
            search_queries=["initial query"],
        )
        self.brief = ResearchBrief(
            main_question="How large is the market?",
            scope="Global market scale",
            source_preferences=["official sources"],
        )
        hit = SearchHit(
            title="Official data",
            url="https://example.com/data",
            content="The market reached 100 units.",
            raw_content="<html>raw page body</html>",
        )
        self.search = FakeSearchProvider(
            {"initial query": [hit], "targeted query": [hit]}
        )
        evidence_outputs = [
            {
                "items": [
                    {
                        "claim": "The market reached 100 units.",
                        "excerpt": "reached 100 units",
                        "context": "Official market estimate",
                        "relevance": "high",
                    }
                ]
            }
            for _ in gaps
        ]
        self.total_queries = total_queries
        self.graph = build_researcher_graph(
            search_provider=self.search,
            evidence_model=ScriptedStructuredModel(evidence_outputs),
            gap_model=ScriptedStructuredModel(gaps),
            budgets=ResearchBudgets(),
            event_sink=RecordingEventSink(),
            cancellation_checker=NeverCancelled(),
        )

    async def ainvoke(self, input_state: dict[str, object]) -> dict[str, object]:
        return await self.graph.ainvoke(
            {**input_state, "total_queries": self.total_queries}
        )


class SupervisorHarness:
    def __init__(self) -> None:
        self.active_workers = 0
        self.peak_concurrency = 0
        self.query_grants: list[int] = []
        self._lock = asyncio.Lock()
        self._coverage_model: ScriptedStructuredModel | None = None

    @property
    def coverage_calls(self) -> int:
        return len(self._coverage_model.calls) if self._coverage_model else 0

    async def _worker(self, input_state: dict[str, object]) -> dict[str, object]:
        task = ResearchTask.model_validate(input_state["task"])
        grant = int(input_state["query_budget"])
        self.query_grants.append(grant)
        async with self._lock:
            self.active_workers += 1
            self.peak_concurrency = max(
                self.peak_concurrency, self.active_workers
            )
        try:
            await asyncio.sleep(0.01)
        finally:
            async with self._lock:
                self.active_workers -= 1
        return {
            "updated_task": task.model_copy(
                update={"status": TaskStatus.COMPLETED, "current_round": 1}
            ),
            "sources": {},
            "evidence": {},
            "gap_assessment": GapAssessment(
                task_id=task.task_id,
                coverage=CoverageLevel.SUFFICIENT,
                should_continue=False,
                reason="Covered",
            ),
            "errors": [],
            "queries_used": grant,
        }

    @staticmethod
    def _tasks(task_count: int) -> dict[str, ResearchTask]:
        return {
            f"task-{index}": ResearchTask(
                task_id=f"task-{index}",
                title=f"Task {index}",
                objective=f"Research subproblem {index}",
                completion_criteria=["Find evidence"],
                search_queries=[f"query {index}"],
            )
            for index in range(1, task_count + 1)
        }

    async def _run(
        self,
        tasks: dict[str, ResearchTask],
        coverage_output: dict[str, object],
    ) -> dict[str, object]:
        self._coverage_model = ScriptedStructuredModel([coverage_output])
        graph = build_supervisor_graph(
            researcher_runner=self._worker,
            coverage_model=self._coverage_model,
            budgets=ResearchBudgets(),
        )
        brief = ResearchBrief(
            main_question="Test question",
            scope="Test scope",
        )
        return await graph.ainvoke(
            {
                "research_brief": brief,
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

    async def run_with_tasks(self, task_count: int) -> dict[str, object]:
        return await self._run(
            self._tasks(task_count),
            {"sufficient": True, "additional_tasks": []},
        )

    async def run_with_coverage(
        self, additional_task_count: int
    ) -> dict[str, object]:
        added = [
            ResearchTask(
                task_id=f"added-{index}",
                title=f"Added {index}",
                objective=f"Fill gap {index}",
                completion_criteria=["Close gap"],
                search_queries=[f"gap query {index}"],
                parent_task_id="task-1",
                gap_reason=f"Missing dimension {index}",
            ).model_dump()
            for index in range(1, additional_task_count + 1)
        ]
        return await self._run(
            self._tasks(1),
            {
                "sufficient": False,
                "global_gaps": ["Missing dimensions"],
                "additional_tasks": added,
            },
        )


class AdaptiveGapModel:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def ainvoke(self, input: object) -> dict[str, object]:
        self.calls.append(input)
        if "Assess global coverage once" in str(input):
            return {
                "sufficient": True,
                "covered_dimensions": ["all planned dimensions"],
                "additional_tasks": [],
            }
        match = re.search(r"Task ID: ([^.;]+)", str(input))
        if match is None:
            raise AssertionError("Gap prompt did not include the task ID")
        return {
            "task_id": match.group(1),
            "coverage": "sufficient",
            "covered_questions": ["completion criterion"],
            "should_continue": False,
            "reason": "Covered",
        }


class RecordingWriterModel:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def ainvoke(self, input: object) -> dict[str, object]:
        self.calls.append(input)
        payload = json.loads(input[-1].content)
        evidence_id = min(payload["evidence"])
        return {
            "title": "Research report",
            "executive_summary": [
                {
                    "paragraph_id": "summary-1",
                    "text": "The evidence supports the result.",
                    "evidence_ids": [evidence_id],
                }
            ],
            "sections": [],
            "limitations": [],
            "suggested_actions": ["Monitor updates"],
        }


class RecordingReviewerModel:
    def __init__(self, verdict: ReviewVerdict) -> None:
        self.verdict = verdict
        self.calls: list[object] = []

    async def ainvoke(self, input: object) -> ReviewResult:
        self.calls.append(input)
        follow_up_tasks = []
        if self.verdict is ReviewVerdict.RESEARCH_GAP:
            follow_up_tasks = [
                ResearchTask(
                    task_id="review-task",
                    title="Targeted review gap",
                    objective="Fill the reviewer evidence gap",
                    completion_criteria=["Find targeted evidence"],
                    search_queries=["review query"],
                    parent_task_id="task-1",
                    gap_reason="Reviewer identified a missing fact",
                )
            ]
        return ReviewResult(
            verdict=self.verdict,
            revision_instructions=(
                ["Tighten the supported wording"]
                if self.verdict is not ReviewVerdict.PASS
                else []
            ),
            follow_up_tasks=follow_up_tasks,
        )


class RaisingStructuredModel:
    def __init__(self, message: str) -> None:
        self.message = message
        self.calls: list[object] = []

    async def ainvoke(self, input: object) -> dict[str, object]:
        self.calls.append(input)
        raise RuntimeError(self.message)


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def emit(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, payload))


class NeverCancelled:
    def raise_if_cancelled(self) -> None:
        return None


class GraphHarness:
    def __init__(self) -> None:
        self._writer_model = RecordingWriterModel()
        self._reviewer_model: object | None = None
        self._last_result: dict[str, object] | None = None

    @property
    def writer_calls(self) -> int:
        return len(self._writer_model.calls)

    @property
    def reviewer_calls(self) -> int:
        return len(self._reviewer_model.calls) if self._reviewer_model else 0

    @property
    def review_task_count(self) -> int:
        if self._last_result is None:
            return 0
        return int("review-task" in self._last_result["tasks"])

    @staticmethod
    def _plan() -> dict[str, object]:
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

    async def _run(
        self,
        verdict: ReviewVerdict,
        with_evidence: bool,
        *,
        reviewer_model: object | None = None,
        budgets: ResearchBudgets | None = None,
    ) -> dict[str, object]:
        self._writer_model = RecordingWriterModel()
        self._reviewer_model = reviewer_model or RecordingReviewerModel(verdict)
        hit = SearchHit(
            title="Official result",
            url="https://example.com/result",
            content="The official result supports the claim.",
        )
        hits = [hit] if with_evidence else []
        search = FakeSearchProvider(
            {
                "query 1": hits,
                "query 2": hits,
                "query 3": hits,
                "review query": hits,
            }
        )
        evidence_model = ScriptedStructuredModel(
            [
                {
                    "items": [
                        {
                            "claim": "The official result supports the claim.",
                            "excerpt": "supports the claim",
                            "context": "Official result",
                            "relevance": "high",
                        }
                    ]
                }
                for _ in range(4)
            ]
        )
        clarifier_model = ScriptedStructuredModel(
            [
                {
                    "needs_clarification": False,
                    "question": None,
                    "reason": "Request is clear",
                },
                ResearchBrief(
                    main_question="What does the evidence show?",
                    scope="Three evidence dimensions",
                    source_preferences=["official sources"],
                ),
            ]
        )
        deps = WorkflowDependencies(
            clarifier_model=clarifier_model,
            planner_model=ScriptedStructuredModel([self._plan()]),
            evidence_model=evidence_model,
            gap_model=AdaptiveGapModel(),
            writer_model=self._writer_model,
            reviewer_model=self._reviewer_model,
            search_provider=search,
            budgets=budgets or ResearchBudgets(),
            event_sink=RecordingEventSink(),
            cancellation_checker=NeverCancelled(),
        )
        graph = build_research_graph(deps)
        self._last_result = await graph.ainvoke(
            {
                "run_id": "run-1",
                "thread_id": "thread-1",
                "messages": ["What does the evidence show?"],
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
            }
        )
        return self._last_result

    async def run(self, verdict: str) -> dict[str, object]:
        return await self._run(ReviewVerdict(verdict), with_evidence=True)

    async def run_without_evidence(self) -> dict[str, object]:
        return await self._run(ReviewVerdict.PASS, with_evidence=False)

    async def run_with_reviewer_failure(self) -> dict[str, object]:
        return await self._run(
            ReviewVerdict.PASS,
            with_evidence=True,
            reviewer_model=RaisingStructuredModel(
                "upstream reviewer failed with SECRET_REVIEW_TOKEN"
            ),
        )

    async def run_with_reviewer_task_budget(
        self, max_reviewer_tasks: int
    ) -> dict[str, object]:
        return await self._run(
            ReviewVerdict.RESEARCH_GAP,
            with_evidence=True,
            budgets=ResearchBudgets(max_reviewer_tasks=max_reviewer_tasks),
        )
