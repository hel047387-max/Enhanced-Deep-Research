from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from deep_research.domain.plan import ResearchBrief, ResearchPlan, ResearchTask
from deep_research.llm import StructuredModel
from deep_research.prompts.planning import planning_prompt


async def plan_research(
    state: dict[str, Any],
    model: StructuredModel,
) -> dict[str, dict[str, ResearchTask]]:
    brief = ResearchBrief.model_validate(state["research_brief"])
    raw = await model.ainvoke(
        [
            SystemMessage(content=planning_prompt(brief.source_preferences)),
            HumanMessage(content=brief.model_dump_json()),
        ]
    )
    plan = ResearchPlan.model_validate(raw)
    return {"tasks": {task.task_id: task for task in plan.tasks}}
