import json

import pytest

from deep_research.api.routes import health_router, router


@pytest.mark.asyncio
async def test_stream_starts_with_valid_envelope_and_sse_headers(async_client) -> None:
    async with async_client.stream(
        "POST",
        "/api/v1/research/stream",
        json={"query": "A complete scoped question"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["connection"] == "keep-alive"
        assert response.headers["x-accel-buffering"] == "no"
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
    snapshot = await async_client.get(f"/api/v1/research/{running_thread_id}")
    assert snapshot.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_snapshot_and_report_use_the_same_runtime(async_client) -> None:
    async with async_client.stream(
        "POST",
        "/api/v1/research/stream",
        json={"query": "A complete scoped question"},
    ) as response:
        events = [
            json.loads(line.removeprefix("data: "))
            async for line in response.aiter_lines()
            if line.startswith("data: ")
        ]
    thread_id = events[0]["thread_id"]

    snapshot = await async_client.get(f"/api/v1/research/{thread_id}")
    report = await async_client.get(f"/api/v1/research/{thread_id}/report")

    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "completed"
    assert report.status_code == 200
    assert report.json()["report"].startswith("# Research report")


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["query", "answer"])
async def test_stream_requests_reject_empty_and_oversized_text(async_client, field) -> None:
    path = (
        "/api/v1/research/stream"
        if field == "query"
        else "/api/v1/research/thread-1/resume/stream"
    )

    empty = await async_client.post(path, json={field: "   "})
    oversized = await async_client.post(path, json={field: "x" * 10_001})

    assert empty.status_code == 422
    assert oversized.status_code == 422


@pytest.mark.asyncio
async def test_cors_uses_the_explicit_allowlist(async_client) -> None:
    allowed = await async_client.options(
        "/api/v1/research/stream",
        headers={
            "Origin": "https://allowed.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    rejected = await async_client.options(
        "/api/v1/research/stream",
        headers={
            "Origin": "https://rejected.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "https://allowed.example"
    assert "access-control-allow-origin" not in rejected.headers


def test_application_exposes_only_the_approved_endpoints() -> None:
    routes = {
        (method, route.path)
        for route in [*router.routes, *health_router.routes]
        for method in getattr(route, "methods", set())
    }

    assert routes == {
        ("POST", "/api/v1/research/stream"),
        ("POST", "/api/v1/research/{thread_id}/resume/stream"),
        ("GET", "/api/v1/research/{thread_id}"),
        ("GET", "/api/v1/research/{thread_id}/report"),
        ("POST", "/api/v1/research/{thread_id}/cancel"),
        ("GET", "/health"),
    }
