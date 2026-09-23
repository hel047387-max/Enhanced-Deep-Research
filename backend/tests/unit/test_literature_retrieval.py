from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from deep_research.domain.literature import (
    LiteratureFilter,
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

    async def collection_exists(self, collection_name: str) -> bool:
        assert collection_name == "literature_units"
        return False

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
