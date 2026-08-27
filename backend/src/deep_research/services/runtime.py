from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel, Field

from deep_research.domain.errors import ResearchError
from deep_research.domain.events import EventType, ResearchEvent
from deep_research.domain.evidence import EvidenceItem, Source
from deep_research.domain.plan import ResearchBrief, ResearchTask
from deep_research.domain.review import ReviewResult
from deep_research.persistence.run_store import RunStatus, RunStore
from deep_research.services.cancellation import (
    CancellationRegistry,
    ResearchCancelled,
)
from deep_research.services.event_stream import EventPublisher


class InvalidResumeState(ValueError):
    """Raised when a thread has no waiting checkpoint to resume."""


class ResearchThreadNotFound(LookupError):
    """Raised when a thread has no persisted run metadata."""


@dataclass(frozen=True)
class _ExecutionIdentity:
    run_id: str
    thread_id: str


_CURRENT_EXECUTION: ContextVar[_ExecutionIdentity | None] = ContextVar(
    "research_execution",
    default=None,
)


class RuntimeEventSink:
    """Graph event sink bound to the current runtime task through context vars."""

    def __init__(self, publisher: EventPublisher) -> None:
        self._publisher = publisher

    async def emit(self, event_type: str, payload: dict[str, object]) -> None:
        identity = _CURRENT_EXECUTION.get()
        if identity is None:
            raise RuntimeError("graph event emitted outside a research execution")
        await self._publisher.publish(
            EventType(event_type),
            identity.run_id,
            identity.thread_id,
            payload,
        )


class RuntimeCancellationChecker:
    """Graph cancellation checker bound to the current runtime task."""

    def __init__(self, registry: CancellationRegistry) -> None:
        self._registry = registry

    def raise_if_cancelled(self) -> None:
        identity = _CURRENT_EXECUTION.get()
        if identity is None:
            raise RuntimeError("cancellation checked outside a research execution")
        self._registry.raise_if_cancelled(identity.thread_id)


@dataclass(frozen=True)
class RunHandle:
    run_id: str
    thread_id: str
    events: AsyncIterator[ResearchEvent]


class ResearchSnapshot(BaseModel, frozen=True):
    run_id: str
    thread_id: str
    status: RunStatus
    clarification: str | None = None
    research_brief: ResearchBrief | None = None
    tasks: dict[str, ResearchTask] = Field(default_factory=dict)
    sources: dict[str, Source] = Field(default_factory=dict)
    evidence: dict[str, EvidenceItem] = Field(default_factory=dict)
    review: ReviewResult | None = None
    report: str | None = None
    errors: list[ResearchError] = Field(default_factory=list)


def _initial_state(run_id: str, thread_id: str, query: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "messages": [query],
        "clarification_count": 0,
        "tasks": {},
        "sources": {},
        "evidence": {},
        "gap_assessments": {},
        "supervisor_added_tasks": 0,
        "coverage_checked": False,
        "total_queries": 0,
        "review_action_count": 0,
        "errors": [],
        "status": RunStatus.CREATED.value,
    }


def serialize_error(error: ResearchError) -> dict[str, object]:
    """Return the one public, JSON-safe representation for terminal errors."""

    return error.model_dump(mode="json")


class ResearchRuntime:
    """Single execution adapter shared by initial and resumed research runs."""

    def __init__(
        self,
        graph: CompiledStateGraph,
        run_store: RunStore,
        publisher: EventPublisher,
        cancellation: CancellationRegistry,
    ) -> None:
        self._graph = graph
        self._run_store = run_store
        self._publisher = publisher
        self._cancellation = cancellation
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._streams: dict[str, AsyncIterator[ResearchEvent]] = {}

    async def start(self, query: str) -> RunHandle:
        thread_id = str(uuid4())
        run_id = str(uuid4())
        self._cancellation.clear(thread_id)
        await self._run_store.create_run(run_id, thread_id)
        return self._launch(run_id, thread_id, _initial_state(run_id, thread_id, query))

    async def resume(self, thread_id: str, answer: str) -> RunHandle:
        latest = await self._run_store.get_latest_for_thread(thread_id)
        if latest is None:
            raise ResearchThreadNotFound(thread_id)
        if latest.status is not RunStatus.WAITING_FOR_USER:
            raise InvalidResumeState(
                f"thread {thread_id} is {latest.status.value}, not waiting_for_user"
            )
        run_id = str(uuid4())
        await self._run_store.create_run(run_id, thread_id)
        graph_input = Command(resume=answer, update={"run_id": run_id})
        return self._launch(run_id, thread_id, graph_input)

    async def snapshot(self, thread_id: str) -> ResearchSnapshot:
        latest = await self._run_store.get_latest_for_thread(thread_id)
        if latest is None:
            raise ResearchThreadNotFound(thread_id)
        graph_snapshot = await self._graph.aget_state(self._config(thread_id))
        values: Mapping[str, Any] = graph_snapshot.values or {}
        return ResearchSnapshot(
            run_id=latest.run_id,
            thread_id=thread_id,
            status=latest.status,
            clarification=values.get("interrupt_question"),
            research_brief=values.get("research_brief"),
            tasks=values.get("tasks", {}),
            sources=values.get("sources", {}),
            evidence=values.get("evidence", {}),
            review=values.get("review_result"),
            report=values.get("final_report"),
            errors=values.get("errors", []),
        )

    async def cancel(self, thread_id: str) -> None:
        latest = await self._run_store.get_latest_for_thread(thread_id)
        if latest is None:
            raise ResearchThreadNotFound(thread_id)
        self._cancellation.cancel(thread_id)
        if latest.status is RunStatus.WAITING_FOR_USER:
            await self._run_store.update_status(latest.run_id, RunStatus.CANCELLED)

    async def close(self) -> None:
        pending = [task for task in self._tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for stream in self._streams.values():
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()
        self._tasks.clear()
        self._streams.clear()

    def _launch(
        self,
        run_id: str,
        thread_id: str,
        graph_input: dict[str, object] | Command,
    ) -> RunHandle:
        self._publisher.open_run(run_id)
        events = self._publisher.subscribe(run_id)
        handle = RunHandle(run_id=run_id, thread_id=thread_id, events=events)
        self._streams[run_id] = events
        task = asyncio.create_task(self._execute(run_id, thread_id, graph_input))
        self._tasks[run_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(run_id, None))
        return handle

    async def _execute(
        self,
        run_id: str,
        thread_id: str,
        graph_input: dict[str, object] | Command,
    ) -> None:
        token: Token[_ExecutionIdentity | None] = _CURRENT_EXECUTION.set(
            _ExecutionIdentity(run_id, thread_id)
        )
        try:
            await self._run_store.update_status(run_id, RunStatus.RUNNING)
            await self._publisher.publish(
                EventType.RUN_STARTED,
                run_id,
                thread_id,
                {},
            )
            result = await self._graph.ainvoke(
                graph_input,
                config=self._config(thread_id),
            )
            if result.get("__interrupt__"):
                status = RunStatus.WAITING_FOR_USER
            elif result.get("status") == RunStatus.FAILED.value:
                status = RunStatus.FAILED
            else:
                status = RunStatus.COMPLETED
            await self._run_store.update_status(run_id, status)
            if status is RunStatus.FAILED:
                errors = result.get("errors", [])
                error = errors[-1] if errors else ResearchError(
                    error_code="research_failed",
                    stage="runtime",
                    message="Research could not produce a supported report.",
                )
                await self._publisher.publish(
                    EventType.ERROR,
                    run_id,
                    thread_id,
                    serialize_error(error),
                )
            await self._publisher.publish(
                EventType.DONE,
                run_id,
                thread_id,
                {"status": status.value},
            )
        except ResearchCancelled:
            await self._run_store.update_status(run_id, RunStatus.CANCELLED)
            await self._publisher.publish(
                EventType.RUN_CANCELLED,
                run_id,
                thread_id,
                {"message": "Research was cancelled."},
            )
            await self._publisher.publish(
                EventType.DONE,
                run_id,
                thread_id,
                {"status": RunStatus.CANCELLED.value},
            )
        except asyncio.CancelledError:
            await self._run_store.update_status(run_id, RunStatus.CANCELLED)
            raise
        except Exception:  # noqa: BLE001 - serialize one stable public error
            error = ResearchError(
                error_code="research_execution_failed",
                stage="runtime",
                message="Research execution failed.",
            )
            await self._run_store.update_status(
                run_id,
                RunStatus.FAILED,
                last_error=error.message,
            )
            await self._publisher.publish(
                EventType.ERROR,
                run_id,
                thread_id,
                serialize_error(error),
            )
            await self._publisher.publish(
                EventType.DONE,
                run_id,
                thread_id,
                {"status": RunStatus.FAILED.value},
            )
        finally:
            _CURRENT_EXECUTION.reset(token)
            await self._publisher.close(run_id)

    @staticmethod
    def _config(thread_id: str) -> dict[str, object]:
        return {
            "configurable": {"thread_id": thread_id},
            "max_concurrency": 3,
        }
