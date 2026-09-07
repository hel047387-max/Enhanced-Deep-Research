from deep_research.config import ResearchBudgets
from deep_research.domain.plan import GapAssessment
from deep_research.domain.review import ReviewVerdict


def may_research_again(
    gap: GapAssessment,
    current_round: int,
    total_queries: int,
    budgets: ResearchBudgets,
) -> bool:
    """根据缺口评估决定是否继续当前任务研究。"""
    return (
        gap.should_continue
        and bool(gap.next_queries)
        and current_round < budgets.max_research_rounds
        and total_queries < budgets.max_total_search_queries
    )


def take_dispatch_batch(task_ids: list[str], limit: int) -> list[str]:
    """按上限截取本轮要派发的任务。"""
    """按上限截取本轮要派发的任务。"""
    return task_ids[: max(0, min(limit, 3))]


def may_add_supervisor_tasks(
    supervisor_added_tasks: int,
    coverage_checked: bool,
    budgets: ResearchBudgets,
) -> bool:
    """判断是否允许监督器追加研究任务。"""
    return not coverage_checked and supervisor_added_tasks < budgets.max_supervisor_tasks


def route_review(verdict: ReviewVerdict, review_action_count: int) -> str:
    """将审查结论映射为图中的下一节点。"""
    """将审查结论映射为图中的下一节点。"""
    if review_action_count >= 1 or verdict is ReviewVerdict.PASS:
        return "finalize"
    return "revise" if verdict is ReviewVerdict.REVISE else "review_research"
