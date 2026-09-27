import json
from copy import deepcopy
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from deep_research.config import ResearchBudgets
from deep_research.domain.plan import (
    ResearchBrief,
    ResearchPlan,
    ResearchTask,
    TaskStatus,
)
from deep_research.llm import StructuredModel
from deep_research.prompts.planning import planning_prompt


#校验大模型的输出并进行归一化处理
def _normalize_plan(raw: Any, *, max_queries: int) -> Any:
    if isinstance(raw, BaseModel):
        payload = raw.model_dump() # 如果 raw 是 Pydantic 模型，就把它转换成普通字典
    elif isinstance(raw, dict):
        payload = deepcopy(raw)
    else:
        return raw

    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        return payload#不继续处理任务，直接返回当前

    normalized_tasks: list[Any] = []
    used_ids: set[str] = set()
    for index, item in enumerate(tasks[:5]):
        if not isinstance(item, dict):
            normalized_tasks.append(item)
            continue
        task = dict(item)
        queries = task.get("search_queries")
        if isinstance(queries, list):
            task["search_queries"] = queries[:max_queries]

        base_id = str(task.get("task_id") or f"task-{index + 1}")
        candidate = base_id
        suffix = 2
        while candidate in used_ids:
            candidate = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(candidate)
        task["task_id"] = candidate

        task["status"] = TaskStatus.PENDING.value
        task["current_round"] = 0
        task["parent_task_id"] = None
        task["gap_reason"] = None
        task["error"] = None
        normalized_tasks.append(task)

    payload["tasks"] = normalized_tasks
    return payload

# 作用：根据 research_brief 生成正式的 ResearchPlan
async def plan_research(
    state: dict[str, Any],
    model: StructuredModel,
    budgets: ResearchBudgets | None = None,
) -> dict[str, dict[str, ResearchTask]]:
    """把研究简报转换为经过预算归一化和校验的任务映射。"""
    brief = ResearchBrief.model_validate(state["research_brief"])
    resolved_budgets = budgets or ResearchBudgets()
    messages = [
        SystemMessage(content=planning_prompt(brief.source_preferences)),
        HumanMessage(content=(
            json.dumps(
                {"brief": brief.model_dump(mode="json"),
                 "historical_research": state["memory_context"]},
                ensure_ascii=False,
            )
            if state.get("memory_context", {}).get("researches")
            else brief.model_dump_json()
        )),
    ]
    plan: ResearchPlan | None = None
    for attempt in range(2):
        raw = await model.ainvoke(messages)
        normalized = _normalize_plan(
            raw,
            max_queries=resolved_budgets.max_queries_per_round,
        )
        try:
            plan = ResearchPlan.model_validate(normalized)
            break
        except ValidationError as exc:
            if attempt == 1:
                raise
            messages = [
                *messages,# 保留之前所有消息
                HumanMessage(
                    content=(
                        "Correct the previous ResearchPlan and return the complete "
                        "structure again. Validation error: "
                        f"{exc}. Previous output: "
                        f"{json.dumps(normalized, ensure_ascii=False, default=str)}"
                    )
                ),
            ]

    if plan is None:
        raise AssertionError("research plan repair loop exhausted")
    maximum = resolved_budgets.max_initial_tasks
    return {"tasks": {task.task_id: task for task in plan.tasks[:maximum]}}
