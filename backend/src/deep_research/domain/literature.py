from __future__ import annotations

from typing import Annotated, Literal, Protocol, TypeAlias
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    model_validator,
)

CleanText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
QueryMode: TypeAlias = Literal["direct", "mqe", "hyde"]
ContentType: TypeAlias = Literal["paragraph", "table", "list", "other"]


class LiteratureMetadata(BaseModel, frozen=True):
    title: CleanText
    authors: list[CleanText] = Field(default_factory=list)
    publication_year: int | None = Field(default=None, ge=1000, le=9999)
    doi: CleanText | None = None
    language: CleanText | None = None
    tags: list[CleanText] = Field(default_factory=list)


class SearchableUnit(BaseModel, frozen=True):
    unit_id: UUID
    document_id: UUID
    title: CleanText
    authors: list[CleanText] = Field(default_factory=list)
    publication_year: int | None = Field(default=None, ge=1000, le=9999)
    doi: CleanText | None = None
    language: CleanText | None = None
    tags: list[CleanText] = Field(default_factory=list)
    heading_path: list[CleanText] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    content_type: ContentType
    previous_unit_id: UUID | None = None
    next_unit_id: UUID | None = None
    text: CleanText

    @model_validator(mode="after")
    def validate_page_range(self) -> SearchableUnit:
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")
        return self

    def embedding_text(self) -> str:
        fields = [
            f"\u6807\u9898\uff1a{self.title}",
            (
                "\u4f5c\u8005\uff1a" + "\u3001".join(self.authors)
                if self.authors
                else ""
            ),
            (
                f"\u5e74\u4efd\uff1a{self.publication_year}"
                if self.publication_year
                else ""
            ),
            (
                "\u6807\u7b7e\uff1a" + "\u3001".join(self.tags)
                if self.tags
                else ""
            ),
            (
                f"\u7ae0\u8282\uff1a{' > '.join(self.heading_path)}"
                if self.heading_path
                else ""
            ),
            f"\u6b63\u6587\uff1a{self.text}",
        ]
        return "\n".join(field for field in fields if field)

    def to_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class LiteratureFilter(BaseModel, frozen=True):
    document_ids: list[UUID] = Field(default_factory=list)
    tags: list[CleanText] = Field(default_factory=list)
    language: CleanText | None = None
    year_from: int | None = Field(default=None, ge=1000, le=9999)
    year_to: int | None = Field(default=None, ge=1000, le=9999)

    @model_validator(mode="after")
    def validate_year_range(self) -> LiteratureFilter:
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_to < self.year_from
        ):
            raise ValueError("year_to must be greater than or equal to year_from")
        return self


class LiteratureSearchRequest(BaseModel, frozen=True):
    query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
    ]
    limit: int = Field(default=3, ge=1, le=50)
    filters: LiteratureFilter = Field(default_factory=LiteratureFilter)


class RetrievedUnit(BaseModel, frozen=True):
    unit: SearchableUnit
    similarity_score: float
    rerank_score: float | None = None


class IngestedDocument(BaseModel, frozen=True):
    document_id: UUID
    units_indexed: int = Field(ge=1)
    metadata: LiteratureMetadata


class LiteratureDocument(LiteratureMetadata, frozen=True):
    document_id: UUID
    units_indexed: int = Field(ge=1)


class LiteratureCitation(BaseModel, frozen=True):
    unit_id: UUID
    document_id: UUID
    title: str
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    doi: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None


class LiteratureAnswer(BaseModel, frozen=True):
    answer: CleanText
    citations: list[LiteratureCitation] = Field(default_factory=list)


class QueryDecision(BaseModel, frozen=True):
    mode: QueryMode
    reason: CleanText


class DocumentParser(Protocol):
    async def parse(
        self,
        *,
        filename: str,
        content: bytes,
        metadata: LiteratureMetadata,
    ) -> list[SearchableUnit]: ...


class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class LiteratureIndex(Protocol):
    async def ensure_collection(self, vector_size: int) -> None: ...

    async def upsert(
        self,
        units: list[SearchableUnit],
        vectors: list[list[float]],
    ) -> None: ...

    async def search(
        self,
        vector: list[float],
        *,
        limit: int,
        filters: LiteratureFilter,
    ) -> list[RetrievedUnit]: ...

    async def retrieve(self, unit_ids: list[UUID]) -> list[SearchableUnit]: ...

    async def list_documents(self) -> list[LiteratureDocument]: ...

    async def delete_document(self, document_id: UUID) -> None: ...


class CandidateReranker(Protocol):
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedUnit],
        *,
        limit: int,
    ) -> list[RetrievedUnit]: ...
