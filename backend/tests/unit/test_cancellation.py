import pytest

from deep_research.services.cancellation import (
    CancellationRegistry,
    ResearchCancelled,
)


def test_cancelled_thread_raises_at_boundary() -> None:
    registry = CancellationRegistry()
    registry.cancel("thread-1")

    with pytest.raises(ResearchCancelled):
        registry.raise_if_cancelled("thread-1")


def test_cancel_is_idempotent_and_clear_restores_new_run() -> None:
    registry = CancellationRegistry()
    registry.cancel("thread-1")
    registry.cancel("thread-1")
    registry.clear("thread-1")

    registry.raise_if_cancelled("thread-1")
