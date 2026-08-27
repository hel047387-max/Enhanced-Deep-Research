from datetime import UTC, datetime

from deep_research.domain.plan import ResearchBrief


def clarification_prompt(source_preferences: list[str] | None = None) -> str:
    preferences = ", ".join(source_preferences or []) or "none supplied"
    return (
        "Decide whether the request is missing an essential subject, time range, or "
        "comparison criterion. Return exactly the ClarificationDecision schema fields: "
        "needs_clarification (boolean), question (string or null), and reason (string). "
        "Ask one concise question at most. Do not invent user constraints and do not "
        f"provide hidden reasoning. Current date: {datetime.now(UTC).date().isoformat()}. "
        f"Source preferences: {preferences}."
    )


def research_brief_prompt(source_preferences: list[str] | None = None) -> str:
    preferences = ", ".join(source_preferences or []) or "none supplied"
    fields = ", ".join(ResearchBrief.model_fields)
    return (
        f"Create a ResearchBrief with exactly these fields: {fields}. Preserve explicit "
        "user constraints, make remaining ambiguity an assumption, and never invent "
        "constraints. Current date: "
        f"{datetime.now(UTC).date().isoformat()}. Source preferences: "
        f"{preferences}. Do not provide hidden reasoning."
    )
