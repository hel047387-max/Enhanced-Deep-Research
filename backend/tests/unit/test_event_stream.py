from itertools import pairwise

import pytest

from deep_research.domain.events import EventType
from deep_research.services.event_stream import EventPublisher


@pytest.mark.asyncio
async def test_events_buffer_before_subscription_and_have_monotonic_sequence() -> None:
    publisher = EventPublisher()
    publisher.open_run("run-1")
    await publisher.publish(EventType.RUN_STARTED, "run-1", "thread-1", {})
    subscription = publisher.subscribe("run-1")
    await publisher.publish(
        EventType.PLAN_CREATED,
        "run-1",
        "thread-1",
        {"task_count": 3},
    )

    first = await anext(subscription)
    second = await anext(subscription)

    assert [first.type, second.type] == [
        EventType.RUN_STARTED,
        EventType.PLAN_CREATED,
    ]
    assert [first.sequence, second.sequence] == [1, 2]


def test_subscription_requires_open_run_and_allows_only_one_subscriber() -> None:
    publisher = EventPublisher()
    with pytest.raises(ValueError, match="not open"):
        publisher.subscribe("missing")

    publisher.open_run("run-1")
    publisher.subscribe("run-1")
    with pytest.raises(ValueError, match="subscriber"):
        publisher.subscribe("run-1")


@pytest.mark.asyncio
async def test_slow_subscriber_receives_sanitized_overflow_then_terminates() -> None:
    publisher = EventPublisher()
    publisher.open_run("run-1")
    subscription = publisher.subscribe("run-1")

    for index in range(257):
        await publisher.publish(
            EventType.TASK_STARTED,
            "run-1",
            "thread-1",
            {"index": index},
        )

    events = [event async for event in subscription]

    assert events[-1].type is EventType.ERROR
    assert events[-1].payload == {
        "error_code": "event_stream_overflow",
        "message": "The live event stream could not keep up and was closed.",
    }
    assert all(
        earlier.sequence < later.sequence
        for earlier, later in pairwise(events)
    )


@pytest.mark.asyncio
async def test_close_terminates_subscription() -> None:
    publisher = EventPublisher()
    publisher.open_run("run-1")
    subscription = publisher.subscribe("run-1")

    await publisher.close("run-1")

    with pytest.raises(StopAsyncIteration):
        await anext(subscription)


@pytest.mark.asyncio
async def test_detached_subscriber_does_not_break_publish_or_terminal_cleanup() -> None:
    publisher = EventPublisher()
    publisher.open_run("run-1")
    subscription = publisher.subscribe("run-1")
    await publisher.publish(EventType.RUN_STARTED, "run-1", "thread-1", {})
    await anext(subscription)

    await subscription.aclose()
    await publisher.publish(EventType.PLAN_CREATED, "run-1", "thread-1", {})
    await publisher.close("run-1")

    publisher.open_run("run-1")
