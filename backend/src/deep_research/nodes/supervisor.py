import json
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from deep_research.config import ResearchBudgets
from deep_research.domain.plan import CoverageDecision, ResearchTask, TaskStatus
from deep_research.llm import StructuredModel
from deep_research.nodes.researcher import ResearcherOutput
from deep_research.state.models import ResearchState

ResearcherRunner = Callable[[dict[str, object]], Awaitable[ResearcherOutput]]


class DispatchReservation(TypedDict):
    task_id: str
    query_budget: int
    total_queries: int


class SupervisorState(ResearchState, total=False):
    dispatch_batch: list[DispatchReservation]
    research_brief: Any


def prepare_dispatch_node(budgets: ResearchBudgets):
    async def prepare_dispatch(state: SupervisorState) -> dict[str, object]:
        """按并发限制和全局查询预算选择下一批待执行任务。"""
        pending = sorted(
            task_id
            for task_id, task in state.get("tasks", {}).items()
            if task.status is TaskStatus.PENDING
        )[: budgets.max_concurrent_researchers]
        remaining = max(
            0,
            budgets.max_total_search_queries - state.get("total_queries", 0),
        )
        maximum_per_task = (
            budgets.max_research_rounds * budgets.max_queries_per_round
        )
        reservations: list[DispatchReservation] = []
        for task_id in pending:
            grant = min(maximum_per_task, remaining)
            reservations.append(
                {
                    "task_id": task_id,
                    "query_budget": grant,
                    "total_queries": state.get("total_queries", 0),
                }
            )
            remaining -= grant
        return {"dispatch_batch": reservations}

    return prepare_dispatch


def research_task_node(researcher_runner: ResearcherRunner):
    async def research_task(state: dict[str, object]) -> dict[str, object]:
        """运行一个研究任务，并把结果合并回共享状态。"""
        output = await researcher_runner(state)
        task = output["updated_task"]
        gap = output["gap_assessment"]
        return {
            "tasks": {task.task_id: task},
            "sources": output["sources"],
            "evidence": output["evidence"],
            "gap_assessments": {gap.task_id: gap},
            "errors": output["errors"],
            "total_queries": output["queries_used"],
        }

    return research_task


def assess_coverage_node(
    coverage_model: StructuredModel,
    budgets: ResearchBudgets,
):
    async def assess_coverage(state: SupervisorState) -> dict[str, object]:
        """评估整体覆盖度，必要时生成针对明确缺口的补充任务。"""
        packet = {
            "brief": state["research_brief"].model_dump(),
            "tasks": {
                task_id: {
                    "status": task.status,
                    "completion_criteria": task.completion_criteria,
                }
                for task_id, task in state.get("tasks", {}).items()
            },
            "gap_assessments": {
                task_id: gap.model_dump()
                for task_id, gap in state.get("gap_assessments", {}).items()
            },
            "evidence_ids": sorted(state.get("evidence", {})),
        }
        raw = await coverage_model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "Assess global coverage once. Return CoverageDecision fields "
                        "sufficient, covered_dimensions, global_gaps, and additional_tasks. "
                        "Additional tasks must target explicit gaps and include parent_task_id "
                        "and gap_reason. Do not recreate the plan or provide hidden reasoning."
                    )
                ),
                HumanMessage(content=json.dumps(packet, default=str)),
            ]
        )
        raw_data = raw.model_dump() if isinstance(raw, BaseModel) else dict(raw)
        remaining = max(
            0,
            budgets.max_supervisor_tasks - state.get("supervisor_added_tasks", 0),
        )
        raw_data["additional_tasks"] = raw_data.get("additional_tasks", [])[:remaining]
        decision = CoverageDecision.model_validate(raw_data)
        accepted: list[ResearchTask] = []
        for task in decision.additional_tasks:
            if task.parent_task_id and task.gap_reason and task.gap_reason.strip():
                accepted.append(task.model_copy(update={"status": TaskStatus.PENDING}))
        return {
            "tasks": {task.task_id: task for task in accepted},
            "coverage_checked": True,
            "supervisor_added_tasks": state.get("supervisor_added_tasks", 0)
            + len(accepted),
            "dispatch_batch": [],
        }

    return assess_coverage
