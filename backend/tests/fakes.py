from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from deep_research.config import ResearchBudgets
from deep_research.domain.plan import GapAssessment, ResearchBrief, ResearchTask
from deep_research.graph.builder import build_researcher_graph
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
