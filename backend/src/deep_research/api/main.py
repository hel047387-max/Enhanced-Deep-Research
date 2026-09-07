from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from deep_research.api.routes import health_router, router
from deep_research.config import Settings, get_settings
from deep_research.domain.plan import (
    CoverageDecision,
    GapAssessment,
    ResearchBrief,
    ResearchPlan,
)
from deep_research.domain.review import ReportDraft, ReviewResult
from deep_research.graph.builder import WorkflowDependencies, build_research_graph
from deep_research.llm import create_structured_model
from deep_research.nodes.clarify import ClarificationDecision
from deep_research.nodes.researcher import EvidenceExtraction
from deep_research.persistence.checkpoint import checkpoint_context
from deep_research.persistence.run_store import RunStore
from deep_research.services.cancellation import CancellationRegistry
from deep_research.services.event_stream import EventPublisher
from deep_research.services.runtime import (
    ResearchRuntime,
    RuntimeCancellationChecker,
    RuntimeEventSink,
)
from deep_research.tools.search import TavilySearchProvider


class _PromptRouter:
    """根据提示词标记把模型调用路由到匹配的固定响应。"""
    def __init__(self, marker: str, matched: Any, fallback: Any) -> None:
        self._marker = marker
        self._matched = matched
        self._fallback = fallback

    async def ainvoke(self, input: Any) -> Any:
        prompt = str(input[0].content)
        model = self._matched if self._marker in prompt else self._fallback
        return await model.ainvoke(input)


def _production_dependencies(
    settings: Settings,
    publisher: EventPublisher,
    cancellation: CancellationRegistry,
) -> WorkflowDependencies:
    if not settings.tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is required to start the research API.")
    clarification = create_structured_model(settings, ClarificationDecision)
    brief = create_structured_model(settings, ResearchBrief)
    gap = create_structured_model(settings, GapAssessment)
    coverage = create_structured_model(settings, CoverageDecision)
    return WorkflowDependencies(
        clarifier_model=_PromptRouter("ClarificationDecision", clarification, brief),
        planner_model=create_structured_model(settings, ResearchPlan),
        evidence_model=create_structured_model(settings, EvidenceExtraction),
        gap_model=_PromptRouter("Assess global coverage once", coverage, gap),
        writer_model=create_structured_model(settings, ReportDraft),
        reviewer_model=create_structured_model(settings, ReviewResult),
        search_provider=TavilySearchProvider.from_api_key(settings.tavily_api_key),
        budgets=settings.budgets,
        event_sink=RuntimeEventSink(publisher),
        cancellation_checker=RuntimeCancellationChecker(cancellation),
    )


def _origins(settings: Settings, override: list[str] | None) -> list[str]:
    """解析 CORS 允许的来源列表。"""
    origins = override or [
        origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
    ]
    if "*" in origins:
        raise ValueError("CORS origins must be an explicit allowlist; '*' is not allowed.")
    return origins


def create_app(
    runtime: ResearchRuntime | None = None,
    *,
    cors_origins: list[str] | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if runtime is not None:
            application.state.runtime = runtime
            yield
            return

        store = RunStore(resolved_settings.checkpoint_db_path)
        await store.initialize()
        publisher = EventPublisher()
        cancellation = CancellationRegistry()
        async with checkpoint_context(resolved_settings.checkpoint_db_path) as checkpointer:
            graph = build_research_graph(
                _production_dependencies(
                    resolved_settings,
                    publisher,
                    cancellation,
                ),
                checkpointer=checkpointer,
            )
            owned_runtime = ResearchRuntime(
                graph,
                store,
                publisher,
                cancellation,
            )
            application.state.runtime = owned_runtime
            try:
                yield
            finally:
                await owned_runtime.close()

    application = FastAPI(
        title="Deep Research API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    if runtime is not None:
        application.state.runtime = runtime
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_origins(resolved_settings, cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(router)
    application.include_router(health_router)
    return application


app = create_app()
