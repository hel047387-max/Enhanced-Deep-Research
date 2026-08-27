import asyncio
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
from deep_research.graph.builder import build_researcher_graph, build_supervisor_graph
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
