import pytest
from pydantic import ValidationError

from deep_research.domain.plan import ResearchPlan, ResearchTask, TaskStatus


def make_task(index: int) -> ResearchTask:
    return ResearchTask(
        task_id=f"task-{index}",
        title=f"Task {index}",
        objective=f"Answer sub-question {index}",
        completion_criteria=["At least two independent evidence items"],
        search_queries=[f"query {index}"],
    )


def test_plan_accepts_three_to_five_tasks() -> None:
    assert len(ResearchPlan(strategy_summary="Coverage", tasks=[make_task(i) for i in range(3)]).tasks) == 3
    assert len(ResearchPlan(strategy_summary="Coverage", tasks=[make_task(i) for i in range(5)]).tasks) == 5


def test_plan_rejects_duplicate_task_ids() -> None:
    with pytest.raises(ValidationError):
        ResearchPlan(strategy_summary="Bad", tasks=[make_task(1), make_task(1), make_task(2)])


def test_task_defaults_to_pending_round_zero() -> None:
    task = make_task(1)
    assert task.status is TaskStatus.PENDING
    assert task.current_round == 0
