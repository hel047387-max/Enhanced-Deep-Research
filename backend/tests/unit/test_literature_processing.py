import os
from types import SimpleNamespace

import pytest

from deep_research.domain.literature import LiteratureMetadata
from deep_research.infrastructure.docling_parser import DoclingParser, EmptyDocument
from deep_research.infrastructure.embedding_provider import (
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


@pytest.mark.asyncio
async def test_docling_parser_preserves_structure_and_neighbors() -> None:
    converter = FakeConverter()
    chunks = [
        FakeChunk(
            "First paragraph",
            {
                "headings": ["Methods", "Retrieval"],
                "doc_items": [
                    {"label": "text", "prov": [{"page_no": 2}]},
                ],
            },
        ),
        FakeChunk(
            "| method | score |\n| RAG | 0.9 |",
            {
                "headings": ["Methods", "Results"],
                "doc_items": [
                    {"label": "table", "prov": [{"page_no": 3}]},
                ],
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
