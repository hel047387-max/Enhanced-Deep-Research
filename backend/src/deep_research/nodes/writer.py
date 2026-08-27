import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from deep_research.domain.review import ReportDraft
from deep_research.llm import StructuredModel
from deep_research.prompts.writing import writing_prompt


async def write_report(
    state: dict[str, Any],
    model: StructuredModel,
) -> dict[str, ReportDraft]:
    review = state.get("review_result")
    packet = {
        "research_brief": state["research_brief"].model_dump(),
        "task_summaries": {
            task_id: {
                "title": task.title,
                "objective": task.objective,
                "status": task.status,
                "gap_reason": task.gap_reason,
            }
            for task_id, task in state.get("tasks", {}).items()
        },
        "sources": {
            source_id: {
                "title": source.title,
                "url": str(source.url),
                "domain": source.domain,
            }
            for source_id, source in state.get("sources", {}).items()
        },
        "evidence": {
            evidence_id: item.model_dump(mode="json")
            for evidence_id, item in state.get("evidence", {}).items()
        },
        "prior_draft": (
            state["draft_report"].model_dump(mode="json")
            if review is not None and state.get("draft_report") is not None
            else None
        ),
        "review": review.model_dump(mode="json") if review is not None else None,
    }
    raw = await model.ainvoke(
        [
            SystemMessage(content=writing_prompt(revision=review is not None)),
            HumanMessage(content=json.dumps(packet, default=str)),
        ]
    )
    return {"draft_report": ReportDraft.model_validate(raw)}
