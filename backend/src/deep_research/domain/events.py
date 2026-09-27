from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EventType(StrEnum):
    """SSE研究流程事件类型枚举。"""
    RUN_STARTED = "run_started"
    CLARIFICATION_REQUIRED = "clarification_required"
    RESEARCH_BRIEF_CREATED = "research_brief_created"
    PLAN_CREATED = "plan_created"
    MEMORY_RECALLED = "memory_recalled"
    MEMORY_SAVED = "memory_saved"
    MEMORY_SAVE_FAILED = "memory_save_failed"
    TASK_STARTED = "task_started"
    SEARCH_STARTED = "search_started"
    SEARCH_COMPLETED = "search_completed"
    EVIDENCE_ADDED = "evidence_added"
    GAP_ASSESSED = "gap_assessed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    COVERAGE_ASSESSED = "coverage_assessed"
    ADDITIONAL_TASKS_CREATED = "additional_tasks_created"
    DRAFT_CREATED = "draft_created"
    REVIEW_COMPLETED = "review_completed"
    REVISION_STARTED = "revision_started"
    REPORT_FINALIZED = "report_finalized"
    RUN_CANCELLED = "run_cancelled"
    ERROR = "error"
    DONE = "done"


def _is_json_value(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, str)):
        return True
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False


class ResearchEvent(BaseModel, frozen=True):
    """Typed progress envelope emitted outside graph state."""

    type: EventType
    run_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("payload")
    @classmethod
    def require_json_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not _is_json_value(value):
            raise ValueError("payload must contain only JSON-compatible values")
        return value
