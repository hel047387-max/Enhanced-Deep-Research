import asyncio
import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from deep_research.domain.events import EventType
from deep_research.graph.builder import build_research_graph
from deep_research.persistence.checkpoint import checkpoint_context
from deep_research.persistence.run_store import RunStatus, RunStore
from deep_research.services.cancellation import CancellationRegistry
from deep_research.services.event_stream import EventPublisher
from deep_research.services.runtime import InvalidResumeState, ResearchRuntime
from tests.conftest import runtime_dependencies

_CONTRACT = Path(__file__).parents[3] / "contracts" / "research-event-sequence.json"


def _shape(value):
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value)


class _BlockingSearch:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def search(self, query: str, max_results: int):
        self.started.set()
        await self.release.wait()
        return []


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
async def test_runtime_emits_shared_projection_contract(runtime_harness) -> None:
    expected = {
        event["type"]: event["payload"]
        for event in json.loads(_CONTRACT.read_text(encoding="utf-8"))
    }
    handle = await runtime_harness.runtime.start("A complete question with scope")
    events = [event async for event in handle.events]
    await runtime_harness.wait_until(handle.run_id, RunStatus.COMPLETED)
    actual = {event.type.value: event.payload for event in events}

    for event_type in (
        "research_brief_created",
        "plan_created",
        "evidence_added",
        "review_completed",
        "report_finalized",
    ):
        assert _shape(actual[event_type]) == _shape(expected[event_type])
    assert "raw_content" not in json.dumps(actual)
    assert "page_body" not in json.dumps(actual)


@pytest.mark.asyncio
async def test_completed_runtime_removes_stream_registry_entry(runtime_harness) -> None:
    handle = await runtime_harness.runtime.start("A complete question with scope")
    await runtime_harness.wait_until(handle.run_id, RunStatus.COMPLETED)

    assert handle.run_id not in runtime_harness.runtime._streams


@pytest.mark.asyncio
async def test_disconnect_during_search_does_not_prevent_cancellation(tmp_path) -> None:
    database = tmp_path / "disconnect.sqlite"
    store = RunStore(database)
    await store.initialize()
    publisher = EventPublisher()
    cancellation = CancellationRegistry()
    search = _BlockingSearch()
    async with checkpoint_context(database) as checkpointer:
        dependencies = replace(
            runtime_dependencies(publisher, cancellation),
            search_provider=search,
        )
        runtime = ResearchRuntime(
            build_research_graph(dependencies, checkpointer=checkpointer),
            store,
            publisher,
            cancellation,
        )
        handle = await runtime.start("A complete question with scope")
        await anext(handle.events)
        await handle.events.aclose()
        await asyncio.wait_for(search.started.wait(), timeout=2)

        await runtime.cancel(handle.thread_id)
        search.release.set()

        async def cancelled():
            while True:
                metadata = await store.get_run(handle.run_id)
                if metadata is not None and metadata.status is RunStatus.CANCELLED:
                    return
                await asyncio.sleep(0.01)

        await asyncio.wait_for(cancelled(), timeout=2)
        await runtime.close()


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


@pytest.mark.asyncio
async def test_runtime_logs_internal_execution_exception(
    tmp_path, caplog
) -> None:
    class FailingGraph:
        async def ainvoke(self, *_args, **_kwargs):
            raise RuntimeError("provider exploded")

    database = tmp_path / "runtime-error.sqlite"
    store = RunStore(database)
    await store.initialize()
    runtime = ResearchRuntime(
        FailingGraph(),
        store,
        EventPublisher(),
        CancellationRegistry(),
    )

    with caplog.at_level(logging.ERROR, logger="deep_research.services.runtime"):
        handle = await runtime.start("A complete question")
        async for _event in handle.events:
            pass
        metadata = await store.get_run(handle.run_id)

    await runtime.close()
    assert metadata is not None
    assert metadata.status is RunStatus.FAILED
    assert "Research execution failed" in caplog.text
    assert "provider exploded" in caplog.text
