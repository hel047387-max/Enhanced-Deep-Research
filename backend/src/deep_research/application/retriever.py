from __future__ import annotations

from typing import Protocol

from deep_research.domain.literature import (
    CandidateReranker,
    EmbeddingProvider,
    LiteratureIndex,
    LiteratureSearchRequest,
    QueryDecision,
    QueryMode,
    RetrievedUnit,
)


class QueryRouting(Protocol):
    async def route(self, query: str) -> QueryDecision: ...


class QueryExpansion(Protocol):
    async def expand(self, query: str, mode: QueryMode) -> list[str]: ...


class LiteratureRetriever:
    def __init__(
        self,
        router: QueryRouting,
        enhancer: QueryExpansion,
        embedder: EmbeddingProvider,
        index: LiteratureIndex,
        reranker: CandidateReranker,
        *,
        candidate_limit: int,
        top_k: int,
    ) -> None:
        self._router = router
        self._enhancer = enhancer
        self._embedder = embedder
        self._index = index
        self._reranker = reranker
        self._candidate_limit = candidate_limit
        self._top_k = top_k

    async def search(self, request: LiteratureSearchRequest) -> list[RetrievedUnit]:
        decision = await self._router.route(request.query)
        queries = (
            [request.query]
            if decision.mode == "direct"
            else await self._enhancer.expand(request.query, decision.mode)
        )

        best_by_unit: dict[object, RetrievedUnit] = {}
        for query in queries[:3]:
            vector = await self._embedder.embed_query(query)
            matches = await self._index.search(
                vector,
                limit=self._candidate_limit,
                filters=request.filters,
            )
            for match in matches:
                current = best_by_unit.get(match.unit.unit_id)
                if current is None or match.similarity_score > current.similarity_score:
                    best_by_unit[match.unit.unit_id] = match

        candidates = sorted(
            best_by_unit.values(),
            key=lambda item: item.similarity_score,
            reverse=True,
        )[: self._candidate_limit]
        return await self._reranker.rerank(
            request.query,
            candidates,
            limit=min(request.limit, self._top_k),
        )