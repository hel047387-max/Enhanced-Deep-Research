from datetime import UTC, datetime
from typing import get_args, get_type_hints

import pytest
from pydantic import ValidationError

from deep_research.domain.errors import ResearchError
from deep_research.domain.events import EventType, ResearchEvent
from deep_research.domain.plan import ResearchTask, TaskStatus
from deep_research.state.models import ResearchState
from deep_research.state.reducers import (
    append_errors,
    merge_evidence,
    merge_gap_assessments,
    merge_sources,
    merge_tasks,
)


def metadata(annotation):
    direct = getattr(annotation, "__metadata__", ())
    if direct:
        return direct
    args = get_args(annotation)
    return getattr(args[0], "__metadata__", ()) if args else ()


def task(task_id: str, status: TaskStatus) -> ResearchTask:
    return ResearchTask(
        task_id=task_id,
        title=task_id,
        objective="objective",
        completion_criteria=["criterion"],
        search_queries=["query"],
        status=status,
    )


def test_merge_tasks_updates_matching_ids_without_losing_parallel_results() -> None:
    existing = {"task-1": task("task-1", TaskStatus.RUNNING)}
    incoming = {
        "task-1": task("task-1", TaskStatus.COMPLETED),
        "task-2": task("task-2", TaskStatus.COMPLETED),
    }

    merged = merge_tasks(existing, incoming)

    assert merged["task-1"].status is TaskStatus.COMPLETED
    assert merged["task-2"].status is TaskStatus.COMPLETED
    assert existing["task-1"].status is TaskStatus.RUNNING
    assert merged is not existing


@pytest.mark.parametrize("merge", [merge_sources, merge_evidence, merge_gap_assessments])
def test_dictionary_reducers_accept_none_and_return_new_mapping(merge) -> None:
    value = object()

    merged = merge(None, {"id": value})

    assert merged == {"id": value}
    assert merged is not None


def test_append_errors_preserves_order_and_does_not_mutate_inputs() -> None:
    first = ResearchError(error_code="search_failed", stage="search", message="first")
    second = ResearchError(error_code="timeout", stage="search", message="second")
    left = [first]
    right = [second]

    merged = append_errors(left, right)

    assert merged == [first, second]
    assert merged is not left
    assert merged is not right
    assert left == [first]
    assert right == [second]


def test_research_error_is_immutable_and_validates_required_fields() -> None:
    error = ResearchError(
        error_code="search_failed",
        stage="search",
        message="provider unavailable",
        details={"attempt": 1, "retryable": True},
    )

    assert error.retryable is False
    assert error.attempt == 1
    with pytest.raises(ValidationError):
        error.message = "changed"
    with pytest.raises(ValidationError):
        ResearchError(error_code="", stage="search", message="bad")


def test_research_event_accepts_every_approved_event_type_and_serializes_json() -> None:
    expected = {
        "run_started",
        "clarification_required",
        "research_brief_created",
        "plan_created",
        "task_started",
        "search_started",
        "search_completed",
        "evidence_added",
        "gap_assessed",
        "task_completed",
        "task_failed",
        "coverage_assessed",
        "additional_tasks_created",
        "draft_created",
        "review_completed",
        "revision_started",
        "report_finalized",
        "run_cancelled",
        "error",
        "done",
    }

    assert {event_type.value for event_type in EventType} == expected
    event = ResearchEvent(
        type=EventType.RUN_STARTED,
        run_id="run-1",
        thread_id="thread-1",
        sequence=1,
        timestamp=datetime(2026, 8, 26, tzinfo=UTC),
        payload={"task_count": 3, "nested": [True, None, "ok"]},
    )

    assert event.model_dump(mode="json")["timestamp"].endswith("Z")
    assert event.model_dump(mode="json")["type"] == "run_started"


def test_research_event_requires_positive_sequence_and_utc_timestamp() -> None:
    base = {
        "type": EventType.DONE,
        "run_id": "run-1",
        "thread_id": "thread-1",
        "timestamp": datetime(2026, 8, 26, tzinfo=UTC),
        "payload": {},
    }

    with pytest.raises(ValidationError):
        ResearchEvent(sequence=0, **base)
    with pytest.raises(ValidationError):
        ResearchEvent(
            sequence=1,
            timestamp=datetime(2026, 8, 26, tzinfo=UTC).replace(tzinfo=None),
            **{key: value for key, value in base.items() if key != "timestamp"},
        )


def test_state_uses_langgraph_message_reducer_and_does_not_store_event_history_or_raw_pages() -> None:
    hints = get_type_hints(ResearchState, include_extras=True)
    messages_annotation = hints["messages"]

    assert metadata(messages_annotation)
    assert callable(metadata(messages_annotation)[0])
    assert "events" not in hints
    assert "raw_results" not in hints
    assert "raw_pages" not in hints
    assert "page_bodies" not in hints


def test_state_annotations_cover_normalized_parallel_collections_and_scalars() -> None:
    hints = get_type_hints(ResearchState, include_extras=True)

    for field, reducer in (
        ("tasks", merge_tasks),
        ("sources", merge_sources),
        ("evidence", merge_evidence),
        ("gap_assessments", merge_gap_assessments),
        ("errors", append_errors),
    ):
        assert reducer in metadata(hints[field])
    assert {
        "run_id",
        "thread_id",
        "clarification_count",
        "research_brief",
        "supervisor_added_tasks",
        "draft_report",
        "review_result",
        "review_action_count",
        "final_report",
        "status",
    } <= hints.keys()
