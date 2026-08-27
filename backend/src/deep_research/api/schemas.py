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
    query: RequestText


class ResearchResumeRequest(BaseModel):
    answer: RequestText


class ResearchSnapshotResponse(BaseModel):
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
    run_id: str
    thread_id: str
    report: str


class CancellationResponse(BaseModel):
    thread_id: str
    status: Literal["accepted"] = "accepted"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorResponse(BaseModel):
    detail: str
