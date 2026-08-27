from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

from deep_research.domain.events import EventType, ResearchEvent

_CLOSE = None
_QUEUE_SIZE = 256


@dataclass
class _RunChannel:
    queue: asyncio.Queue[ResearchEvent | None]
    sequence: int = 0
    subscribed: bool = False
    attached: bool = False
    terminated: bool = False


class EventPublisher:
    """Single-process, no-replay event transport with one consumer per run."""

    def __init__(self) -> None:
        self._runs: dict[str, _RunChannel] = {}

    def open_run(self, run_id: str) -> None:
        if run_id in self._runs:
            raise ValueError(f"run is already open: {run_id}")
        self._runs[run_id] = _RunChannel(asyncio.Queue(maxsize=_QUEUE_SIZE))

    def subscribe(self, run_id: str) -> AsyncIterator[ResearchEvent]:
        channel = self._runs.get(run_id)
        if channel is None:
            raise ValueError(f"run is not open: {run_id}")
        if channel.subscribed:
            raise ValueError(f"run already has a subscriber: {run_id}")
        channel.subscribed = True
        channel.attached = True

        async def iterate() -> AsyncIterator[ResearchEvent]:
            try:
                while True:
                    event = await channel.queue.get()
                    if event is _CLOSE:
                        return
                    yield event
            finally:
                channel.attached = False
                while not channel.queue.empty():
                    channel.queue.get_nowait()

        return iterate()

    async def publish(
        self,
        event_type: EventType | str,
        run_id: str,
        thread_id: str,
        payload: dict[str, object],
    ) -> None:
        channel = self._runs.get(run_id)
        if channel is None:
            raise ValueError(f"run is not open: {run_id}")
        if channel.terminated:
            return
        if channel.subscribed and not channel.attached:
            return
        if channel.queue.full():
            self._terminate_overflow(channel, run_id, thread_id)
            self._runs.pop(run_id, None)
            return
        channel.sequence += 1
        channel.queue.put_nowait(
            ResearchEvent(
                type=EventType(event_type),
                run_id=run_id,
                thread_id=thread_id,
                sequence=channel.sequence,
                timestamp=datetime.now(UTC),
                payload=payload,
            )
        )

    async def close(self, run_id: str) -> None:
        channel = self._runs.get(run_id)
        if channel is None or channel.terminated:
            return
        self._runs.pop(run_id, None)
        channel.terminated = True
        if not channel.attached:
            while not channel.queue.empty():
                channel.queue.get_nowait()
            return
        if channel.queue.full():
            self._terminate_overflow(channel, run_id, "unavailable")
            return
        channel.queue.put_nowait(_CLOSE)

    @staticmethod
    def _terminate_overflow(
        channel: _RunChannel,
        run_id: str,
        thread_id: str,
    ) -> None:
        while channel.queue.qsize() > _QUEUE_SIZE - 2:
            channel.queue.get_nowait()
        channel.sequence += 1
        channel.queue.put_nowait(
            ResearchEvent(
                type=EventType.ERROR,
                run_id=run_id,
                thread_id=thread_id,
                sequence=channel.sequence,
                timestamp=datetime.now(UTC),
                payload={
                    "error_code": "event_stream_overflow",
                    "message": "The live event stream could not keep up and was closed.",
                },
            )
        )
        channel.queue.put_nowait(_CLOSE)
        channel.terminated = True
