from __future__ import annotations

from uuid import UUID

import pytest

from deep_research.application.answer_service import (
    AnswerService,
    InsufficientLiteratureEvidence,
    InvalidLiteratureCitation,
)
from deep_research.application.context_builder import LiteratureContext
from deep_research.domain.literature import (
    LiteratureSearchRequest,
    RetrievedUnit,
    SearchableUnit,
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
    def __init__(self, results: list[RetrievedUnit]) -> None:
        self.results = results

    async def search(self, request: LiteratureSearchRequest) -> list[RetrievedUnit]:
        return self.results


class FakeContextBuilder:
    def __init__(self, units: list[SearchableUnit]) -> None:
        self.units = units

    async def build(self, results: list[RetrievedUnit]) -> LiteratureContext:
        return LiteratureContext(text="grounded context", units=self.units)


class FakeModel:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output

    async def ainvoke(self, input):
        return self.output


@pytest.mark.asyncio
async def test_answer_accepts_selected_unit_citations() -> None:
    unit = make_unit()
    service = AnswerService(
        FakeRetriever([RetrievedUnit(unit=unit, similarity_score=0.8)]),
        FakeContextBuilder([unit]),
        FakeModel(
            {
                "answer": "The literature supports hybrid retrieval.",
                "citation_unit_ids": [str(unit.unit_id)],
            }
        ),
    )

    answer = await service.answer(LiteratureSearchRequest(query="What is supported?"))

    assert answer.citations[0].page_start == 12
    assert answer.citations[0].page_end == 13
    assert answer.citations[0].unit_id == unit.unit_id


@pytest.mark.asyncio
async def test_answer_rejects_unknown_unit_citation() -> None:
    unit = make_unit()
    service = AnswerService(
        FakeRetriever([RetrievedUnit(unit=unit, similarity_score=0.8)]),
        FakeContextBuilder([unit]),
        FakeModel(
            {
                "answer": "Unsupported answer.",
                "citation_unit_ids": ["33333333-3333-4333-8333-333333333333"],
            }
        ),
    )

    with pytest.raises(InvalidLiteratureCitation):
        await service.answer(LiteratureSearchRequest(query="What is supported?"))


@pytest.mark.asyncio
async def test_answer_reports_insufficient_evidence() -> None:
    service = AnswerService(
        FakeRetriever([]),
        FakeContextBuilder([]),
        FakeModel({"answer": "unused", "citation_unit_ids": []}),
    )

    with pytest.raises(InsufficientLiteratureEvidence):
        await service.answer(LiteratureSearchRequest(query="Unknown topic"))