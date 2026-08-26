# API, Streaming, and Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the approved research graph through one resumable FastAPI/SSE execution path backed by SQLite checkpoints, typed run metadata, and cooperative cancellation.

**Architecture:** `thread_id` addresses LangGraph conversation state while `run_id` addresses one stream execution. FastAPI adapts HTTP requests to an injected ResearchRuntime; SQLite owns committed checkpoints and run metadata, and an async EventPublisher streams typed events without entering Graph State.

**Tech Stack:** FastAPI, Uvicorn, LangGraph SQLite checkpointer, aiosqlite, Pydantic 2, HTTPX, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-08-26-deep-research-agent-design.md`

## Global Constraints

- Complete the foundation and Agent workflow plans first.
- Initial and resumed research use the same graph/runtime; no duplicate synchronous workflow.
- Checkpoint key is `thread_id`; each execution attempt has a new `run_id`.
- Clarification closes the current stream with status `waiting_for_user` and resumes through LangGraph `Command(resume=answer)`.
- SSE events share the approved envelope and never expose chain-of-thought, secrets, or raw pages.
- MVP has no SSE history replay and supports one FastAPI instance.
- Cancellation is cooperative and checked at node boundaries.
- Checkpoint write failure is fatal; partial task failures are not.

---

## File map

- `backend/src/deep_research/persistence/checkpoint.py`: SQLite checkpointer lifecycle.
- `backend/src/deep_research/persistence/run_store.py`: run metadata repository.
- `backend/src/deep_research/services/event_stream.py`: async event publisher/subscriber.
- `backend/src/deep_research/services/cancellation.py`: per-thread cancellation registry.
- `backend/src/deep_research/services/runtime.py`: one graph execution/resume adapter.
- `backend/src/deep_research/api/schemas.py`: HTTP request, snapshot, and error schemas.
- `backend/src/deep_research/api/routes.py`: endpoints and SSE encoding.
- `backend/src/deep_research/api/main.py`: FastAPI lifecycle and dependency wiring.
- `backend/tests/conftest.py`: runtime, HTTP client, and restart fixtures backed by temporary SQLite files.
- `backend/tests/integration/`: SQLite, runtime, SSE, resume, and cancellation tests.

### Task 1: SQLite checkpoint and run metadata

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/deep_research/persistence/checkpoint.py`
- Create: `backend/src/deep_research/persistence/run_store.py`
- Create: `backend/tests/integration/test_persistence.py`

**Interfaces:**
- Consumes: SQLite path, thread ID, run ID, status, and sanitized error.
- Produces: `checkpoint_context(path)`, `RunStore.create_run`, `RunStore.update_status`, `RunStore.get_run`, and `RunStore.get_latest_for_thread`.

- [ ] **Step 1: Write failing persistence tests with a temporary database**

```python
from pathlib import Path

import pytest

from deep_research.persistence.run_store import RunStatus, RunStore


@pytest.mark.asyncio
async def test_run_store_persists_status_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "research.sqlite"
    first = RunStore(db)
    await first.initialize()
    await first.create_run("run-1", "thread-1")
    await first.update_status("run-1", RunStatus.WAITING_FOR_USER)
    second = RunStore(db)
    await second.initialize()
    restored = await second.get_run("run-1")
    assert restored is not None
    assert restored.status is RunStatus.WAITING_FOR_USER


@pytest.mark.asyncio
async def test_latest_run_is_selected_by_updated_time(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "research.sqlite")
    await store.initialize()
    await store.create_run("run-1", "thread-1")
    await store.create_run("run-2", "thread-1")
    assert (await store.get_latest_for_thread("thread-1")).run_id == "run-2"
```

- [ ] **Step 2: Run tests to verify repositories are absent**

Run: `cd backend && pytest tests/integration/test_persistence.py -v`

Expected: FAIL because RunStore is not implemented.

- [ ] **Step 3: Implement schema initialization and checkpointer lifecycle**

Add runtime dependencies `fastapi>=0.115`, `uvicorn[standard]>=0.32`, `langgraph-checkpoint-sqlite>=2.0`, and `aiosqlite>=0.20`, plus test dependency `httpx>=0.27`.

Use `aiosqlite` with an explicit table:

```sql
CREATE TABLE IF NOT EXISTS research_runs (
    run_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    cancelled_at TEXT,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_runs_thread_updated
ON research_runs(thread_id, updated_at DESC);
```

Define `RunStatus` values `created`, `running`, `waiting_for_user`, `completed`, `failed`, and `cancelled`. Use UTC ISO-8601 timestamps. Implement an async context manager that creates the LangGraph SQLite saver, runs its setup, yields it, and closes its connection during FastAPI shutdown.

- [ ] **Step 4: Run persistence tests**

Run: `cd backend && pytest tests/integration/test_persistence.py -v`

Expected: PASS and only temporary SQLite files are created.

- [ ] **Step 5: Commit persistence adapters**

```bash
git add backend/pyproject.toml backend/src/deep_research/persistence backend/tests/integration/test_persistence.py
git commit -m "feat: persist checkpoints and run metadata"
```

### Task 2: EventPublisher and cancellation registry

**Files:**
- Modify: `backend/src/deep_research/services/event_stream.py`
- Create: `backend/src/deep_research/services/cancellation.py`
- Create: `backend/tests/unit/test_event_stream.py`
- Create: `backend/tests/unit/test_cancellation.py`

**Interfaces:**
- Consumes: thread/run IDs and event payloads.
- Produces: `EventPublisher.open_run`, `EventPublisher.publish`, `EventPublisher.subscribe`, `EventPublisher.close`, `CancellationRegistry.cancel`, and `CancellationRegistry.raise_if_cancelled`.

- [ ] **Step 1: Write failing monotonic-sequence and cancellation tests**

```python
import pytest

from deep_research.domain.events import EventType
from deep_research.services.cancellation import CancellationRegistry, ResearchCancelled
from deep_research.services.event_stream import EventPublisher


@pytest.mark.asyncio
async def test_events_have_monotonic_sequence_per_run() -> None:
    publisher = EventPublisher()
    subscription = publisher.subscribe("run-1")
    await publisher.publish(EventType.RUN_STARTED, "run-1", "thread-1", {})
    await publisher.publish(EventType.PLAN_CREATED, "run-1", "thread-1", {"task_count": 3})
    first = await anext(subscription)
    second = await anext(subscription)
    assert [first.sequence, second.sequence] == [1, 2]


def test_cancelled_thread_raises_at_boundary() -> None:
    registry = CancellationRegistry()
    registry.cancel("thread-1")
    with pytest.raises(ResearchCancelled):
        registry.raise_if_cancelled("thread-1")
```

- [ ] **Step 2: Run tests to establish the missing services**

Run: `cd backend && pytest tests/unit/test_event_stream.py tests/unit/test_cancellation.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement bounded queues and cooperative cancellation**

`open_run(run_id)` creates exactly one `asyncio.Queue[ResearchEvent | None]` and sequence counter before execution starts. `subscribe(run_id)` attaches to that pre-opened queue, so `run_started` cannot race ahead of the HTTP response; reject missing or already-subscribed run IDs. `None` is the internal close sentinel and the iterator removes the queue in `finally`. Limit queues to 256 items; if a client cannot keep up, replace the oldest queued item with one sanitized error event and the close sentinel rather than blocking the graph.

CancellationRegistry stores cancelled thread IDs under an `asyncio.Lock`; `clear(thread_id)` is called only for a new initial thread, not for resume of a cancelled thread.

- [ ] **Step 4: Run event and cancellation tests**

Run: `cd backend && pytest tests/unit/test_event_stream.py tests/unit/test_cancellation.py -v`

Expected: PASS.

- [ ] **Step 5: Commit runtime signaling services**

```bash
git add backend/src/deep_research/services/event_stream.py backend/src/deep_research/services/cancellation.py backend/tests/unit/test_event_stream.py backend/tests/unit/test_cancellation.py
git commit -m "feat: add research events and cancellation"
```

### Task 3: ResearchRuntime for initial run and resume

**Files:**
- Create: `backend/src/deep_research/services/runtime.py`
- Modify: `backend/src/deep_research/graph/builder.py`
- Create: `backend/tests/integration/test_runtime.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: compiled graph, RunStore, EventPublisher, CancellationRegistry, initial query or resume answer.
- Produces: `ResearchRuntime.start(query: str) -> RunHandle`, `resume(thread_id: str, answer: str) -> RunHandle`, `snapshot(thread_id: str) -> ResearchSnapshot`, and `cancel(thread_id: str) -> None`; `RunHandle` contains `run_id`, `thread_id`, and the already-opened `events: AsyncIterator[ResearchEvent]`.

- [ ] **Step 1: Write failing initial, interrupt, and resume tests**

```python
@pytest.mark.asyncio
async def test_runtime_creates_distinct_run_ids_for_resume(runtime_harness) -> None:
    initial = await runtime_harness.runtime.start("Research market growth")
    await runtime_harness.wait_until(initial.run_id, "waiting_for_user")
    resumed = await runtime_harness.runtime.resume(initial.thread_id, "Use 2024-2026")
    assert resumed.thread_id == initial.thread_id
    assert resumed.run_id != initial.run_id
    await runtime_harness.wait_until(resumed.run_id, "completed")


@pytest.mark.asyncio
async def test_resume_rejects_non_waiting_thread(runtime_harness) -> None:
    handle = await runtime_harness.runtime.start("A complete question with scope")
    await runtime_harness.wait_until(handle.run_id, "completed")
    with pytest.raises(InvalidResumeState):
        await runtime_harness.runtime.resume(handle.thread_id, "late answer")
```

- [ ] **Step 2: Run tests to verify runtime is absent**

Run: `cd backend && pytest tests/integration/test_runtime.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement one execution path**

`start` creates UUIDv4 IDs, stores `created`, calls `EventPublisher.open_run(run_id)`, obtains the iterator for `RunHandle.events`, and only then launches one background asyncio task. It invokes the graph with `config={"configurable": {"thread_id": thread_id}, "max_concurrency": 3}`. `resume` validates the latest run status, creates and opens a new run ID the same way, and invokes `Command(resume=answer)` with the same thread ID. Both call a private `_execute(handle, graph_input)` method so status/error/event behavior cannot diverge.

On normal interrupt, store `waiting_for_user` and emit `clarification_required` followed by `done`. On graph completion, store `completed`, emit `report_finalized`, then `done`. On cancellation or exception, store the corresponding terminal status and emit sanitized terminal events.

Define `RuntimeHarness` in `tests/conftest.py` with field `runtime: ResearchRuntime`, async `wait_until(run_id: str, status: str) -> RunMetadata`, and a temporary SQLite database shared by RunStore and checkpointer. Its graph uses the real builder with scripted Clarifier/Planner/Writer/Reviewer models and FakeSearchProvider; the fixture closes runtime tasks and database resources after every test.

- [ ] **Step 4: Run runtime integration tests**

Run: `cd backend && pytest tests/integration/test_runtime.py -v`

Expected: PASS.

- [ ] **Step 5: Commit resumable runtime**

```bash
git add backend/src/deep_research/services/runtime.py backend/src/deep_research/graph/builder.py backend/tests/integration/test_runtime.py
git commit -m "feat: add resumable research runtime"
```

### Task 4: FastAPI schemas, SSE endpoints, and lifecycle

**Files:**
- Modify: `backend/src/deep_research/api/schemas.py`
- Modify: `backend/src/deep_research/api/routes.py`
- Modify: `backend/src/deep_research/api/main.py`
- Create: `backend/tests/integration/test_api.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: ResearchRuntime dependency.
- Produces: approved `/api/v1/research` endpoints, SSE encoder, snapshot response, report response, cancellation response, and health response.

- [ ] **Step 1: Write failing API contract tests**

```python
import json

import pytest


@pytest.mark.asyncio
async def test_stream_starts_with_valid_envelope(async_client) -> None:
    async with async_client.stream("POST", "/api/v1/research/stream", json={"query": "Complete scoped question"}) as response:
        assert response.status_code == 200
        line = await anext(response.aiter_lines())
        assert line.startswith("data: ")
        event = json.loads(line.removeprefix("data: "))
        assert event["type"] == "run_started"
        assert event["run_id"]
        assert event["thread_id"]
        assert event["sequence"] == 1


@pytest.mark.asyncio
async def test_cancel_endpoint_is_idempotent(async_client, running_thread_id) -> None:
    first = await async_client.post(f"/api/v1/research/{running_thread_id}/cancel")
    second = await async_client.post(f"/api/v1/research/{running_thread_id}/cancel")
    assert first.status_code == 202
    assert second.status_code == 202
```

- [ ] **Step 2: Run API tests**

Run: `cd backend && pytest tests/integration/test_api.py -v`

Expected: FAIL because the application has no routes.

- [ ] **Step 3: Implement schemas and one router**

Define `ResearchStartRequest(query: str)`, `ResearchResumeRequest(answer: str)`, `ResearchSnapshotResponse`, `ReportResponse`, and `ErrorResponse`. Reject empty strings and cap query/answer length at 10,000 characters. The stream routes iterate `RunHandle.events` returned by `start`/`resume`; they never subscribe after launching execution. Encode SSE as `data: {json}\n\n` with UTF-8 JSON and `Cache-Control: no-cache`, `Connection: keep-alive`, and `X-Accel-Buffering: no`.

Use FastAPI lifespan to initialize RunStore/checkpointer/runtime and close resources. Configure CORS from the parsed allowlist; never use wildcard origins with credentials.

Add `async_client() -> AsyncIterator[httpx.AsyncClient]` using `ASGITransport(app=create_app(test_runtime))`, and `running_thread_id() -> str` that starts a scripted blocking run and waits until RunStore reports `running`. Teardown cancels the run and closes the client.

- [ ] **Step 4: Run API, runtime, and persistence tests**

Run: `cd backend && pytest tests/integration/test_persistence.py tests/integration/test_runtime.py tests/integration/test_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the HTTP/SSE surface**

```bash
git add backend/src/deep_research/api backend/tests/integration/test_api.py
git commit -m "feat: expose resumable research SSE API"
```

### Task 5: Restart recovery and terminal failure behavior

**Files:**
- Modify: `backend/tests/integration/test_runtime.py`
- Modify: `backend/tests/integration/test_api.py`
- Modify: `backend/src/deep_research/services/runtime.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: committed checkpoint and persisted RunMetadata after a runtime instance is replaced.
- Produces: restart-safe snapshot/resume behavior and sanitized fatal error events.

- [ ] **Step 1: Add failing restart and checkpoint-error tests**

```python
@pytest.mark.asyncio
async def test_new_runtime_resumes_waiting_checkpoint(shared_database_runtime_factory) -> None:
    first = await shared_database_runtime_factory()
    handle = await first.start("Ambiguous topic")
    await first.wait_until(handle.run_id, "waiting_for_user")
    second = await shared_database_runtime_factory()
    resumed = await second.resume(handle.thread_id, "Scope is the EU market in 2025")
    await second.wait_until(resumed.run_id, "completed")
    assert (await second.snapshot(handle.thread_id)).status == "completed"


@pytest.mark.asyncio
async def test_checkpoint_failure_is_fatal_and_sanitized(runtime_with_failing_checkpointer) -> None:
    handle = await runtime_with_failing_checkpointer.start("Complete question")
    terminal = await runtime_with_failing_checkpointer.terminal_event(handle.run_id)
    assert terminal.type.value == "error"
    assert "api_key" not in str(terminal.payload).lower()
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run: `cd backend && pytest tests/integration/test_runtime.py -k 'resumes_waiting or checkpoint_failure' -v`

Expected: FAIL until restart lookup and fatal persistence handling are complete.

- [ ] **Step 3: Implement restart lookup and fatal persistence boundary**

On runtime creation, do not automatically restart `running` jobs. Snapshot reports their last committed state. Resume is valid only for `waiting_for_user`; a future recovery feature may address abandoned running jobs. Wrap checkpoint errors as `ResearchError(stage="checkpoint", retryable=False)`, mark the run failed, and sanitize payloads through one error serializer.

Add `shared_database_runtime_factory() -> Awaitable[ResearchRuntimeHarness]` that constructs independently owned runtimes against the same temporary database path, and `runtime_with_failing_checkpointer` using a checkpointer whose async write method raises `OSError("checkpoint unavailable")`. Each created runtime is registered for teardown.

- [ ] **Step 4: Run the complete API/persistence suite**

Run: `cd backend && pytest tests/unit/test_event_stream.py tests/unit/test_cancellation.py tests/integration/test_persistence.py tests/integration/test_runtime.py tests/integration/test_api.py -q && ruff check src tests`

Expected: PASS.

- [ ] **Step 5: Commit recovery behavior**

```bash
git add backend/src/deep_research/services/runtime.py backend/tests/integration/test_runtime.py backend/tests/integration/test_api.py
git commit -m "test: verify checkpoint recovery and failures"
```

## Plan completion gate

Run:

```bash
cd backend
pytest tests/unit tests/integration -q
ruff check src tests
```

Expected: the complete fake-backed backend passes, SQLite restart tests pass, and the API exposes only the single resumable SSE workflow. Do not begin frontend work until this gate passes.
