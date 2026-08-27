from datetime import UTC, datetime

from deep_research.domain.plan import ResearchPlan, ResearchTask


def planning_prompt(source_preferences: list[str]) -> str:
    plan_fields = ", ".join(ResearchPlan.model_fields)
    task_fields = ", ".join(ResearchTask.model_fields)
    preferences = ", ".join(source_preferences) or "none supplied"
    return (
        f"Return a ResearchPlan with fields {plan_fields}; every ResearchTask uses fields "
        f"{task_fields}. Create 3-5 standalone, non-overlapping research tasks, each with "
        "one or two initial queries. Exclude report-writing tasks and do not invent user "
        "constraints. Current date: "
        f"{datetime.now(UTC).date().isoformat()}. Source preferences: "
        f"{preferences}. Do not provide hidden reasoning."
    )
