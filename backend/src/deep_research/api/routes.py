from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from deep_research.api.schemas import (
    CancellationResponse,
    HealthResponse,
    ReportResponse,
    ResearchResumeRequest,
    ResearchSnapshotResponse,
    ResearchStartRequest,
)
from deep_research.domain.events import ResearchEvent
from deep_research.services.runtime import (
    InvalidResumeState,
    ResearchRuntime,
    ResearchThreadNotFound,
    RunHandle,
)


def _runtime(request: Request) -> ResearchRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Research runtime is unavailable.")
    return runtime


async def _sse(events: AsyncIterator[ResearchEvent]) -> AsyncIterator[str]:
    async for event in events:
        data = json.dumps(
            event.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        yield f"data: {data}\n\n"


def _stream(handle: RunHandle) -> StreamingResponse:
    return StreamingResponse(
        _sse(handle.events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


router = APIRouter(prefix="/api/v1/research")


@router.post("/stream")
async def start_stream(
    body: ResearchStartRequest,
    request: Request,
) -> StreamingResponse:
    handle = await _runtime(request).start(body.query)
    return _stream(handle)


@router.post("/{thread_id}/resume/stream")
async def resume_stream(
    thread_id: str,
    body: ResearchResumeRequest,
    request: Request,
) -> StreamingResponse:
    try:
        handle = await _runtime(request).resume(thread_id, body.answer)
    except ResearchThreadNotFound as exc:
        raise HTTPException(status_code=404, detail="Research thread was not found.") from exc
    except InvalidResumeState as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Research thread is not waiting for clarification.",
        ) from exc
    return _stream(handle)


@router.get("/{thread_id}", response_model=ResearchSnapshotResponse)
async def get_snapshot(
    thread_id: str,
    request: Request,
) -> ResearchSnapshotResponse:
    try:
        snapshot = await _runtime(request).snapshot(thread_id)
    except ResearchThreadNotFound as exc:
        raise HTTPException(status_code=404, detail="Research thread was not found.") from exc
    return ResearchSnapshotResponse.model_validate(snapshot.model_dump())


@router.get("/{thread_id}/report", response_model=ReportResponse)
async def get_report(thread_id: str, request: Request) -> ReportResponse:
    try:
        snapshot = await _runtime(request).snapshot(thread_id)
    except ResearchThreadNotFound as exc:
        raise HTTPException(status_code=404, detail="Research thread was not found.") from exc
    if snapshot.report is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The research report is not available yet.",
        )
    return ReportResponse(
        run_id=snapshot.run_id,
        thread_id=thread_id,
        report=snapshot.report,
    )


@router.post(
    "/{thread_id}/cancel",
    response_model=CancellationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_research(
    thread_id: str,
    request: Request,
) -> CancellationResponse:
    try:
        await _runtime(request).cancel(thread_id)
    except ResearchThreadNotFound as exc:
        raise HTTPException(status_code=404, detail="Research thread was not found.") from exc
    return CancellationResponse(thread_id=thread_id)


health_router = APIRouter()


@health_router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
