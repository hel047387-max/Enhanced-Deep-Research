import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from deep_research.domain.review import ReviewResult
from deep_research.llm import StructuredModel
from deep_research.prompts.review import review_prompt


async def review_report(
    state: dict[str, Any],
    model: StructuredModel,
) -> dict[str, ReviewResult]:
    """评估报告覆盖度、证据支撑和矛盾，并返回有界的评审动作。"""
    packet = {
        "draft": state["draft_report"].model_dump(mode="json"),
        "known_evidence_ids": sorted(state.get("evidence", {})),
        "task_statuses": {
            task_id: task.status for task_id, task in state.get("tasks", {}).items()
        },
    }
    raw = await model.ainvoke(
        [
            SystemMessage(content=review_prompt()),
            HumanMessage(content=json.dumps(packet, default=str)),
        ]
    )
    return {"review_result": ReviewResult.model_validate(raw)}
