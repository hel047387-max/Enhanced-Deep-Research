from __future__ import annotations

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from deep_research.api.literature_routes import LiteratureApplication
from deep_research.api.main import create_app
from deep_research.config import Settings
from deep_research.domain.literature import (
    IngestedDocument,
    LiteratureAnswer,
    LiteratureCitation,
    LiteratureMetadata,
    RetrievedUnit,
    SearchableUnit,
)


class FakeProcessor:
    def __init__(self) -> None:
        self.ingest_calls: list[tuple[str, bytes, LiteratureMetadata]] = []
        self.deleted: list[UUID] = []

    async def ingest(
        self,
        filename: str,
        content: bytes,
        metadata: LiteratureMetadata,
    ) -> IngestedDocument:
        self.ingest_calls.append((filename, content, metadata))
        return IngestedDocument(
            document_id=UUID("22222222-2222-4222-8222-222222222222"),
            units_indexed=2,
            metadata=metadata,
        )

    async def delete(self, document_id: UUID) -> None:
        self.deleted.append(document_id)


class FakeRetriever:
    def __init__(self) -> None:
        self.requests = []
        self.unit = SearchableUnit(
            unit_id=UUID("11111111-1111-4111-8111-111111111111"),
            document_id=UUID("22222222-2222-4222-8222-222222222222"),
            title="RAG paper",
            authors=["Author"],
            publication_year=2025,
            doi="10.1/example",
            language="en",
            tags=["RAG"],
            heading_path=["Methods"],
            page_start=2,
            page_end=2,
            content_type="paragraph",
            text="Hybrid retrieval evidence.",
        )

    async def search(self, request):
        self.requests.append(request)
        return [RetrievedUnit(unit=self.unit, similarity_score=0.8, rerank_score=0.9)]

class FakeAnswerService:
    async def answer(self, request):
        return LiteratureAnswer(
            answer="Grounded answer.",
            citations=[
                LiteratureCitation(
                    unit_id=UUID("11111111-1111-4111-8111-111111111111"),
                    document_id=UUID("22222222-2222-4222-8222-222222222222"),
                    title="RAG paper",
                    authors=["Author"],
                    publication_year=2025,
                    page_start=2,
                    page_end=2,
                )
            ],
        )

@pytest.fixture
async def literature_client(runtime_harness):
    processor = FakeProcessor()
    retriever = FakeRetriever()
    literature = LiteratureApplication(processor=processor, retriever=retriever, answer_service=FakeAnswerService())
    app = create_app(
        runtime_harness.runtime,
        literature_application=literature,
        settings=Settings(rag_max_upload_bytes=100),
        cors_origins=["https://allowed.example"],
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client, processor, retriever


@pytest.mark.asyncio
async def test_upload_indexes_document(literature_client) -> None:
    client, processor, _ = literature_client

    response = await client.post(
        "/api/v1/literature/documents",
        files={"file": ("paper.pdf", b"%PDF", "application/pdf")},
        data={
            "metadata_json": (
                '{"title":"RAG paper","authors":["Author"],"tags":["RAG"]}'
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["units_indexed"] == 2
    assert processor.ingest_calls[0][2].title == "RAG paper"


@pytest.mark.asyncio
async def test_search_returns_flattened_units(literature_client) -> None:
    client, _, retriever = literature_client

    response = await client.post(
        "/api/v1/literature/search",
        json={"query": "hybrid retrieval", "limit": 5, "tags": ["RAG"]},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["text"] == "Hybrid retrieval evidence."
    assert response.json()["items"][0]["rerank_score"] == 0.9
    assert retriever.requests[0].filters.tags == ["RAG"]


@pytest.mark.asyncio
async def test_delete_document(literature_client) -> None:
    client, processor, _ = literature_client
    document_id = "22222222-2222-4222-8222-222222222222"

    response = await client.delete(f"/api/v1/literature/documents/{document_id}")

    assert response.status_code == 204
    assert processor.deleted == [UUID(document_id)]


@pytest.mark.asyncio
async def test_oversized_upload_stops_before_parsing(literature_client) -> None:
    client, processor, _ = literature_client

    response = await client.post(
        "/api/v1/literature/documents",
        files={"file": ("large.pdf", b"x" * 101, "application/pdf")},
    )

    assert response.status_code == 413
    assert processor.ingest_calls == []


@pytest.mark.asyncio
async def test_disabled_literature_returns_503(async_client) -> None:
    response = await async_client.post(
        "/api/v1/literature/search",
        json={"query": "RAG"},
    )

    assert response.status_code == 503

@pytest.mark.asyncio
async def test_answer_returns_grounded_citations(literature_client) -> None:
    client, _, _ = literature_client

    response = await client.post(
        "/api/v1/literature/answer",
        json={"query": "What does the paper support?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Grounded answer."
    assert response.json()["citations"][0]["page_start"] == 2
