from deep_research.domain.plan import TaskStatus
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
    """校验 Evidence 关联并确定性渲染最终 Markdown 报告。"""
    draft = state["draft_report"]
    if draft is None:
        raise ValueError("cannot finalize without a draft")
    failure_limitations = [
        f"Failed task {task.task_id} ({task.title}) limited report coverage."
        for task in sorted(state.get("tasks", {}).values(), key=lambda item: item.task_id)
        if task.status is TaskStatus.FAILED
    ]
    if failure_limitations:
        draft = draft.model_copy(
            update={
                "limitations": [
                    *draft.limitations,
                    *(
                        limitation
                        for limitation in failure_limitations
                        if limitation not in draft.limitations
                    ),
                ]
            }
        )
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
