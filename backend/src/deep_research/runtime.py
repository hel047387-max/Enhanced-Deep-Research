from typing import Protocol


class EventSink(Protocol):
    async def emit(self, event_type: str, payload: dict[str, object]) -> None: ...


class CancellationChecker(Protocol):
    def raise_if_cancelled(self) -> None: ...
