from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from deep_research.domain.errors import ResearchError
from deep_research.domain.evidence import EvidenceItem, Source
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
