from __future__ import annotations

from threading import RLock


class ResearchCancelled(RuntimeError):
    """Raised at a cooperative graph boundary after cancellation."""


class CancellationRegistry:
    """Thread-safe in-process cancellation flags keyed by conversation thread."""

    def __init__(self) -> None:
        self._cancelled: set[str] = set()
        self._lock = RLock()

    def cancel(self, thread_id: str) -> None:
        with self._lock:
            self._cancelled.add(thread_id)

    def clear(self, thread_id: str) -> None:
        with self._lock:
            self._cancelled.discard(thread_id)

    def is_cancelled(self, thread_id: str) -> bool:
        with self._lock:
            return thread_id in self._cancelled

    def raise_if_cancelled(self, thread_id: str) -> None:
        if self.is_cancelled(thread_id):
            raise ResearchCancelled("research was cancelled")
