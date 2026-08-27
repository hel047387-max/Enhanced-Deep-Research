from deep_research.domain.review import ReportDraft
from deep_research.services.citations import render_report, validate_draft
from deep_research.state.models import ResearchState


def _remove_invalid_associations(
    draft: ReportDraft,
    invalid_ids: set[str],
) -> ReportDraft:
    def clean_paragraph(paragraph):
        return paragraph.model_copy(
            update={
                "evidence_ids": [
                    item for item in paragraph.evidence_ids if item not in invalid_ids
                ]
            }
        )

    limitation = (
        "Insufficient evidence: invalid or unavailable citation associations were removed "
        "during deterministic finalization."
    )
    return draft.model_copy(
        update={
            "executive_summary": [
                clean_paragraph(paragraph) for paragraph in draft.executive_summary
            ],
            "sections": [
                section.model_copy(
                    update={
                        "paragraphs": [
                            clean_paragraph(paragraph)
                            for paragraph in section.paragraphs
                        ]
                    }
                )
                for section in draft.sections
            ],
            "limitations": [*draft.limitations, limitation],
        }
    )


async def finalize_report(state: ResearchState) -> dict[str, object]:
    draft = state["draft_report"]
    if draft is None:
        raise ValueError("cannot finalize without a draft")
    issues = validate_draft(
        draft,
        state.get("evidence", {}),
        state.get("sources", {}),
        state.get("tasks", {}),
    )
    if issues:
        invalid_ids = {
            issue.evidence_id for issue in issues if issue.evidence_id is not None
        }
        draft = _remove_invalid_associations(draft, invalid_ids)
    final_report = render_report(
        draft,
        state.get("evidence", {}),
        state.get("sources", {}),
        state.get("tasks", {}),
    )
    return {
        "draft_report": draft,
        "final_report": final_report,
        "status": "completed",
    }
