from deep_research.domain.review import ReportDraft


def writing_prompt(*, revision: bool) -> str:
    fields = ", ".join(ReportDraft.model_fields)
    instruction = (
        "Revise the prior draft using the review instructions. "
        if revision
        else "Create the initial evidence-grounded draft. "
    )
    return (
        f"{instruction}Return a ReportDraft with exactly these fields: {fields}. "
        "Use only evidence IDs included in the supplied packet. Do not search, invent "
        "facts, invent identifiers, or provide hidden reasoning. State uncertainty in "
        "limitations."
    )
