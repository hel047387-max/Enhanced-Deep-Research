from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from deep_research.application.research_adapter import (
    ResearchAdapter,
    ResearchEvidenceBatch,
)
from deep_research.config import ResearchBudgets
from deep_research.domain.errors import ResearchError
from deep_research.domain.evidence import (
    EvidenceItem,
    EvidenceSource,
    Relevance,
    SourceType,
)
from deep_research.domain.plan import (
    CoverageLevel,
    GapAssessment,
    ResearchBrief,
    ResearchTask,
    TaskStatus,
)
from deep_research.llm import StructuredModel
from deep_research.prompts.research import evidence_extraction_prompt
from deep_research.runtime import CancellationChecker, EventSink
from deep_research.services.evidence_store import build_evidence, build_source
from deep_research.tools.search import SearchProvider


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
    use_literature: NotRequired[bool]


class ResearcherState(ResearcherInput, total=False):
    queries: list[str]
    sources: dict[str, EvidenceSource]
    evidence: dict[str, EvidenceItem]
    gap_assessment: GapAssessment
    current_round: int
    queries_used: int
    errors: list[ResearchError]
    budget_exhausted: bool
    failed: bool
    failure_code: str
    task_started_emitted: bool


class ResearcherOutput(TypedDict):
    updated_task: ResearchTask
    sources: dict[str, EvidenceSource]
    evidence: dict[str, EvidenceItem]
    gap_assessment: GapAssessment
    errors: list[ResearchError]
    queries_used: int


_PUBLIC_FAILURES: dict[str, tuple[str, bool]] = {
    "search_failed": ("Search provider request failed.", True),
    "source_normalization_failed": ("A search result could not be normalized safely.", False),
    "evidence_extraction_failed": ("Evidence extraction failed.", True),
    "gap_analysis_failed": ("Gap assessment failed.", True),
}


def researcher_failure_patch(
    state: ResearcherState,
    error_code: str,
    *,
    current_round: int | None = None,
    queries_used: int | None = None,
) -> dict[str, object]:
    message, retryable = _PUBLIC_FAILURES[error_code]
    task = state["task"]
    return {
        "failed": True,
        "failure_code": error_code,
        "current_round": (
            state.get("current_round", 0)
            if current_round is None
            else current_round
        ),
        "queries_used": (
            state.get("queries_used", 0) if queries_used is None else queries_used
        ),
        "sources": {},
        "evidence": {},
        "gap_assessment": GapAssessment(
            task_id=task.task_id,
            coverage=CoverageLevel.INSUFFICIENT,
            missing_questions=task.completion_criteria,
            evidence_issues=[message],
            should_continue=False,
            reason=message,
        ),
        "errors": [
            *state.get("errors", []),
            ResearchError(
                error_code=error_code,
                stage="research",
                message=message,
                task_id=task.task_id,
                retryable=retryable,
            ),
        ],
    }


def prepare_queries_node(budgets: ResearchBudgets, event_sink: EventSink):
    async def prepare_queries(state: ResearcherState) -> dict[str, object]:
        """根据任务目标生成并限制本轮搜索查询。"""
        patch: dict[str, object] = {}
        if not state.get("task_started_emitted", False):
            await event_sink.emit("task_started", {"task_id": state["task"].task_id})
            patch["task_started_emitted"] = True
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
        patch.update(
            {
                "queries": candidates[:allowed],
                "budget_exhausted": allowed == 0,
            }
        )
        return patch

    return prepare_queries


def research_round_node(
    search_provider: SearchProvider,
    evidence_model: StructuredModel,
    budgets: ResearchBudgets,
    event_sink: EventSink,
    cancellation_checker: CancellationChecker,
    literature_adapter: ResearchAdapter | None = None,
):
    async def research_round(state: ResearcherState) -> dict[str, object]:
        """执行搜索、提取证据并更新任务轮次。"""
        task = state["task"]
        brief = state["research_brief"]
        queries = state.get("queries", [])
        round_number = state.get("current_round", 0) + 1
        attempts = 0
        hits = []
        literature_batches: list[ResearchEvidenceBatch] = []
        literature_errors: list[ResearchError] = []
        await event_sink.emit(
            "search_started",
            {
                "task_id": task.task_id,
                "round": round_number,
                "query_count": len(queries),
            },
        )
        for query in queries:
            cancellation_checker.raise_if_cancelled()
            attempts += 1
            if state.get("use_literature", False) and literature_adapter is not None:
                try:
                    literature_batches.append(
                        await literature_adapter.search(
                            query,
                            task=task,
                            brief=brief,
                            round_number=round_number,
                            max_sources=budgets.max_sources_per_task,
                            max_evidence=budgets.max_evidence_per_task,
                        )
                    )
                except Exception:  # noqa: BLE001 - web research can still continue
                    literature_errors.append(
                        ResearchError(
                            error_code="literature_search_failed",
                            stage="research",
                            message=(
                                "Indexed literature search failed; web research "
                                "continued."
                            ),
                            task_id=task.task_id,
                            retryable=True,
                        )
                    )
            try:
                hits.extend(
                    await search_provider.search(
                        query,
                        max_results=budgets.max_sources_per_task,
                    )
                )
            except Exception:  # noqa: BLE001 - converted to a stable public error
                await event_sink.emit(
                    "search_completed",
                    {
                        "task_id": task.task_id,
                        "round": round_number,
                        "query_count": attempts,
                        "result_count": 0,
                        "status": "failed",
                    },
                )
                return researcher_failure_patch(
                    state,
                    "search_failed",
                    current_round=round_number,
                    queries_used=state.get("queries_used", 0) + attempts,
                )
        await event_sink.emit(
            "search_completed",
            {
                "task_id": task.task_id,
                "round": round_number,
                "query_count": attempts,
                "result_count": len(hits) + sum(len(batch.sources) for batch in literature_batches),
                "status": "completed",
            },
        )

        sources = dict(state.get("sources", {}))
        evidence = dict(state.get("evidence", {}))
        added_ids: list[str] = []
        for batch in literature_batches:
            for source_id, source in batch.sources.items():
                if len(sources) >= budgets.max_sources_per_task:
                    break
                sources[source_id] = source
            for evidence_id, item in batch.evidence.items():
                if len(evidence) >= budgets.max_evidence_per_task:
                    break
                if item.source_id in sources:
                    evidence[evidence_id] = item
                    added_ids.append(evidence_id)
        for hit in hits:
            if len(sources) >= budgets.max_sources_per_task:
                break
            body = hit.raw_content or hit.content
            try:
                source = build_source(
                    url=str(hit.url),
                    title=hit.title,
                    body=body,
                    retrieved_at=datetime.now(UTC),
                    source_type=SourceType.WEB,
                )
            except Exception:  # noqa: BLE001 - converted to a stable public error
                return researcher_failure_patch(
                    state,
                    "source_normalization_failed",
                    current_round=round_number,
                    queries_used=state.get("queries_used", 0) + attempts,
                )
            cancellation_checker.raise_if_cancelled()
            try:
                raw = await evidence_model.ainvoke(
                    [
                        SystemMessage(
                            content=evidence_extraction_prompt(
                                brief, task, round_number
                            )
                        ),
                        HumanMessage(content=body),
                    ]
                )
                extraction = EvidenceExtraction.model_validate(raw)
            except Exception:  # noqa: BLE001 - converted to a stable public error
                return researcher_failure_patch(
                    state,
                    "evidence_extraction_failed",
                    current_round=round_number,
                    queries_used=state.get("queries_used", 0) + attempts,
                )
            sources[source.source_id] = source
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
                added_ids.append(built.evidence_id)
        if added_ids:
            added_evidence = [evidence[evidence_id] for evidence_id in sorted(added_ids)]
            added_source_ids = {item.source_id for item in added_evidence}
            await event_sink.emit(
                "evidence_added",
                {
                    "task_id": task.task_id,
                    "round": round_number,
                    "evidence_ids": sorted(added_ids),
                    "count": len(added_ids),
                    "sources": [
                        sources[source_id].model_dump(mode="json")
                        for source_id in sorted(added_source_ids)
                    ],
                    "evidence": [
                        item.model_dump(mode="json") for item in added_evidence
                    ],
                },
            )
        return {
            "sources": sources,
            "evidence": evidence,
            "current_round": round_number,
            "queries_used": state.get("queries_used", 0) + attempts,
            "errors": [*state.get("errors", []), *literature_errors],
        }

    return research_round


def complete_task_node(event_sink: EventSink):
    async def complete_task(state: ResearcherState) -> ResearcherOutput:
        """汇总研究结果并生成任务完成或失败输出。"""
        gap = state.get("gap_assessment")
        if gap is None:
            gap = GapAssessment(
                task_id=state["task"].task_id,
                coverage=CoverageLevel.INSUFFICIENT,
                missing_questions=state["task"].completion_criteria,
                should_continue=False,
                reason="No global query capacity remained",
            )
        if state.get("failed", False):
            status = TaskStatus.FAILED
        elif gap.coverage is CoverageLevel.SUFFICIENT and state.get("evidence"):
            status = TaskStatus.COMPLETED
        else:
            status = TaskStatus.INSUFFICIENT
        errors = state.get("errors", [])
        updated_task = state["task"].model_copy(
            update={
                "status": status,
                "current_round": state.get("current_round", 0),
                "error": errors[-1].message if status is TaskStatus.FAILED else None,
            }
        )
        event_type = "task_failed" if status is TaskStatus.FAILED else "task_completed"
        payload: dict[str, object] = {
            "task_id": updated_task.task_id,
            "status": status.value,
            "round": updated_task.current_round,
            "queries_used": state.get("queries_used", 0),
        }
        if status is TaskStatus.FAILED:
            payload["error_code"] = errors[-1].error_code
        await event_sink.emit(event_type, payload)
        return {
            "updated_task": updated_task,
            "sources": state.get("sources", {}),
            "evidence": state.get("evidence", {}),
            "gap_assessment": gap,
            "errors": errors,
            "queries_used": state.get("queries_used", 0),
        }

    return complete_task
