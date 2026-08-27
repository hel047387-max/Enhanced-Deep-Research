from deep_research.domain.review import ReviewResult


def review_prompt() -> str:
    fields = ", ".join(ReviewResult.model_fields)
    return (
        f"Return a ReviewResult with exactly these fields: {fields}. Check coverage, "
        "grounding, citation completeness, contradictions, overclaiming, and clarity. "
        "Reference exact section, paragraph, and evidence IDs. Choose one verdict only: "
        "pass, revise, or research_gap. research_gap requires exactly one targeted "
        "follow-up task; other verdicts require none. Do not alter evidence or provide "
        "hidden reasoning."
    )
