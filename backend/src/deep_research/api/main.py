from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from deep_research.api.literature_routes import (
    LiteratureApplication,
)
from deep_research.api.literature_routes import (
    router as literature_router,
)
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


def _production_literature_application(
    settings: Settings,
) -> tuple[LiteratureApplication, Any]:
    try:
        from qdrant_client import AsyncQdrantClient
    except ImportError:
        raise RuntimeError(
            "Literature RAG requires the optional 'rag' dependencies."
        ) from None

    from deep_research.application.document_processor import DocumentProcessor
    from deep_research.application.query_enhancer import (
        ExpandedQueries,
        HypotheticalPassage,
        QueryEnhancer,
    )
    from deep_research.application.query_router import QueryRouter
    from deep_research.application.retriever import LiteratureRetriever
    from deep_research.domain.literature import QueryDecision
    from deep_research.infrastructure.cross_encoder_reranker import (
        SentenceTransformerReranker,
    )
    from deep_research.infrastructure.docling_parser import DoclingParser
    from deep_research.infrastructure.embedding_provider import (
        SentenceTransformerEmbeddingProvider,
    )
    from deep_research.infrastructure.qdrant_index import QdrantLiteratureIndex

    client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    index = QdrantLiteratureIndex(client, settings.qdrant_collection)
    embedder = SentenceTransformerEmbeddingProvider.from_model_name(
        settings.rag_embedding_model
    )
    parser = DoclingParser.from_model_name(
        settings.rag_embedding_model,
        max_tokens=settings.rag_chunk_max_tokens,
    )
    reranker = SentenceTransformerReranker.from_model_name(
        settings.rag_reranker_model
    )
    router = QueryRouter(create_structured_model(settings, QueryDecision))
    enhancer = QueryEnhancer(
        create_structured_model(settings, ExpandedQueries),
        create_structured_model(settings, HypotheticalPassage),
    )
    retriever = LiteratureRetriever(
        router,
        enhancer,
        embedder,
        index,
        reranker,
        candidate_limit=settings.rag_candidate_limit,
        top_k=settings.rag_top_k,
    )
    return (
        LiteratureApplication(
            processor=DocumentProcessor(parser, embedder, index),
            retriever=retriever,
        ),
        client,
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
    literature_application: LiteratureApplication | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        owned_literature_client = None
        if literature_application is not None:
            application.state.literature_application = literature_application
        elif resolved_settings.rag_enabled:
            (
                application.state.literature_application,
                owned_literature_client,
            ) = _production_literature_application(resolved_settings)
        if runtime is not None:
            application.state.runtime = runtime
            try:
                yield
            finally:
                if owned_literature_client is not None:
                    await owned_literature_client.close()
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
                if owned_literature_client is not None:
                    await owned_literature_client.close()

    application = FastAPI(
        title="Deep Research API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_origins(resolved_settings, cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    application.include_router(router)
    application.include_router(literature_router)
    application.include_router(health_router)
    application.state.rag_max_upload_bytes = resolved_settings.rag_max_upload_bytes
    if runtime is not None:
        application.state.runtime = runtime
    if literature_application is not None:
        application.state.literature_application = literature_application
    return application


app = create_app()
