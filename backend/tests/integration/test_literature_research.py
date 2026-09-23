from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from deep_research.application.research_adapter import ResearchAdapter
from deep_research.config import ResearchBudgets
from deep_research.domain.evidence import LiteratureSource, Source, SourceType
from deep_research.domain.literature import RetrievedUnit, SearchableUnit
from deep_research.domain.plan import ResearchBrief, ResearchTask
from deep_research.graph.builder import build_researcher_graph
from deep_research.services.citations import render_source_reference
from tests.fakes import (
    FakeSearchProvider,
    NeverCancelled,
    RecordingEventSink,
    ScriptedStructuredModel,
)


def make_unit() -> SearchableUnit:
    return SearchableUnit(
        unit_id=UUID("11111111-1111-4111-8111-111111111111"),
        document_id=UUID("22222222-2222-4222-8222-222222222222"),
        title="RAG paper",
        authors=["Author"],
        publication_year=2025,
        doi="10.1/example",
        language="en",
        tags=["RAG"],
        heading_path=["Methods"],
        page_start=12,
        page_end=13,
        content_type="paragraph",
        text="The paper supports hybrid retrieval.",
    )


class FakeRetriever:
    async def search(self, request):
        return [RetrievedUnit(unit=make_unit(), similarity_score=0.9)]


def evidence_output() -> dict[str, object]:
    return {
        "items": [
            {
                "claim": "Hybrid retrieval is supported.",
                "excerpt": "supports hybrid retrieval",
                "context": "Evaluation result",
                "relevance": "high",
            }
        ]
    }


def test_literature_source_needs_no_url_and_renders_location() -> None:
    unit = make_unit()
    source = LiteratureSource(
        source_id=f"lit-{unit.unit_id}",
        document_id=unit.document_id,
        unit_id=unit.unit_id,
        title=unit.title,
        authors=unit.authors,
        publication_year=unit.publication_year,
        doi=unit.doi,
        heading_path=unit.heading_path,
        page_start=unit.page_start,
        page_end=unit.page_end,
        retrieved_at=datetime.now(UTC),
    )

    assert source.source_kind == "literature"
    assert "pp. 12-13" in render_source_reference(source)


def test_web_source_still_rejects_localhost() -> None:
    with pytest.raises(ValidationError):
        Source(
            source_id="src-local",
            url="http://localhost/private",
            canonical_url="http://localhost/private",
            title="Local",
            domain="localhost",
            retrieved_at=datetime.now(UTC),
            content_hash="hash",
            source_type=SourceType.WEB,
        )


@pytest.mark.asyncio
async def test_researcher_admits_literature_as_current_run_evidence() -> None:
    task = ResearchTask(
        task_id="task-1",
        title="RAG evidence",
        objective="Find literature evidence",
        completion_criteria=["Find grounded evidence"],
        search_queries=["hybrid retrieval"],
    )
    brief = ResearchBrief(
        main_question="Does hybrid retrieval help?",
        scope="Indexed literature",
    )
    evidence_model = ScriptedStructuredModel([evidence_output()])
    adapter = ResearchAdapter(FakeRetriever(), evidence_model)
    graph = build_researcher_graph(
        search_provider=FakeSearchProvider({"hybrid retrieval": []}),
        evidence_model=ScriptedStructuredModel([]),
        gap_model=ScriptedStructuredModel(
            [
                {
                    "task_id": "task-1",
                    "coverage": "sufficient",
                    "covered_questions": ["Find grounded evidence"],
                    "should_continue": False,
                    "reason": "Literature evidence is sufficient",
                }
            ]
        ),
        budgets=ResearchBudgets(max_research_rounds=1),
        event_sink=RecordingEventSink(),
        cancellation_checker=NeverCancelled(),
        literature_adapter=adapter,
    )

    result = await graph.ainvoke(
        {
            "task": task,
            "research_brief": brief,
            "total_queries": 0,
            "query_budget": 1,
            "use_literature": True,
        }
    )

    assert any(source.source_kind == "literature" for source in result["sources"].values())
    assert all(item.source_id in result["sources"] for item in result["evidence"].values())
    assert result["updated_task"].status.value == "completed"