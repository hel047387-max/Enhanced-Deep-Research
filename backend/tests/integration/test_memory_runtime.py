from dataclasses import replace

import pytest

from deep_research.graph.builder import build_research_graph
from deep_research.persistence.checkpoint import checkpoint_context
from deep_research.persistence.memory_store import MemoryStore
from deep_research.persistence.run_store import RunStatus, RunStore
from deep_research.services.cancellation import CancellationRegistry
from deep_research.services.event_stream import EventPublisher
from deep_research.services.runtime import ResearchRuntime
from tests.conftest import RuntimeHarness, RuntimePlannerModel, runtime_dependencies


class RecordingPlanner(RuntimePlannerModel):
    def __init__(self):
        self.prompts = []

    async def ainvoke(self, input):
        self.prompts.append(str(input[1].content))
        return await super().ainvoke(input)


@pytest.mark.asyncio
async def test_completed_research_is_archived_and_next_plan_sees_old_leads(tmp_path):
    database = tmp_path / "research.sqlite"
    store = RunStore(database)
    await store.initialize()
    memory = MemoryStore(database)
    await memory.initialize()
    publisher = EventPublisher()
    cancellation = CancellationRegistry()
    planner = RecordingPlanner()
    deps = replace(
        runtime_dependencies(publisher, cancellation),
        planner_model=planner,
        memory_store=memory,
    )
    async with checkpoint_context(database) as checkpointer:
        graph = build_research_graph(deps, checkpointer=checkpointer)
        runtime = ResearchRuntime(graph, store, publisher, cancellation, memory)
        harness = RuntimeHarness(runtime, store)
        try:
            first = await runtime.start("A complete scoped question")
            await harness.wait_until(first.run_id, RunStatus.COMPLETED)
            detail = await memory.get_archive(first.thread_id)
            assert detail is not None
            assert detail["report"]
            assert detail["evidence"]
            assert (await store.get_run(first.run_id)).memory_status == "saved"

            second = await runtime.start("A new scoped question")
            await harness.wait_until(second.run_id, RunStatus.COMPLETED)
            snapshot = await runtime.snapshot(second.thread_id)
            assert snapshot.memory_references[0]["thread_id"] == first.thread_id
            assert snapshot.memory_references[0]["summary"]
            assert "historical_research" in planner.prompts[-1]

            third = await runtime.start("Another question", use_memory=False)
            await harness.wait_until(third.run_id, RunStatus.COMPLETED)
            assert (await runtime.snapshot(third.thread_id)).memory_references == []
            assert (await memory.get_archive(third.thread_id)) is not None
        finally:
            await runtime.close()


class FailingMemoryStore:
    async def archive(self, thread_id, run_id, state):
        raise OSError("disk full")


@pytest.mark.asyncio
async def test_archive_failure_keeps_completed_report(tmp_path):
    database = tmp_path / "research.sqlite"
    store = RunStore(database)
    await store.initialize()
    publisher = EventPublisher()
    cancellation = CancellationRegistry()
    async with checkpoint_context(database) as checkpointer:
        graph = build_research_graph(
            runtime_dependencies(publisher, cancellation),
            checkpointer=checkpointer,
        )
        runtime = ResearchRuntime(graph, store, publisher, cancellation, FailingMemoryStore())
        harness = RuntimeHarness(runtime, store)
        try:
            handle = await runtime.start("A complete scoped question", use_memory=False)
            await harness.wait_until(handle.run_id, RunStatus.COMPLETED)
            snapshot = await runtime.snapshot(handle.thread_id)
            events = [event.type.value async for event in handle.events]
            assert snapshot.report
            assert snapshot.memory_status == "failed"
            assert "memory_save_failed" in events
            assert "done" in events
        finally:
            await runtime.close()


@pytest.mark.asyncio
async def test_startup_recovery_backfills_completed_run(tmp_path):
    database = tmp_path / "research.sqlite"
    store = RunStore(database)
    await store.initialize()
    publisher = EventPublisher()
    cancellation = CancellationRegistry()
    async with checkpoint_context(database) as checkpointer:
        graph = build_research_graph(
            runtime_dependencies(publisher, cancellation),
            checkpointer=checkpointer,
        )
        original = ResearchRuntime(graph, store, publisher, cancellation)
        harness = RuntimeHarness(original, store)
        handle = await original.start("A complete scoped question")
        await harness.wait_until(handle.run_id, RunStatus.COMPLETED)
        await original.close()

    memory = MemoryStore(database)
    await memory.initialize()
    new_publisher = EventPublisher()
    new_cancellation = CancellationRegistry()
    async with checkpoint_context(database) as checkpointer:
        graph = build_research_graph(
            replace(
                runtime_dependencies(new_publisher, new_cancellation),
                memory_store=memory,
            ),
            checkpointer=checkpointer,
        )
        runtime = ResearchRuntime(graph, store, new_publisher, new_cancellation, memory)
        try:
            await runtime.recover_archives()
            await runtime.recover_archives()
            assert len(await memory.list_archives()) == 1
            assert (await store.get_run(handle.run_id)).memory_status == "saved"
        finally:
            await runtime.close()


@pytest.mark.asyncio
async def test_run_store_migrates_existing_metadata_table(tmp_path):
    import sqlite3

    database = tmp_path / "legacy.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE research_runs (
                run_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                cancelled_at TEXT, last_error TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO research_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("run-1", "thread-1", "completed", "2026-01-01T00:00:00+00:00",
             "2026-01-01T00:00:00+00:00", None, None),
        )

    store = RunStore(database)
    await store.initialize()
    assert (await store.get_run("run-1")).memory_status is None
    await store.update_memory_status("run-1", "saved")
    assert (await store.get_run("run-1")).memory_status == "saved"


class FailingRecallStore(MemoryStore):
    async def recall(self, brief):
        raise OSError("memory index unavailable")


@pytest.mark.asyncio
async def test_recall_failure_is_visible_but_research_completes(tmp_path):
    database = tmp_path / "research.sqlite"
    store = RunStore(database)
    await store.initialize()
    memory = FailingRecallStore(database)
    await memory.initialize()
    publisher = EventPublisher()
    cancellation = CancellationRegistry()
    async with checkpoint_context(database) as checkpointer:
        graph = build_research_graph(
            replace(
                runtime_dependencies(publisher, cancellation),
                memory_store=memory,
            ),
            checkpointer=checkpointer,
        )
        runtime = ResearchRuntime(graph, store, publisher, cancellation, memory)
        harness = RuntimeHarness(runtime, store)
        try:
            handle = await runtime.start("A complete scoped question")
            await harness.wait_until(handle.run_id, RunStatus.COMPLETED)
            snapshot = await runtime.snapshot(handle.thread_id)
            assert snapshot.report
            assert snapshot.memory_warning is not None
            assert snapshot.memory_references == []
            assert snapshot.memory_status == "saved"
        finally:
            await runtime.close()
