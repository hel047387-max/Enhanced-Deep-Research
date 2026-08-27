import json

import pytest

from deep_research.domain.events import EventType
from deep_research.persistence.run_store import RunStatus
from deep_research.services.runtime import InvalidResumeState


@pytest.mark.asyncio
async def test_runtime_creates_distinct_run_ids_for_resume(runtime_harness) -> None:
    initial = await runtime_harness.runtime.start("Ambiguous topic")
    initial_events = [event async for event in initial.events]
    await runtime_harness.wait_until(initial.run_id, RunStatus.WAITING_FOR_USER)

    resumed = await runtime_harness.runtime.resume(
        initial.thread_id,
        "Use the EU market in 2024-2026",
    )
    resumed_events = [event async for event in resumed.events]
    await runtime_harness.wait_until(resumed.run_id, RunStatus.COMPLETED)

    assert resumed.thread_id == initial.thread_id
    assert resumed.run_id != initial.run_id
    assert initial_events[0].type is EventType.RUN_STARTED
    assert initial_events[-1].type is EventType.DONE
    assert [event.type for event in initial_events].count(
        EventType.CLARIFICATION_REQUIRED
    ) == 1
    assert resumed_events[0].type is EventType.RUN_STARTED
    assert resumed_events[-2].type is EventType.REPORT_FINALIZED
    assert resumed_events[-1].type is EventType.DONE


@pytest.mark.asyncio
async def test_resume_rejects_non_waiting_thread(runtime_harness) -> None:
    handle = await runtime_harness.runtime.start("A complete question with scope")
    await runtime_harness.wait_until(handle.run_id, RunStatus.COMPLETED)

    with pytest.raises(InvalidResumeState):
        await runtime_harness.runtime.resume(handle.thread_id, "late answer")


@pytest.mark.asyncio
async def test_snapshot_reads_committed_graph_projection(runtime_harness) -> None:
    handle = await runtime_harness.runtime.start("A complete question with scope")
    await runtime_harness.wait_until(handle.run_id, RunStatus.COMPLETED)

    snapshot = await runtime_harness.runtime.snapshot(handle.thread_id)

    assert snapshot.run_id == handle.run_id
    assert snapshot.thread_id == handle.thread_id
    assert snapshot.status is RunStatus.COMPLETED
    assert snapshot.report is not None
    assert snapshot.tasks


@pytest.mark.asyncio
async def test_new_runtime_resumes_waiting_checkpoint(
    shared_database_runtime_factory,
) -> None:
    first = await shared_database_runtime_factory()
    handle = await first.runtime.start("Ambiguous topic")
    await first.wait_until(handle.run_id, RunStatus.WAITING_FOR_USER)

    second = await shared_database_runtime_factory()
    resumed = await second.runtime.resume(
        handle.thread_id,
        "Scope is the EU market in 2025",
    )
    await second.wait_until(resumed.run_id, RunStatus.COMPLETED)
    snapshot = await second.runtime.snapshot(handle.thread_id)

    assert snapshot.status is RunStatus.COMPLETED
    assert resumed.thread_id == handle.thread_id
    assert resumed.run_id != handle.run_id


@pytest.mark.asyncio
async def test_new_runtime_does_not_auto_restart_running_metadata(
    shared_database_runtime_factory,
) -> None:
    first = await shared_database_runtime_factory()
    await first.store.create_run("run-abandoned", "thread-abandoned")
    await first.store.update_status("run-abandoned", RunStatus.RUNNING)

    second = await shared_database_runtime_factory()
    snapshot = await second.runtime.snapshot("thread-abandoned")

    assert snapshot.run_id == "run-abandoned"
    assert snapshot.status is RunStatus.RUNNING
    assert snapshot.tasks == {}


@pytest.mark.asyncio
async def test_checkpoint_failure_is_fatal_and_sanitized(
    runtime_with_failing_checkpointer,
) -> None:
    handle = await runtime_with_failing_checkpointer.runtime.start(
        "A complete question with api_key=TOP_SECRET"
    )
    events = [event async for event in handle.events]
    metadata = await runtime_with_failing_checkpointer.wait_until(
        handle.run_id,
        RunStatus.FAILED,
    )
    terminal = next(event for event in events if event.type is EventType.ERROR)

    assert terminal.payload["stage"] == "checkpoint"
    assert terminal.payload["retryable"] is False
    assert "api_key" not in json.dumps(terminal.payload).lower()
    assert metadata.last_error == "Research checkpoint persistence failed."
