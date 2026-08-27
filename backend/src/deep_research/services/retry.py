import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    retries: int,
    base_delay_seconds: float,
    transient_exceptions: tuple[type[Exception], ...] = (
        TimeoutError,
        ConnectionError,
    ),
) -> T:
    """Run an async operation with a bounded exponential retry schedule."""

    if retries < 0:
        raise ValueError("retries must be non-negative")
    if base_delay_seconds < 0:
        raise ValueError("base_delay_seconds must be non-negative")

    for attempt in range(retries + 1):
        try:
            return await operation()
        except transient_exceptions:
            if attempt == retries:
                raise
            await asyncio.sleep(base_delay_seconds * 2**attempt)
    raise AssertionError("retry loop must return or raise")
