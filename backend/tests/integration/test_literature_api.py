from __future__ import annotations

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from deep_research.api.literature_routes import LiteratureApplication
from deep_research.api.main import create_app
from deep_research.auth.passwords import Argon2PasswordHasher
from deep_research.auth.rate_limit import LoginRateLimiter
from deep_research.auth.service import AuthService
from deep_research.config import Settings
from deep_research.domain.literature import (
    IngestedDocument,
    LiteratureAnswer,
    LiteratureCitation,
    LiteratureDocument,
    LiteratureMetadata,
    RetrievedUnit,
    SearchableUnit,
)
from deep_research.persistence.auth_store import AuthStore


class FakeProcessor:
    def __init__(self) -> None:
        self.ingest_calls: list[tuple[str, bytes, LiteratureMetadata]] = []
        self.deleted: list[UUID] = []
        self.ingest_error: Exception | None = None
        self.documents = [
            LiteratureDocument(
                document_id=UUID("22222222-2222-4222-8222-222222222222"),
                title="RAG paper",
                authors=["Author"],
                publication_year=2025,
                doi="10.1/example",
                language="en",
                tags=["RAG"],
                units_indexed=2,
            )
        ]

    async def ingest(
        self,
        filename: str,
        content: bytes,
        metadata: LiteratureMetadata,
    ) -> IngestedDocument:
        if self.ingest_error is not None:
            raise self.ingest_error
        self.ingest_calls.append((filename, content, metadata))
        return IngestedDocument(
            document_id=UUID("22222222-2222-4222-8222-222222222222"),
            units_indexed=2,
            metadata=metadata,
        )

    async def delete(self, document_id: UUID) -> None:
        self.deleted.append(document_id)

    async def list_documents(self) -> list[LiteratureDocument]:
        return self.documents


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
async def literature_client(runtime_harness, tmp_path):
    processor = FakeProcessor()
    retriever = FakeRetriever()
    literature = LiteratureApplication(
        processor=processor,
        retriever=retriever,
        answer_service=FakeAnswerService(),
    )
    auth_store = AuthStore(tmp_path / "literature-auth.sqlite")
    await auth_store.initialize()
    auth_service = AuthService(
        auth_store,
        Argon2PasswordHasher(),
        LoginRateLimiter(max_attempts=5, window_seconds=900),
    )
    app = create_app(
        runtime_harness.runtime,
        literature_application=literature,
        settings=Settings(rag_max_upload_bytes=100),
        cors_origins=["https://allowed.example"],
        auth_service=auth_service,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        registration = await client.post(
            "/api/v1/auth/register",
            json={"username": "owner", "password": "correct password"},
        )
        assert registration.status_code == 201
        client.headers["X-CSRF-Token"] = registration.json()["csrf_token"]
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
async def test_list_documents_returns_qdrant_catalog(literature_client) -> None:
    client, _, _ = literature_client

    response = await client.get("/api/v1/literature/documents")

    assert response.status_code == 200
    assert response.json() == [
        {
            "document_id": "22222222-2222-4222-8222-222222222222",
            "title": "RAG paper",
            "authors": ["Author"],
            "publication_year": 2025,
            "doi": "10.1/example",
            "language": "en",
            "tags": ["RAG"],
            "units_indexed": 2,
        }
    ]


@pytest.mark.asyncio
async def test_upload_logs_indexing_exception(literature_client, caplog) -> None:
    client, processor, _ = literature_client
    processor.ingest_error = RuntimeError("parser exploded")

    with caplog.at_level("ERROR", logger="deep_research.api.literature_routes"):
        response = await client.post(
            "/api/v1/literature/documents",
            files={"file": ("paper.pdf", b"%PDF", "application/pdf")},
        )

    assert response.status_code == 502
    assert "Document indexing failed for paper.pdf" in caplog.text
    assert "parser exploded" in caplog.text


@pytest.mark.asyncio
async def test_search_returns_flattened_units(literature_client) -> None:
    client, _, retriever = literature_client

    response = await client.post(
        "/api/v1/literature/search",
        json={
            "query": "hybrid retrieval",
            "limit": 2,
            "document_ids": ["22222222-2222-4222-8222-222222222222"],
            "tags": ["RAG"],
        },
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["text"] == "Hybrid retrieval evidence."
    assert response.json()["items"][0]["rerank_score"] == 0.9
    assert retriever.requests[0].filters.tags == ["RAG"]
    assert retriever.requests[0].filters.document_ids == [
        UUID("22222222-2222-4222-8222-222222222222")
    ]
    assert retriever.requests[0].limit == 2


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


@pytest.mark.asyncio
async def test_research_request_reports_unavailable_literature(async_client) -> None:
    async with async_client.stream(
        "POST",
        "/api/v1/research/stream",
        json={"query": "A complete scoped question", "use_literature": True},
    ) as response:
        events = [
            line async for line in response.aiter_lines() if line.startswith("data: ")
        ]

    assert response.status_code == 200
    assert any("literature_unavailable" in event for event in events)


@pytest.mark.asyncio
async def test_search_rejects_reversed_year_range(literature_client) -> None:
    client, _, _ = literature_client

    response = await client.post(
        "/api/v1/literature/search",
        json={"query": "RAG", "year_from": 2025, "year_to": 2020},
    )

    assert response.status_code == 422
