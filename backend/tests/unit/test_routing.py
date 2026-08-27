from deep_research.config import ResearchBudgets
from deep_research.domain.plan import CoverageLevel, GapAssessment
from deep_research.domain.review import ReviewVerdict
from deep_research.graph.routing import (
    may_add_supervisor_tasks,
    may_research_again,
    route_review,
    take_dispatch_batch,
)


def _actionable_gap() -> GapAssessment:
    return GapAssessment(
        task_id="task-1",
        coverage=CoverageLevel.PARTIAL,
        next_queries=["next"],
        should_continue=True,
        reason="missing",
    )


def test_research_again_requires_gap_queries_and_both_budgets() -> None:
    gap = _actionable_gap()
    budgets = ResearchBudgets()

    assert may_research_again(gap, current_round=1, total_queries=19, budgets=budgets)
    assert not may_research_again(gap, current_round=2, total_queries=19, budgets=budgets)
    assert not may_research_again(gap, current_round=1, total_queries=20, budgets=budgets)


def test_research_again_rejects_non_actionable_gap() -> None:
    gap = _actionable_gap().model_copy(update={"should_continue": False})

    assert not may_research_again(gap, 1, 0, ResearchBudgets())
    assert not may_research_again(
        gap.model_copy(update={"should_continue": True, "next_queries": []}),
        1,
        0,
        ResearchBudgets(),
    )


def test_dispatch_batch_never_exceeds_three() -> None:
    assert take_dispatch_batch(["a", "b", "c", "d"], limit=3) == ["a", "b", "c"]
    assert take_dispatch_batch(["a", "b", "c", "d"], limit=99) == ["a", "b", "c"]


def test_supervisor_tasks_are_allowed_only_before_coverage_check() -> None:
    budgets = ResearchBudgets()

    assert may_add_supervisor_tasks(0, False, budgets)
    assert not may_add_supervisor_tasks(0, True, budgets)
    assert not may_add_supervisor_tasks(2, False, budgets)


def test_review_route_allows_only_one_repair_action() -> None:
    assert route_review(ReviewVerdict.PASS, 0) == "finalize"
    assert route_review(ReviewVerdict.REVISE, 0) == "revise"
    assert route_review(ReviewVerdict.RESEARCH_GAP, 0) == "review_research"
    assert route_review(ReviewVerdict.REVISE, 1) == "finalize"
    assert route_review(ReviewVerdict.RESEARCH_GAP, 1) == "finalize"
