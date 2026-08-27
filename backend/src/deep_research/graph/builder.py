from langgraph.graph import END, START, StateGraph

from deep_research.config import ResearchBudgets
from deep_research.graph.routing import may_research_again
from deep_research.llm import StructuredModel
from deep_research.nodes.gap_analyzer import assess_gap_node
from deep_research.nodes.researcher import (
    ResearcherInput,
    ResearcherOutput,
    ResearcherState,
    complete_task_node,
    execute_search_node,
    extract_evidence_node,
    prepare_queries_node,
)
from deep_research.tools.search import SearchProvider


def build_researcher_graph(
    search_provider: SearchProvider,
    evidence_model: StructuredModel,
    gap_model: StructuredModel,
    budgets: ResearchBudgets,
):
    builder = StateGraph(
        ResearcherState,
        input_schema=ResearcherInput,
        output_schema=ResearcherOutput,
    )
    builder.add_node("prepare_queries", prepare_queries_node(budgets))
    builder.add_node("execute_search", execute_search_node(search_provider))
    builder.add_node("extract_evidence", extract_evidence_node(evidence_model, budgets))
    builder.add_node("assess_gap", assess_gap_node(gap_model))
    builder.add_node("complete_task", complete_task_node)
    builder.add_edge(START, "prepare_queries")

    def after_prepare(state: ResearcherState) -> str:
        return "complete" if not state.get("queries") else "search"

    builder.add_conditional_edges(
        "prepare_queries",
        after_prepare,
        {"search": "execute_search", "complete": "complete_task"},
    )
    builder.add_edge("execute_search", "extract_evidence")
    builder.add_edge("extract_evidence", "assess_gap")

    def route_researcher(state: ResearcherState) -> str:
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
        return "search" if can_continue else "done"

    builder.add_conditional_edges(
        "assess_gap",
        route_researcher,
        {"search": "prepare_queries", "done": "complete_task"},
    )
    builder.add_edge("complete_task", END)
    return builder.compile()
