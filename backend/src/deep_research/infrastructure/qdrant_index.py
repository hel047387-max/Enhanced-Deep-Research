from __future__ import annotations

from typing import Any
from uuid import UUID

from deep_research.domain.literature import (
    LiteratureFilter,
    RetrievedUnit,
    SearchableUnit,
)


class QdrantLiteratureIndex:
    def __init__(
        self,
        client: Any,
        collection_name: str,
        *,
        models_module: Any | None = None,
    ) -> None:
        if models_module is None:
            try:
                from qdrant_client import models as models_module
            except ImportError:
                raise RuntimeError(
                    "Qdrant indexing requires the optional 'rag' dependencies."
                ) from None
        self._client = client
        self._collection_name = collection_name
        self._models = models_module

    async def ensure_collection(self, vector_size: int) -> None:
        if await self._client.collection_exists(self._collection_name):
            return
        await self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=self._models.VectorParams(
                size=vector_size,
                distance=self._models.Distance.COSINE,
            ),
        )

    async def upsert(
        self,
        units: list[SearchableUnit],
        vectors: list[list[float]],
    ) -> None:
        if len(units) != len(vectors):
            raise ValueError("unit and vector counts must match")
        points = [
            self._models.PointStruct(
                id=str(unit.unit_id),
                vector=vector,
                payload=unit.to_payload(),
            )
            for unit, vector in zip(units, vectors, strict=True)
        ]
        await self._client.upsert(
            collection_name=self._collection_name,
            points=points,
            wait=True,
        )

    async def search(
        self,
        vector: list[float],
        *,
        limit: int,
        filters: LiteratureFilter,
    ) -> list[RetrievedUnit]:
        response = await self._client.query_points(
            collection_name=self._collection_name,
            query=vector,
            query_filter=self._build_filter(filters),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [
            RetrievedUnit(
                unit=SearchableUnit.model_validate(point.payload),
                similarity_score=float(point.score),
            )
            for point in response.points
        ]

    async def retrieve(self, unit_ids: list[UUID]) -> list[SearchableUnit]:
        if not unit_ids:
            return []
        points = await self._client.retrieve(
            collection_name=self._collection_name,
            ids=[str(unit_id) for unit_id in unit_ids],
            with_payload=True,
            with_vectors=False,
        )
        return [
            SearchableUnit.model_validate(point.payload)
            for point in points
        ]

    async def delete_document(self, document_id: UUID) -> None:
        selector = self._models.FilterSelector(
            filter=self._models.Filter(
                must=[
                    self._models.FieldCondition(
                        key="document_id",
                        match=self._models.MatchValue(value=str(document_id)),
                    )
                ]
            )
        )
        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=selector,
            wait=True,
        )

    def _build_filter(self, filters: LiteratureFilter) -> Any | None:
        conditions: list[Any] = []
        if filters.document_ids:
            conditions.append(
                self._models.FieldCondition(
                    key="document_id",
                    match=self._models.MatchAny(
                        any=[str(document_id) for document_id in filters.document_ids]
                    ),
                )
            )
        if filters.tags:
            conditions.append(
                self._models.FieldCondition(
                    key="tags",
                    match=self._models.MatchAny(any=filters.tags),
                )
            )
        if filters.language:
            conditions.append(
                self._models.FieldCondition(
                    key="language",
                    match=self._models.MatchValue(value=filters.language),
                )
            )
        if filters.year_from is not None:
            conditions.append(
                self._models.FieldCondition(
                    key="publication_year",
                    range=self._models.Range(gte=filters.year_from),
                )
            )
        if filters.year_to is not None:
            conditions.append(
                self._models.FieldCondition(
                    key="publication_year",
                    range=self._models.Range(lte=filters.year_to),
                )
            )
        return self._models.Filter(must=conditions) if conditions else None
