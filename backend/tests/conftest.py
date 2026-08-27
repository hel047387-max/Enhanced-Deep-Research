from collections.abc import Callable

import pytest
from pydantic import BaseModel

from deep_research.domain.plan import (
    CoverageLevel,
    GapAssessment,
    ResearchBrief,
    ResearchPlan,
    ResearchTask,
)
from tests.fakes import (
    GraphHarness,
    ResearcherHarness,
    ScriptedStructuredModel,
    SupervisorHarness,
)


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


@pytest.fixture
def partial_gap() -> GapAssessment:
    return GapAssessment(
        task_id="task-1",
        coverage=CoverageLevel.PARTIAL,
        covered_questions=["market size"],
        missing_questions=["growth rate"],
        next_queries=["targeted query"],
        should_continue=True,
        reason="Growth rate remains missing",
    )


@pytest.fixture
def sufficient_gap() -> GapAssessment:
    return GapAssessment(
        task_id="task-1",
        coverage=CoverageLevel.SUFFICIENT,
        covered_questions=["market size", "growth rate"],
        should_continue=False,
        reason="Completion criteria are covered",
    )


@pytest.fixture
def researcher_factory() -> Callable[[list[GapAssessment], int], ResearcherHarness]:
    return lambda gaps, total_queries=0: ResearcherHarness(gaps, total_queries)


@pytest.fixture
def supervisor_harness() -> SupervisorHarness:
    return SupervisorHarness()


@pytest.fixture
def graph_harness() -> GraphHarness:
    return GraphHarness()
