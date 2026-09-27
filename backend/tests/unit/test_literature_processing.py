import os
from types import SimpleNamespace
from uuid import UUID

import pytest

from deep_research.application.document_processor import (
    DocumentProcessor,
    EmbeddingCountMismatch,
)
from deep_research.domain.literature import (
    LiteratureFilter,
    LiteratureMetadata,
    SearchableUnit,
)
from deep_research.infrastructure.docling_parser import DoclingParser, EmptyDocument
from deep_research.infrastructure.embedding_provider import (
    DashScopeEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)


class FakeMeta:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def export_json_dict(self) -> dict[str, object]:
        return self._payload


class FakeChunk:
    def __init__(self, text: str, payload: dict[str, object]) -> None:
        self.text = text
        self.meta = FakeMeta(payload)


class FakeConverter:
    def __init__(self) -> None:
        self.source: str | None = None

    def convert(self, source: str):
        self.source = source
        assert os.path.exists(source)
        return SimpleNamespace(document=object())


class FakeChunker:
    def __init__(self, chunks: list[FakeChunk]) -> None:
        self.chunks = chunks

    def chunk(self, *, dl_doc: object):
        assert dl_doc is not None
        return iter(self.chunks)


class FakeEmbeddingModel:
    def __init__(self) -> None:
        self.document_inputs: list[str] = []
        self.query_inputs: list[str] = []

    def get_sentence_embedding_dimension(self) -> int:
        return 3

    def encode_document(self, texts: list[str], *, normalize_embeddings: bool):
        assert normalize_embeddings is True
        self.document_inputs = texts
        return SimpleNamespace(tolist=lambda: [[1.0, 0.0, 0.0] for _ in texts])

    def encode_query(self, text: str, *, normalize_embeddings: bool):
        assert normalize_embeddings is True
        self.query_inputs.append(text)
        return SimpleNamespace(tolist=lambda: [0.0, 1.0, 0.0])


def test_docling_parser_factory_uses_unicode_safe_pdf_backend() -> None:
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat

    parser = DoclingParser.from_model_name(
        "sentence-transformers/all-MiniLM-L6-v2",
        max_tokens=256,
    )

    pdf_options = parser._converter.format_to_options[InputFormat.PDF]
    assert pdf_options.backend is PyPdfiumDocumentBackend


@pytest.mark.asyncio
async def test_docling_parser_preserves_structure_and_neighbors() -> None:
    converter = FakeConverter()
    chunks = [
        FakeChunk(
            "First paragraph",
            {
                "headings": ["Methods", "Retrieval"],
                "doc_items": [{"label": "text", "prov": [{"page_no": 2}]}],
            },
        ),
        FakeChunk(
            "| method | score |\n| RAG | 0.9 |",
            {
                "headings": ["Methods", "Results"],
                "doc_items": [{"label": "table", "prov": [{"page_no": 3}]}],
            },
        ),
    ]
    parser = DoclingParser(converter=converter, chunker=FakeChunker(chunks))

    units = await parser.parse(
        filename="paper.pdf",
        content=b"%PDF test",
        metadata=LiteratureMetadata(
            title="RAG paper",
            authors=["Author"],
            publication_year=2025,
            language="en",
            tags=["RAG"],
        ),
    )

    assert [unit.text for unit in units] == [
        "First paragraph",
        "| method | score |\n| RAG | 0.9 |",
    ]
    assert units[0].heading_path == ["Methods", "Retrieval"]
    assert units[0].page_start == 2
    assert units[1].content_type == "table"
    assert units[0].next_unit_id == units[1].unit_id
    assert units[1].previous_unit_id == units[0].unit_id
    assert converter.source is not None
    assert not os.path.exists(converter.source)


@pytest.mark.asyncio
async def test_docling_parser_rejects_empty_document() -> None:
    parser = DoclingParser(
        converter=FakeConverter(),
        chunker=FakeChunker([FakeChunk("  ", {"headings": [], "doc_items": []})]),
    )

    with pytest.raises(EmptyDocument):
        await parser.parse(
            filename="empty.pdf",
            content=b"%PDF",
            metadata=LiteratureMetadata(title="Empty"),
        )


@pytest.mark.asyncio
async def test_same_embedding_provider_encodes_documents_and_queries() -> None:
    model = FakeEmbeddingModel()
    provider = SentenceTransformerEmbeddingProvider(model)

    documents = await provider.embed_documents(["document"])
    query = await provider.embed_query("query")

    assert provider.dimension == 3
    assert documents == [[1.0, 0.0, 0.0]]
    assert query == [0.0, 1.0, 0.0]
    assert model.document_inputs == ["document"]
    assert model.query_inputs == ["query"]


class FakeDashScopeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def call(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return {
            "status_code": 200,
            "output": {"embeddings": [{"embedding": [0.6, 0.8]}]},
        }


@pytest.mark.asyncio
async def test_dashscope_provider_uses_the_configured_model_for_documents_and_queries() -> None:
    client = FakeDashScopeClient()
    provider = DashScopeEmbeddingProvider(
        client=client,
        model_name="text-embedding-v3",
        api_key="secret",
        expected_dimension=2,
    )

    documents = await provider.embed_documents(["document"])
    query = await provider.embed_query("query")

    assert documents == [[0.6, 0.8]]
    assert query == [0.6, 0.8]
    assert provider.dimension == 2
    assert [call["model"] for call in client.calls] == [
        "text-embedding-v3",
        "text-embedding-v3",
    ]
    assert all(call["api_key"] == "secret" for call in client.calls)


class InvalidDashScopeClient:
    def call(self, **kwargs: object) -> object:
        return {"status_code": 200, "output": {"embeddings": [{"embedding": "bad"}]}}


@pytest.mark.asyncio
async def test_dashscope_provider_rejects_a_non_list_embedding_vector() -> None:
    provider = DashScopeEmbeddingProvider(
        client=InvalidDashScopeClient(),
        model_name="text-embedding-v3",
        api_key="secret",
    )

    with pytest.raises(TypeError, match="without vector values"):
        await provider.embed_query("query")


class StubParser:
    def __init__(self, units: list[SearchableUnit]) -> None:
        self.units = units

    async def parse(
        self,
        *,
        filename: str,
        content: bytes,
        metadata: LiteratureMetadata,
    ) -> list[SearchableUnit]:
        return self.units


class StubEmbedder:
    dimension = 3

    def __init__(self) -> None:
        self.document_texts: list[str] = []
        self.vectors: list[list[float]] | None = None

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_texts = texts
        if self.vectors is not None:
            return self.vectors
        return [[1.0, 0.0, 0.0] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        raise AssertionError("query embedding is not used during ingestion")


class StubIndex:
    def __init__(self) -> None:
        self.ensured_dimension: int | None = None
        self.upserted_units: list[SearchableUnit] = []
        self.upsert_calls = 0
        self.upsert_error: Exception | None = None
        self.deleted_document: UUID | None = None

    async def ensure_collection(self, vector_size: int) -> None:
        self.ensured_dimension = vector_size

    async def upsert(
        self,
        units: list[SearchableUnit],
        vectors: list[list[float]],
    ) -> None:
        self.upsert_calls += 1
        if self.upsert_error is not None:
            raise self.upsert_error
        self.upserted_units = units

    async def search(
        self,
        vector: list[float],
        *,
        limit: int,
        filters: LiteratureFilter,
    ):
        raise AssertionError("search is not used during ingestion")

    async def retrieve(self, unit_ids: list[UUID]):
        raise AssertionError("retrieve is not used during ingestion")

    async def delete_document(self, document_id: UUID) -> None:
        self.deleted_document = document_id


def ingestion_unit(unit_id: str, text: str) -> SearchableUnit:
    return SearchableUnit(
        unit_id=unit_id,
        document_id="22222222-2222-4222-8222-222222222222",
        title="RAG paper",
        content_type="paragraph",
        text=text,
    )


@pytest.mark.asyncio
async def test_ingest_embeds_and_upserts_units() -> None:
    units = [
        ingestion_unit("11111111-1111-4111-8111-111111111111", "one"),
        ingestion_unit("33333333-3333-4333-8333-333333333333", "two"),
    ]
    parser = StubParser(units)
    embedder = StubEmbedder()
    index = StubIndex()
    processor = DocumentProcessor(parser, embedder, index)
    metadata = LiteratureMetadata(title="RAG paper")

    result = await processor.ingest("paper.pdf", b"%PDF", metadata)

    assert result.units_indexed == 2
    assert embedder.document_texts == [unit.embedding_text() for unit in units]
    assert index.ensured_dimension == 3
    assert index.upserted_units == units


@pytest.mark.asyncio
async def test_empty_document_never_writes_qdrant() -> None:
    index = StubIndex()
    processor = DocumentProcessor(StubParser([]), StubEmbedder(), index)

    with pytest.raises(EmptyDocument):
        await processor.ingest(
            "empty.pdf",
            b"%PDF",
            LiteratureMetadata(title="Empty"),
        )

    assert index.upsert_calls == 0


@pytest.mark.asyncio
async def test_embedding_count_must_match_unit_count() -> None:
    unit = ingestion_unit("11111111-1111-4111-8111-111111111111", "one")
    embedder = StubEmbedder()
    embedder.vectors = []
    index = StubIndex()
    processor = DocumentProcessor(StubParser([unit]), embedder, index)

    with pytest.raises(EmbeddingCountMismatch):
        await processor.ingest(
            "paper.pdf",
            b"%PDF",
            LiteratureMetadata(title="RAG paper"),
        )

    assert index.upsert_calls == 0


@pytest.mark.asyncio
async def test_qdrant_failure_remains_an_error() -> None:
    unit = ingestion_unit("11111111-1111-4111-8111-111111111111", "one")
    index = StubIndex()
    index.upsert_error = RuntimeError("qdrant unavailable")
    processor = DocumentProcessor(StubParser([unit]), StubEmbedder(), index)

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        await processor.ingest(
            "paper.pdf",
            b"%PDF",
            LiteratureMetadata(title="RAG paper"),
        )


@pytest.mark.asyncio
async def test_delete_delegates_to_vector_index() -> None:
    index = StubIndex()
    processor = DocumentProcessor(StubParser([]), StubEmbedder(), index)
    document_id = UUID("22222222-2222-4222-8222-222222222222")

    await processor.delete(document_id)

    assert index.deleted_document == document_id
