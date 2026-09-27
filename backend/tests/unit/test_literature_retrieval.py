from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from deep_research.application.context_builder import ContextBuilder
from deep_research.application.retriever import LiteratureRetriever
from deep_research.domain.literature import (
    LiteratureFilter,
    LiteratureSearchRequest,
    QueryDecision,
    RetrievedUnit,
    SearchableUnit,
)
from deep_research.infrastructure.cross_encoder_reranker import (
    SentenceTransformerReranker,
)
from deep_research.infrastructure.qdrant_index import QdrantLiteratureIndex


class ModelValue:
    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)


class FakeDistance:
    COSINE = "cosine"
    DOT = "dot"
    EUCLID = "euclid"


class FakeModels:
    Distance = FakeDistance
    VectorParams = ModelValue
    PointStruct = ModelValue
    Filter = ModelValue
    FieldCondition = ModelValue
    MatchValue = ModelValue
    MatchAny = ModelValue
    Range = ModelValue
    FilterSelector = ModelValue


class FakeQdrantClient:
    def __init__(self) -> None:
        self.created: ModelValue | None = None
        self.upserted: list[ModelValue] = []
        self.query_filter: ModelValue | None = None
        self.deleted: ModelValue | None = None
        self.search_points: list[object] = []
        self.retrieved_points: list[object] = []
        self.collection_present = False
        self.scroll_pages: list[tuple[list[object], object | None]] = []
        self.scroll_calls: list[dict[str, object]] = []

    async def collection_exists(self, collection_name: str) -> bool:
        assert collection_name == "literature_units"
        return self.collection_present

    async def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: ModelValue,
    ) -> None:
        self.created = vectors_config

    async def upsert(
        self,
        *,
        collection_name: str,
        points: list[ModelValue],
        wait: bool,
    ) -> None:
        assert collection_name == "literature_units"
        assert wait is True
        self.upserted = points

    async def query_points(self, **kwargs: object):
        self.query_filter = kwargs["query_filter"]
        return SimpleNamespace(points=self.search_points)

    async def retrieve(self, **kwargs: object):
        return self.retrieved_points

    async def delete(self, **kwargs: object) -> None:
        self.deleted = kwargs["points_selector"]

    async def scroll(self, **kwargs: object):
        self.scroll_calls.append(kwargs)
        return self.scroll_pages.pop(0)


class FakeRerankerModel:
    def predict(self, pairs: list[tuple[str, str]]):
        assert len(pairs) == 2
        return [0.1, 0.9]


def make_unit(
    unit_id: str = "11111111-1111-4111-8111-111111111111",
    *,
    text: str = "First unit",
) -> SearchableUnit:
    return SearchableUnit(
        unit_id=unit_id,
        document_id="22222222-2222-4222-8222-222222222222",
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
        text=text,
    )


@pytest.mark.asyncio
async def test_index_upserts_one_vector_and_complete_payload() -> None:
    client = FakeQdrantClient()
    index = QdrantLiteratureIndex(
        client,
        "literature_units",
        models_module=FakeModels,
    )
    unit = make_unit()

    await index.ensure_collection(3)
    await index.upsert([unit], [[0.1, 0.2, 0.3]])

    assert client.created is not None
    assert client.created.size == 3
    assert client.created.distance == "cosine"
    assert client.upserted[0].vector == [0.1, 0.2, 0.3]
    assert client.upserted[0].payload == unit.model_dump(mode="json")


@pytest.mark.asyncio
async def test_index_uses_the_configured_vector_distance() -> None:
    client = FakeQdrantClient()
    index = QdrantLiteratureIndex(
        client,
        "literature_units",
        distance="dot",
        models_module=FakeModels,
    )

    await index.ensure_collection(3)

    assert client.created is not None
    assert client.created.distance == "dot"


@pytest.mark.asyncio
async def test_search_validates_complete_payload_and_applies_filters() -> None:
    client = FakeQdrantClient()
    unit = make_unit()
    client.search_points = [
        SimpleNamespace(payload=unit.to_payload(), score=0.82),
    ]
    index = QdrantLiteratureIndex(
        client,
        "literature_units",
        models_module=FakeModels,
    )

    results = await index.search(
        [0.1, 0.2, 0.3],
        limit=5,
        filters=LiteratureFilter(
            document_ids=[unit.document_id],
            tags=["RAG"],
            language="en",
            year_from=2024,
            year_to=2025,
        ),
    )

    assert results == [RetrievedUnit(unit=unit, similarity_score=0.82)]
    assert client.query_filter is not None
    assert len(client.query_filter.must) == 5


@pytest.mark.asyncio
async def test_missing_payload_text_is_rejected() -> None:
    client = FakeQdrantClient()
    payload = make_unit().to_payload()
    del payload["text"]
    client.search_points = [SimpleNamespace(payload=payload, score=0.5)]
    index = QdrantLiteratureIndex(
        client,
        "literature_units",
        models_module=FakeModels,
    )

    with pytest.raises(ValidationError):
        await index.search(
            [0.1, 0.2, 0.3],
            limit=5,
            filters=LiteratureFilter(),
        )


@pytest.mark.asyncio
async def test_retrieve_and_delete_use_unit_and_document_ids() -> None:
    client = FakeQdrantClient()
    unit = make_unit()
    client.retrieved_points = [SimpleNamespace(payload=unit.to_payload())]
    index = QdrantLiteratureIndex(
        client,
        "literature_units",
        models_module=FakeModels,
    )

    retrieved = await index.retrieve([unit.unit_id])
    await index.delete_document(unit.document_id)

    assert retrieved == [unit]
    assert client.deleted is not None
    assert client.deleted.filter.must[0].key == "document_id"


@pytest.mark.asyncio
async def test_list_documents_groups_units_from_all_scroll_pages() -> None:
    client = FakeQdrantClient()
    client.collection_present = True
    first = make_unit()
    second = make_unit(
        "33333333-3333-4333-8333-333333333333",
        text="Second unit",
    )
    other = make_unit(
        "44444444-4444-4444-8444-444444444444",
        text="Other document",
    ).model_copy(
        update={
            "document_id": UUID("55555555-5555-4555-8555-555555555555"),
            "title": "Another paper",
        }
    )
    client.scroll_pages = [
        ([SimpleNamespace(payload=first.to_payload())], "next"),
        (
            [
                SimpleNamespace(payload=second.to_payload()),
                SimpleNamespace(payload=other.to_payload()),
            ],
            None,
        ),
    ]
    index = QdrantLiteratureIndex(
        client,
        "literature_units",
        models_module=FakeModels,
    )

    documents = await index.list_documents()

    assert [(item.title, item.units_indexed) for item in documents] == [
        ("Another paper", 1),
        ("RAG paper", 2),
    ]
    assert client.scroll_calls[0]["offset"] is None
    assert client.scroll_calls[1]["offset"] == "next"
    assert all(call["with_vectors"] is False for call in client.scroll_calls)


@pytest.mark.asyncio
async def test_list_documents_returns_empty_when_collection_does_not_exist() -> None:
    client = FakeQdrantClient()
    index = QdrantLiteratureIndex(
        client,
        "literature_units",
        models_module=FakeModels,
    )

    assert await index.list_documents() == []
    assert client.scroll_calls == []


@pytest.mark.asyncio
async def test_cross_encoder_reranks_candidates() -> None:
    first = RetrievedUnit(unit=make_unit(), similarity_score=0.9)
    second = RetrievedUnit(
        unit=make_unit(
            "33333333-3333-4333-8333-333333333333",
            text="Second unit",
        ),
        similarity_score=0.7,
    )
    reranker = SentenceTransformerReranker(FakeRerankerModel())

    ranked = await reranker.rerank("query", [first, second], limit=2)

    assert [item.unit.unit_id for item in ranked] == [
        UUID("33333333-3333-4333-8333-333333333333"),
        UUID("11111111-1111-4111-8111-111111111111"),
    ]
    assert ranked[0].rerank_score == 0.9


class StaticRouter:
    def __init__(self, strategy: str) -> None:
        self.strategy = strategy

    async def route(self, query: str) -> QueryDecision:
        return QueryDecision(mode=self.strategy, reason="test")


class StaticEnhancer:
    def __init__(self, queries: list[str]) -> None:
        self.queries = queries

    async def expand(self, query: str, strategy: str) -> list[str]:
        return self.queries


class RecordingQueryEmbedder:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [float(len(self.queries))]


class SearchIndex:
    def __init__(
        self,
        results: list[list[RetrievedUnit]],
        neighbors: list[SearchableUnit] | None = None,
    ) -> None:
        self.results = iter(results)
        self.neighbors = neighbors or []
        self.retrieve_calls: list[list[UUID]] = []

    async def search(
        self,
        vector: list[float],
        *,
        limit: int,
        filters: LiteratureFilter,
    ) -> list[RetrievedUnit]:
        return next(self.results)

    async def retrieve(self, unit_ids: list[UUID]) -> list[SearchableUnit]:
        self.retrieve_calls.append(unit_ids)
        return self.neighbors


class RecordingReranker:
    def __init__(self) -> None:
        self.candidates: list[RetrievedUnit] = []

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedUnit],
        *,
        limit: int,
    ) -> list[RetrievedUnit]:
        self.candidates = candidates
        return candidates[:limit]


@pytest.mark.asyncio
async def test_direct_route_embeds_original_query_once() -> None:
    unit = RetrievedUnit(unit=make_unit(), similarity_score=0.8)
    embedder = RecordingQueryEmbedder()
    retriever = LiteratureRetriever(
        StaticRouter("direct"),
        StaticEnhancer(["ignored"]),
        embedder,
        SearchIndex([[unit]]),
        RecordingReranker(),
        candidate_limit=10,
        top_k=5,
    )

    result = await retriever.search(LiteratureSearchRequest(query="original"))

    assert embedder.queries == ["original"]
    assert result == [unit]


@pytest.mark.asyncio
async def test_mqe_uses_three_queries_and_deduplicates_units() -> None:
    first = make_unit()
    second = make_unit(
        "33333333-3333-4333-8333-333333333333",
        text="Second unit",
    )
    embedder = RecordingQueryEmbedder()
    reranker = RecordingReranker()
    retriever = LiteratureRetriever(
        StaticRouter("mqe"),
        StaticEnhancer(["q1", "q2", "q3", "q4"]),
        embedder,
        SearchIndex(
            [
                [RetrievedUnit(unit=first, similarity_score=0.5)],
                [
                    RetrievedUnit(unit=first, similarity_score=0.9),
                    RetrievedUnit(unit=second, similarity_score=0.7),
                ],
                [RetrievedUnit(unit=second, similarity_score=0.6)],
            ]
        ),
        reranker,
        candidate_limit=10,
        top_k=5,
    )

    await retriever.search(LiteratureSearchRequest(query="original"))

    assert embedder.queries == ["q1", "q2", "q3"]
    assert [item.unit.unit_id for item in reranker.candidates] == [
        first.unit_id,
        second.unit_id,
    ]
    assert reranker.candidates[0].similarity_score == 0.9


@pytest.mark.asyncio
async def test_context_adds_existing_neighbors_once() -> None:
    previous = make_unit(
        "44444444-4444-4444-8444-444444444444",
        text="Previous",
    )
    primary = make_unit(text="Primary").model_copy(
        update={"previous_unit_id": previous.unit_id, "next_unit_id": previous.unit_id}
    )
    index = SearchIndex([], neighbors=[previous])
    builder = ContextBuilder(index, max_chars=10_000)

    context = await builder.build(
        [RetrievedUnit(unit=primary, similarity_score=0.9)]
    )

    assert index.retrieve_calls == [[previous.unit_id]]
    assert [unit.unit_id for unit in context.units] == [
        primary.unit_id,
        previous.unit_id,
    ]
    assert "Primary" in context.text
    assert "Previous" in context.text


@pytest.mark.asyncio
async def test_context_respects_character_budget() -> None:
    unit = make_unit(text="x" * 500)
    builder = ContextBuilder(SearchIndex([]), max_chars=120)

    context = await builder.build(
        [RetrievedUnit(unit=unit, similarity_score=0.9)]
    )

    assert len(context.text) <= 120
    assert context.units == [unit]