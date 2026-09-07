from dataclasses import dataclass

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send, interrupt

from deep_research.config import ResearchBudgets
from deep_research.domain.errors import ResearchError
from deep_research.graph.routing import may_research_again, route_review
from deep_research.llm import StructuredModel
from deep_research.nodes.clarify import clarify_request, write_research_brief
from deep_research.nodes.finalizer import finalize_report
from deep_research.nodes.gap_analyzer import assess_gap_node
from deep_research.nodes.planner import plan_research
from deep_research.nodes.researcher import (
    ResearcherInput,
    ResearcherOutput,
    ResearcherState,
    complete_task_node,
    prepare_queries_node,
    research_round_node,
)
from deep_research.nodes.reviewer import review_report
from deep_research.nodes.supervisor import (
    ResearcherRunner,
    SupervisorState,
    assess_coverage_node,
    prepare_dispatch_node,
    research_task_node,
)
from deep_research.nodes.writer import write_report
from deep_research.runtime import CancellationChecker, EventSink
from deep_research.services.citations import validate_draft
from deep_research.state.models import ResearchState
from deep_research.tools.search import SearchProvider


@dataclass(frozen=True)
class WorkflowDependencies:
    """保存构建研究图所需的模型、工具、预算和运行时回调。"""
    clarifier_model: StructuredModel
    planner_model: StructuredModel
    evidence_model: StructuredModel
    gap_model: StructuredModel
    writer_model: StructuredModel
    reviewer_model: StructuredModel
    search_provider: SearchProvider
    budgets: ResearchBudgets
    event_sink: EventSink
    cancellation_checker: CancellationChecker


def build_researcher_graph(
    search_provider: SearchProvider,
    evidence_model: StructuredModel,
    gap_model: StructuredModel,
    budgets: ResearchBudgets,
    event_sink: EventSink,
    cancellation_checker: CancellationChecker,
):
    """构建单个 Researcher 的查询、搜索、缺口分析和完成子图。"""
    builder = StateGraph(
        ResearcherState,
        input_schema=ResearcherInput,
        output_schema=ResearcherOutput,
    )
    builder.add_node("prepare_queries", prepare_queries_node(budgets, event_sink))
    builder.add_node(
        "research_round",
        research_round_node(
            search_provider,
            evidence_model,
            budgets,
            event_sink,
            cancellation_checker,
        ),
    )
    builder.add_node(
        "assess_gap",
        assess_gap_node(gap_model, event_sink, cancellation_checker),
    )
    builder.add_node("complete_task", complete_task_node(event_sink))
    builder.add_edge(START, "prepare_queries")

    def after_prepare(state: ResearcherState) -> str:
        return "complete" if not state.get("queries") else "search"

    builder.add_conditional_edges(
        "prepare_queries",
        after_prepare,
        {"search": "research_round", "complete": "complete_task"},
    )
    builder.add_conditional_edges(
        "research_round",
        lambda state: "done" if state.get("failed", False) else "gap",
        {"done": "complete_task", "gap": "assess_gap"},
    )

    def route_researcher(state: ResearcherState) -> str:
        if state.get("failed", False):
            return "done"
        can_continue = may_research_again(
            state["gap_assessment"],
            state.get("current_round", 0),
            state.get("total_queries", 0) + state.get("queries_used", 0),
            budgets,
        )
        if state.get("queries_used", 0) >= state.get(
            "query_budget", budgets.max_total_search_queries
        ):
            can_continue = False
        if can_continue:
            cancellation_checker.raise_if_cancelled()
        return "search" if can_continue else "done"

    builder.add_conditional_edges(
        "assess_gap",
        route_researcher,
        {"search": "prepare_queries", "done": "complete_task"},
    )
    builder.add_edge("complete_task", END)
    return builder.compile()


def build_supervisor_graph(
    researcher_runner: ResearcherRunner,
    coverage_model: StructuredModel,
    budgets: ResearchBudgets,
):
    """构建 Supervisor 子图，负责派发研究任务和全局覆盖检查。"""
    builder = StateGraph(SupervisorState)
    builder.add_node("prepare_dispatch", prepare_dispatch_node(budgets))
    builder.add_node("research_task", research_task_node(researcher_runner))
    builder.add_node("assess_coverage", assess_coverage_node(coverage_model, budgets))
    builder.add_node("finish", lambda _state: {})
    builder.add_edge(START, "prepare_dispatch")

    def route_dispatch(state: SupervisorState):
        if state.get("dispatch_batch"):
            return [
                Send(
                    "research_task",
                    {
                        "task": state["tasks"][reservation["task_id"]],
                        "research_brief": state["research_brief"],
                        "total_queries": reservation["total_queries"],
                        "query_budget": reservation["query_budget"],
                    },
                )
                for reservation in state["dispatch_batch"]
            ]
        return "done" if state.get("coverage_checked", False) else "coverage"

    builder.add_conditional_edges(
        "prepare_dispatch",
        route_dispatch,
        {"coverage": "assess_coverage", "done": "finish"},
    )
    builder.add_edge("research_task", "prepare_dispatch")
    builder.add_edge("assess_coverage", "prepare_dispatch")
    builder.add_edge("finish", END)
    return builder.compile()


def build_research_graph_builder(
    deps: WorkflowDependencies,
) -> StateGraph:
    """组装顶层研究图，并连接澄清、规划、研究、写作、评审和最终化。"""
    researcher = build_researcher_graph(
        search_provider=deps.search_provider,
        evidence_model=deps.evidence_model,
        gap_model=deps.gap_model,
        budgets=deps.budgets,
        event_sink=deps.event_sink,
        cancellation_checker=deps.cancellation_checker,
    )
    supervisor = build_supervisor_graph(
        researcher_runner=researcher.ainvoke,
        coverage_model=deps.gap_model,
        budgets=deps.budgets,
    )
    builder = StateGraph(ResearchState)

    async def clarify_node(state: ResearchState) -> dict[str, object]:
        deps.cancellation_checker.raise_if_cancelled()
        patch = await clarify_request(state, deps.clarifier_model)
        if patch.get("interrupt_question"):
            await deps.event_sink.emit(
                "clarification_required",
                {"question": patch["interrupt_question"]},
            )
        return patch

    async def ask_clarification_node(state: ResearchState) -> dict[str, object]:
        answer = interrupt({"question": state["interrupt_question"]})
        return {
            "messages": [HumanMessage(content=str(answer))],
            "interrupt_question": None,
            "status": "running",
        }

    async def brief_node(state: ResearchState) -> dict[str, object]:
        deps.cancellation_checker.raise_if_cancelled()
        patch = await write_research_brief(state, deps.clarifier_model)
        await deps.event_sink.emit(
            "research_brief_created",
            {"brief": patch["research_brief"].model_dump(mode="json")},
        )
        return patch

    async def planner_node(state: ResearchState) -> dict[str, object]:
        deps.cancellation_checker.raise_if_cancelled()
        patch = await plan_research(state, deps.planner_model, budgets=deps.budgets)
        await deps.event_sink.emit(
            "plan_created",
            {
                "task_count": len(patch["tasks"]),
                "tasks": [
                    task.model_dump(mode="json")
                    for task in patch["tasks"].values()
                ],
            },
        )
        return patch

    async def supervisor_node(state: ResearchState) -> dict[str, object]:
        deps.cancellation_checker.raise_if_cancelled()
        result = await supervisor.ainvoke(
            {
                "research_brief": state["research_brief"],
                "tasks": state.get("tasks", {}),
                "sources": state.get("sources", {}),
                "evidence": state.get("evidence", {}),
                "gap_assessments": state.get("gap_assessments", {}),
                "total_queries": state.get("total_queries", 0),
                "coverage_checked": state.get("coverage_checked", False),
                "supervisor_added_tasks": state.get("supervisor_added_tasks", 0),
                "errors": state.get("errors", []),
            }
        )
        await deps.event_sink.emit(
            "coverage_assessed",
            {"task_count": len(result.get("tasks", {}))},
        )
        return {
            key: result[key]
            for key in (
                "tasks",
                "sources",
                "evidence",
                "gap_assessments",
                "total_queries",
                "coverage_checked",
                "supervisor_added_tasks",
                "errors",
            )
            if key in result
        }

    async def no_evidence_node(_state: ResearchState) -> dict[str, object]:
        return {
            "status": "failed",
            "errors": [
                ResearchError(
                    error_code="no_valid_evidence",
                    stage="writing",
                    message="No valid evidence was available; report generation stopped.",
                )
            ],
        }

    async def writer_node(state: ResearchState) -> dict[str, object]:
        deps.cancellation_checker.raise_if_cancelled()
        patch = await write_report(state, deps.writer_model)
        await deps.event_sink.emit("draft_created", {})
        return patch

    async def validate_initial_draft_node(state: ResearchState) -> dict[str, object]:
        issues = validate_draft(
            state["draft_report"],
            state.get("evidence", {}),
            state.get("sources", {}),
            state.get("tasks", {}),
        )
        if not issues:
            return {}
        return {
            "status": "failed",
            "errors": [
                ResearchError(
                    error_code="invalid_draft_citations",
                    stage="writing",
                    message="; ".join(issue.message for issue in issues),
                )
            ],
        }

    async def reviewer_node(state: ResearchState) -> dict[str, object]:
        deps.cancellation_checker.raise_if_cancelled()
        try:
            patch = await review_report(state, deps.reviewer_model)
        except Exception:  # noqa: BLE001 - degrade with a stable public result
            draft = state["draft_report"]
            if draft is None:
                raise ValueError("reviewer fallback requires a draft") from None
            limitation = (
                "Review incomplete: reviewer assessment failed; deterministic citation "
                "validation was used."
            )
            await deps.event_sink.emit(
                "review_completed",
                {"status": "incomplete"},
            )
            return {
                "draft_report": draft.model_copy(
                    update={"limitations": [*draft.limitations, limitation]}
                ),
                "review_result": None,
                "review_incomplete": True,
                "errors": [
                    ResearchError(
                        error_code="review_failed",
                        stage="review",
                        message=(
                            "Reviewer assessment failed; deterministic finalization "
                            "continued."
                        ),
                        retryable=True,
                    )
                ],
            }
        await deps.event_sink.emit(
            "review_completed",
            {
                "verdict": patch["review_result"].verdict.value,
                "review": patch["review_result"].model_dump(mode="json"),
            },
        )
        return patch

    async def skip_reviewer_research_node(state: ResearchState) -> dict[str, object]:
        draft = state["draft_report"]
        if draft is None:
            raise ValueError("reviewer budget fallback requires a draft")
        limitation = (
            "Reviewer research was skipped because the configured Reviewer task budget "
            "is zero."
        )
        return {
            "draft_report": draft.model_copy(
                update={"limitations": [*draft.limitations, limitation]}
            )
        }

    async def revise_node(state: ResearchState) -> dict[str, object]:
        deps.cancellation_checker.raise_if_cancelled()
        await deps.event_sink.emit("revision_started", {})
        patch = await write_report(state, deps.writer_model)
        return {**patch, "review_action_count": state.get("review_action_count", 0) + 1}

    async def review_research_node(state: ResearchState) -> dict[str, object]:
        deps.cancellation_checker.raise_if_cancelled()
        if deps.budgets.max_reviewer_tasks < 1:
            raise ValueError("reviewer task budget is exhausted")
        review = state["review_result"]
        if review is None or len(review.follow_up_tasks) != 1:
            raise ValueError("research_gap requires exactly one follow-up task")
        task = review.follow_up_tasks[0]
        remaining = max(
            0,
            deps.budgets.max_total_search_queries - state.get("total_queries", 0),
        )
        grant = min(
            remaining,
            deps.budgets.max_research_rounds * deps.budgets.max_queries_per_round,
        )
        output = await researcher.ainvoke(
            {
                "task": task,
                "research_brief": state["research_brief"],
                "total_queries": state.get("total_queries", 0),
                "query_budget": grant,
            }
        )
        gap = output["gap_assessment"]
        return {
            "tasks": {output["updated_task"].task_id: output["updated_task"]},
            "sources": output["sources"],
            "evidence": output["evidence"],
            "gap_assessments": {gap.task_id: gap},
            "errors": output["errors"],
            "total_queries": output["queries_used"],
            "review_action_count": state.get("review_action_count", 0) + 1,
        }

    async def rewrite_after_research_node(state: ResearchState) -> dict[str, object]:
        deps.cancellation_checker.raise_if_cancelled()
        await deps.event_sink.emit("revision_started", {"after_research": True})
        return await write_report(state, deps.writer_model)

    async def finalizer_node(state: ResearchState) -> dict[str, object]:
        deps.cancellation_checker.raise_if_cancelled()
        patch = await finalize_report(state)
        await deps.event_sink.emit(
            "report_finalized",
            {"report": patch["final_report"]},
        )
        return patch

    builder.add_node("clarify", clarify_node)
    builder.add_node("ask_clarification", ask_clarification_node)
    builder.add_node("brief", brief_node)
    builder.add_node("planner", planner_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("no_evidence", no_evidence_node)
    builder.add_node("writer", writer_node)
    builder.add_node("validate_initial_draft", validate_initial_draft_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("skip_reviewer_research", skip_reviewer_research_node)
    builder.add_node("revise", revise_node)
    builder.add_node("review_research", review_research_node)
    builder.add_node("rewrite_after_research", rewrite_after_research_node)
    builder.add_node("finalizer", finalizer_node)
    builder.add_edge(START, "clarify")
    builder.add_conditional_edges(
        "clarify",
        lambda state: "ask" if state.get("interrupt_question") else "brief",
        {"ask": "ask_clarification", "brief": "brief"},
    )
    builder.add_edge("ask_clarification", "brief")
    builder.add_edge("brief", "planner")
    builder.add_edge("planner", "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        lambda state: "write" if state.get("evidence") else "fail",
        {"write": "writer", "fail": "no_evidence"},
    )
    builder.add_edge("no_evidence", END)
    builder.add_edge("writer", "validate_initial_draft")
    builder.add_conditional_edges(
        "validate_initial_draft",
        lambda state: "fail" if state.get("status") == "failed" else "review",
        {"fail": END, "review": "reviewer"},
    )

    def review_route(state: ResearchState) -> str:
        review = state.get("review_result")
        if review is None:
            return "finalize"
        if (
            review.verdict.value == "research_gap"
            and deps.budgets.max_reviewer_tasks < 1
        ):
            return "skip_research"
        return route_review(review.verdict, state.get("review_action_count", 0))

    builder.add_conditional_edges(
        "reviewer",
        review_route,
        {
            "finalize": "finalizer",
            "revise": "revise",
            "review_research": "review_research",
            "skip_research": "skip_reviewer_research",
        },
    )
    builder.add_edge("skip_reviewer_research", "finalizer")
    builder.add_edge("revise", "finalizer")
    builder.add_edge("review_research", "rewrite_after_research")
    builder.add_edge("rewrite_after_research", "finalizer")
    builder.add_edge("finalizer", END)
    return builder


def build_research_graph(
    deps: WorkflowDependencies,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """编译顶层 StateGraph，可选注入 checkpoint 以支持恢复。"""
    return build_research_graph_builder(deps).compile(checkpointer=checkpointer)
