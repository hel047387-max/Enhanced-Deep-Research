from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from deep_research.config import ResearchBudgets
from deep_research.domain.errors import ResearchError
from deep_research.domain.evidence import EvidenceItem, Relevance, Source, SourceType
from deep_research.domain.plan import (
    CoverageLevel,
    GapAssessment,
    ResearchBrief,
    ResearchTask,
    TaskStatus,
)
from deep_research.llm import StructuredModel
from deep_research.prompts.research import evidence_extraction_prompt
from deep_research.services.evidence_store import build_evidence, build_source
from deep_research.tools.search import SearchHit, SearchProvider


class ExtractedEvidence(BaseModel, frozen=True):
    claim: str = Field(min_length=1)
    excerpt: str = Field(min_length=1, max_length=1000)
    context: str = Field(min_length=1)
    relevance: Relevance


class EvidenceExtraction(BaseModel, frozen=True):
    items: list[ExtractedEvidence]


class ResearcherInput(TypedDict):
    task: ResearchTask
    research_brief: ResearchBrief
    total_queries: int
    query_budget: NotRequired[int]


class ResearcherState(ResearcherInput, total=False):
    queries: list[str]
    raw_results: list[SearchHit]
    sources: dict[str, Source]
    evidence: dict[str, EvidenceItem]
    gap_assessment: GapAssessment
    current_round: int
    queries_used: int
    errors: list[ResearchError]
    budget_exhausted: bool


class ResearcherOutput(TypedDict):
    updated_task: ResearchTask
    sources: dict[str, Source]
    evidence: dict[str, EvidenceItem]
    gap_assessment: GapAssessment
    errors: list[ResearchError]
    queries_used: int


def prepare_queries_node(budgets: ResearchBudgets):
    async def prepare_queries(state: ResearcherState) -> dict[str, object]:
        current_round = state.get("current_round", 0)
        used = state.get("queries_used", 0)
        remaining_global = max(
            0,
            budgets.max_total_search_queries - state.get("total_queries", 0) - used,
        )
        reserved = state.get("query_budget", remaining_global)
        remaining_reserved = max(0, reserved - used)
        if current_round == 0:
            candidates = state["task"].search_queries
        else:
            candidates = state["gap_assessment"].next_queries
        allowed = min(
            len(candidates),
            budgets.max_queries_per_round,
            remaining_global,
            remaining_reserved,
        )
        return {
            "queries": candidates[:allowed],
            "raw_results": [],
            "budget_exhausted": allowed == 0,
        }

    return prepare_queries


def execute_search_node(search_provider: SearchProvider):
    async def execute_search(state: ResearcherState) -> dict[str, object]:
        results: list[SearchHit] = []
        errors: list[ResearchError] = []
        for query in state.get("queries", []):
            try:
                results.extend(await search_provider.search(query, max_results=8))
            except Exception as exc:  # noqa: BLE001 - sanitize provider failures into state
                errors.append(
                    ResearchError(
                        error_code="search_failed",
                        stage="research",
                        message=str(exc),
                        task_id=state["task"].task_id,
                        retryable=True,
                    )
                )
        query_count = len(state.get("queries", []))
        return {
            "raw_results": results,
            "current_round": state.get("current_round", 0) + (1 if query_count else 0),
            "queries_used": state.get("queries_used", 0) + query_count,
            "errors": [*state.get("errors", []), *errors],
        }

    return execute_search


def extract_evidence_node(
    evidence_model: StructuredModel,
    budgets: ResearchBudgets,
):
    async def extract_evidence(state: ResearcherState) -> dict[str, object]:
        sources = dict(state.get("sources", {}))
        evidence = dict(state.get("evidence", {}))
        task = state["task"]
        brief = state["research_brief"]
        round_number = state.get("current_round", 1)
        for hit in state.get("raw_results", []):
            if len(sources) >= budgets.max_sources_per_task:
                break
            body = hit.raw_content or hit.content
            source = build_source(
                url=str(hit.url),
                title=hit.title,
                body=body,
                retrieved_at=datetime.now(UTC),
                source_type=SourceType.WEB,
            )
            sources[source.source_id] = source
            raw = await evidence_model.ainvoke(
                [
                    SystemMessage(
                        content=evidence_extraction_prompt(brief, task, round_number)
                    ),
                    HumanMessage(content=body),
                ]
            )
            extraction = EvidenceExtraction.model_validate(raw)
            for item in extraction.items:
                if len(evidence) >= budgets.max_evidence_per_task:
                    break
                built = build_evidence(
                    task_id=task.task_id,
                    source_id=source.source_id,
                    claim=item.claim,
                    excerpt=item.excerpt,
                    context=item.context,
                    relevance=item.relevance,
                    discovered_in_round=round_number,
                )
                evidence[built.evidence_id] = built
        return {"sources": sources, "evidence": evidence, "raw_results": []}

    return extract_evidence


def complete_task_node(state: ResearcherState) -> ResearcherOutput:
    gap = state.get("gap_assessment")
    if gap is None:
        gap = GapAssessment(
            task_id=state["task"].task_id,
            coverage=CoverageLevel.INSUFFICIENT,
            missing_questions=state["task"].completion_criteria,
            should_continue=False,
            reason="No global query capacity remained",
        )
    status = (
        TaskStatus.COMPLETED
        if gap.coverage is CoverageLevel.SUFFICIENT and state.get("evidence")
        else TaskStatus.INSUFFICIENT
    )
    return {
        "updated_task": state["task"].model_copy(
            update={"status": status, "current_round": state.get("current_round", 0)}
        ),
        "sources": state.get("sources", {}),
        "evidence": state.get("evidence", {}),
        "gap_assessment": gap,
        "errors": state.get("errors", []),
        "queries_used": state.get("queries_used", 0),
    }
