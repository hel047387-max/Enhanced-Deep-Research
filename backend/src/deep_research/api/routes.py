from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request, status
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
    # 【特殊用法】getattr(obj, "attr", default)：
    # 尝试读取 request.app.state.runtime；如果这个属性不存在，就返回 None。
    # app.state 通常用于保存整个 FastAPI 应用共享的对象。
    """从应用共享状态获取 Runtime；未初始化时返回 503。"""
    if runtime is None:
        raise HTTPException(status_code=503, detail="Research runtime is unavailable.")
    return runtime


async def _sse(events: AsyncIterator[ResearchEvent]) -> AsyncIterator[str]:
    """把领域事件编码成浏览器可消费的 SSE data 帧。"""
    async for event in events:
        data = json.dumps(
            event.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        yield f"data: {data}\n\n"


def _stream(handle: RunHandle) -> StreamingResponse:
    """创建长连接响应，让研究事件以 text/event-stream 持续返回。"""
    return StreamingResponse(
        _sse(handle.events),# handle.events 是 ResearchEvent 的异步事件流。
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


router = APIRouter(prefix="/api/v1/research")

#HTTP Request
#├── method        → POST / GET
#├── url           → /stream
#├── headers       → 请求头
#├── path_params   → 路径参数
#├── query_params  → 查询参数
#└── body          → 请求体
#request.app       FastAPI 应用实例
@router.post("/stream")
async def start_stream(
    body: ResearchStartRequest,
    request: Request,
) -> StreamingResponse:
    """启动新研究并返回实时事件流；请求体中的 query 是研究问题。"""
    handle = await _runtime(request).start(body.query, use_memory=body.use_memory, use_literature=body.use_literature)
    return _stream(handle)


@router.post("/{thread_id}/resume/stream")
async def resume_stream(
    thread_id: str,
    body: ResearchResumeRequest,
    request: Request,
) -> StreamingResponse:
    """提交澄清回答，从指定 thread 的 checkpoint 继续研究。"""
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
    """读取最新状态快照，供前端刷新后恢复研究进度。"""
    try:
        snapshot = await _runtime(request).snapshot(thread_id)
    except ResearchThreadNotFound as exc:
        raise HTTPException(status_code=404, detail="Research thread was not found.") from exc
    return ResearchSnapshotResponse.model_validate(snapshot.model_dump())


@router.get("/{thread_id}/report", response_model=ReportResponse)
async def get_report(thread_id: str, request: Request) -> ReportResponse:
    """返回最终 Markdown 报告；报告未生成时返回 409。"""
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
    """请求协作式取消指定研究线程。"""
    try:
        await _runtime(request).cancel(thread_id)
    except ResearchThreadNotFound as exc:
        raise HTTPException(status_code=404, detail="Research thread was not found.") from exc
    return CancellationResponse(thread_id=thread_id)


memory_router = APIRouter(prefix="/api/v1/memories")


def _memory_store(request: Request):
    store = _runtime(request).memory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Research memory is unavailable.")
    return store


@memory_router.get("/researches")
async def list_research_archives(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return {"items": await _memory_store(request).list_archives(limit=limit, offset=offset)}


@memory_router.get("/search")
async def search_research_memory(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=50),
):
    return await _memory_store(request).search(
        q, max_researches=limit, max_cards=10
    )


@memory_router.get("/researches/{thread_id}")
async def get_research_archive(thread_id: str, request: Request):
    detail = await _memory_store(request).get_archive(thread_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Research archive was not found.")
    return detail


health_router = APIRouter()


@health_router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """提供不依赖模型和搜索服务的健康检查。"""
    return HealthResponse()
