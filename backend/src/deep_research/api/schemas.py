from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from deep_research.domain.errors import ResearchError
from deep_research.domain.evidence import EvidenceItem, Source
from deep_research.domain.literature import (
    LiteratureFilter,
    LiteratureSearchRequest,
    RetrievedUnit,
    SearchableUnit,
)
from deep_research.domain.plan import ResearchBrief, ResearchTask
from deep_research.domain.review import ReviewResult
from deep_research.persistence.run_store import RunStatus

RequestText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
]


class ResearchStartRequest(BaseModel):
    """启动研究请求的 API 数据模型。"""
    query: RequestText


class ResearchResumeRequest(BaseModel):
    """恢复研究请求的 API 数据模型。"""
    answer: RequestText


class ResearchSnapshotResponse(BaseModel):
    """研究状态快照响应模型。"""
    run_id: str
    thread_id: str
    status: RunStatus
    clarification: str | None = None
    research_brief: ResearchBrief | None = None
    tasks: dict[str, ResearchTask] = Field(default_factory=dict)
    sources: dict[str, Source] = Field(default_factory=dict)
    evidence: dict[str, EvidenceItem] = Field(default_factory=dict)
    review: ReviewResult | None = None
    report: str | None = None
    errors: list[ResearchError] = Field(default_factory=list)


class ReportResponse(BaseModel):
    """最终报告响应模型。"""
    run_id: str
    thread_id: str
    report: str


class CancellationResponse(BaseModel):
    """取消操作响应模型。"""
    thread_id: str
    status: Literal["accepted"] = "accepted"


class HealthResponse(BaseModel):
    """健康检查响应模型。"""
    status: Literal["ok"] = "ok"


class ErrorResponse(BaseModel):
    """统一错误响应模型。"""
    detail: str


class LiteratureSearchBody(BaseModel):
    query: RequestText
    limit: int = Field(default=8, ge=1, le=50)
    document_ids: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    language: str | None = None
    year_from: int | None = Field(default=None, ge=1000, le=9999)
    year_to: int | None = Field(default=None, ge=1000, le=9999)

    def to_domain(self) -> LiteratureSearchRequest:
        return LiteratureSearchRequest(
            query=self.query,
            limit=self.limit,
            filters=LiteratureFilter(
                document_ids=self.document_ids,
                tags=self.tags,
                language=self.language,
                year_from=self.year_from,
                year_to=self.year_to,
            ),
        )


class LiteratureSearchItem(SearchableUnit):
    similarity_score: float
    rerank_score: float | None = None

    @classmethod
    def from_result(cls, result: RetrievedUnit) -> "LiteratureSearchItem":
        return cls(
            **result.unit.model_dump(),
            similarity_score=result.similarity_score,
            rerank_score=result.rerank_score,
        )


class LiteratureSearchResponse(BaseModel):
    items: list[LiteratureSearchItem] = Field(default_factory=list)
