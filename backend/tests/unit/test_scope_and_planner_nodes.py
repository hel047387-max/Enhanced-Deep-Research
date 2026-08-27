import pytest

from deep_research.config import ResearchBudgets
from deep_research.nodes.clarify import clarify_request, write_research_brief
from deep_research.nodes.planner import plan_research
from tests.fakes import ScriptedStructuredModel


@pytest.mark.asyncio
async def test_clarifier_requests_only_one_answer() -> None:
    model = ScriptedStructuredModel(
        [
            {
                "needs_clarification": True,
                "question": "Which time range?",
                "reason": "Missing range",
            }
        ]
    )

    result = await clarify_request(
        {"messages": ["Research market growth"], "clarification_count": 0}, model
    )

    assert result["interrupt_question"] == "Which time range?"
    assert result["clarification_count"] == 1


@pytest.mark.asyncio
async def test_clarifier_never_interrupts_twice() -> None:
    model = ScriptedStructuredModel(
        [
            {
                "needs_clarification": True,
                "question": "Which region?",
                "reason": "Region remains unspecified",
            }
        ]
    )

    result = await clarify_request(
        {"messages": ["Research market growth"], "clarification_count": 1}, model
    )

    assert "interrupt_question" not in result
    assert result["clarification_assumptions"] == ["Region remains unspecified"]


@pytest.mark.asyncio
async def test_brief_node_validates_structured_output(brief, model_factory) -> None:
    result = await write_research_brief(
        {"messages": ["Research market growth"]},
        model_factory(brief.model_dump()),
    )

    assert result == {"research_brief": brief}


@pytest.mark.asyncio
async def test_planner_returns_three_to_five_unique_tasks(
    brief, three_task_plan, model_factory
) -> None:
    result = await plan_research(
        {"research_brief": brief}, model_factory(three_task_plan)
    )

    assert len(result["tasks"]) == 3
    assert len(set(result["tasks"])) == 3


@pytest.mark.asyncio
async def test_planner_rejects_too_few_tasks(brief, model_factory) -> None:
    invalid = {
        "strategy_summary": "Too narrow",
        "tasks": [
            {
                "task_id": "only",
                "title": "Only task",
                "objective": "Do everything",
                "completion_criteria": ["Done"],
                "search_queries": ["everything"],
            }
        ],
    }

    with pytest.raises(ValueError):
        await plan_research({"research_brief": brief}, model_factory(invalid))


@pytest.mark.asyncio
async def test_planner_truncates_valid_plan_to_configured_initial_task_budget(
    brief, three_task_plan, model_factory
) -> None:
    five_tasks = [
        three_task_plan.tasks[index % 3].model_copy(
            update={"task_id": f"task-{index + 1}"}
        )
        for index in range(5)
    ]
    plan = three_task_plan.model_copy(update={"tasks": five_tasks})

    result = await plan_research(
        {"research_brief": brief},
        model_factory(plan),
        budgets=ResearchBudgets(max_initial_tasks=3),
    )

    assert list(result["tasks"]) == ["task-1", "task-2", "task-3"]
