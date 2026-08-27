from collections.abc import Callable

import pytest
from pydantic import BaseModel

from deep_research.domain.plan import ResearchBrief, ResearchPlan, ResearchTask
from tests.fakes import ScriptedStructuredModel


@pytest.fixture
def brief() -> ResearchBrief:
    return ResearchBrief(
        main_question="How is the market growing?",
        scope="Global market fundamentals",
        time_range="2024-2026",
        comparison_dimensions=["growth", "competition"],
        source_preferences=["official sources"],
    )


@pytest.fixture
def three_task_plan() -> ResearchPlan:
    return ResearchPlan(
        strategy_summary="Cover scale, competition, and outlook independently.",
        tasks=[
            ResearchTask(
                task_id=f"task-{index}",
                title=title,
                objective=objective,
                completion_criteria=["Find one grounded answer"],
                search_queries=[query],
            )
            for index, (title, objective, query) in enumerate(
                [
                    ("Scale", "Measure market scale", "market scale"),
                    ("Competition", "Map competitors", "market competitors"),
                    ("Outlook", "Assess outlook", "market outlook"),
                ],
                start=1,
            )
        ],
    )


@pytest.fixture
def model_factory() -> Callable[[BaseModel | dict[str, object]], ScriptedStructuredModel]:
    return lambda result: ScriptedStructuredModel([result])
