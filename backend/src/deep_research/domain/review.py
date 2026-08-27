from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from deep_research.domain.plan import ResearchTask


class ReviewVerdict(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    RESEARCH_GAP = "research_gap"


class ReportParagraph(BaseModel, frozen=True):
    paragraph_id: str
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ReportSection(BaseModel, frozen=True):
    section_id: str
    heading: str
    paragraphs: list[ReportParagraph]


class ReportDraft(BaseModel, frozen=True):
    title: str
    executive_summary: list[ReportParagraph]
    sections: list[ReportSection]
    limitations: list[str]
    suggested_actions: list[str]


class ReviewIssue(BaseModel, frozen=True):
    section_id: str | None = None
    paragraph_id: str | None = None
    evidence_id: str | None = None
    message: str


class ReviewResult(BaseModel, frozen=True):
    verdict: ReviewVerdict
    blocking_issues: list[ReviewIssue] = Field(default_factory=list)
    unsupported_claims: list[ReviewIssue] = Field(default_factory=list)
    conflicting_evidence: list[ReviewIssue] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    follow_up_tasks: list[ResearchTask] = Field(default_factory=list, max_length=1)

    @model_validator(mode="after")
    def validate_follow_up_task_semantics(self) -> "ReviewResult":
        if self.verdict is ReviewVerdict.RESEARCH_GAP and len(self.follow_up_tasks) != 1:
            raise ValueError("research_gap requires exactly one follow-up task")
        if self.verdict is not ReviewVerdict.RESEARCH_GAP and self.follow_up_tasks:
            raise ValueError("pass and revise verdicts cannot include follow-up tasks")
        return self
