from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from deep_research.domain.errors import ResearchError
from deep_research.domain.evidence import EvidenceItem, Source
from deep_research.domain.plan import GapAssessment, ResearchBrief, ResearchTask
from deep_research.domain.review import ReportDraft, ReviewResult
from deep_research.state.reducers import (
    append_errors,
    merge_evidence,
    merge_gap_assessments,
    merge_sources,
    merge_tasks,
)

ResearchStatus = Literal[
    "created",
    "running",
    "waiting_for_user",
    "completed",
    "failed",
    "cancelled",
]


class ResearchState(TypedDict, total=False):
    """LangGraph state containing normalized research projections only."""

    run_id: NotRequired[str]
    thread_id: NotRequired[str]
    messages: NotRequired[Annotated[list[BaseMessage], add_messages]]
    clarification_count: NotRequired[int]
    research_brief: NotRequired[ResearchBrief | None]
    tasks: NotRequired[Annotated[dict[str, ResearchTask], merge_tasks]]
    sources: NotRequired[Annotated[dict[str, Source], merge_sources]]
    evidence: NotRequired[Annotated[dict[str, EvidenceItem], merge_evidence]]
    gap_assessments: NotRequired[Annotated[dict[str, GapAssessment], merge_gap_assessments]]
    supervisor_added_tasks: NotRequired[int]
    draft_report: NotRequired[ReportDraft | None]
    review_result: NotRequired[ReviewResult | None]
    review_action_count: NotRequired[int]
    final_report: NotRequired[str | None]
    status: NotRequired[ResearchStatus]
    errors: NotRequired[Annotated[list[ResearchError], append_errors]]
