from __future__ import annotations

from uuid import UUID

from deep_research.domain.literature import (
    DocumentParser,
    EmbeddingProvider,
    IngestedDocument,
    LiteratureDocument,
    LiteratureIndex,
    LiteratureMetadata,
)
from deep_research.infrastructure.docling_parser import EmptyDocument


class EmbeddingCountMismatch(ValueError):
    def __init__(self, unit_count: int, vector_count: int) -> None:
        super().__init__(
            f"embedding provider returned {vector_count} vectors for "
            f"{unit_count} searchable units"
        )


class DocumentProcessor:
    def __init__(
        self,
        parser: DocumentParser,
        embedder: EmbeddingProvider,
        index: LiteratureIndex,
    ) -> None:
        self._parser = parser
        self._embedder = embedder
        self._index = index

    async def ingest(
        self,
        filename: str,
        content: bytes,
        metadata: LiteratureMetadata,
    ) -> IngestedDocument:
        units = await self._parser.parse(
            filename=filename,
            content=content,
            metadata=metadata,
        )
        if not units:
            raise EmptyDocument(filename)

        vectors = await self._embedder.embed_documents(
            [unit.embedding_text() for unit in units]
        )
        if len(vectors) != len(units):
            raise EmbeddingCountMismatch(len(units), len(vectors))

        await self._index.ensure_collection(self._embedder.dimension)
        await self._index.upsert(units, vectors)
        return IngestedDocument(
            document_id=units[0].document_id,
            units_indexed=len(units),
            metadata=metadata,
        )

    async def list_documents(self) -> list[LiteratureDocument]:
        return await self._index.list_documents()

    async def delete(self, document_id: UUID) -> None:
        await self._index.delete_document(document_id)
