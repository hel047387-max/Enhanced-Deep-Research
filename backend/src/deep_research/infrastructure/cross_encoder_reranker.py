from __future__ import annotations

import asyncio
from typing import Any

from deep_research.domain.literature import RetrievedUnit


class SentenceTransformerReranker:
    def __init__(self, model: Any) -> None:
        self._model = model

    @classmethod
    def from_model_name(cls, model_name: str) -> SentenceTransformerReranker:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            raise RuntimeError(
                "Literature reranking requires the optional 'rag' dependencies."
            ) from None
        return cls(CrossEncoder(model_name))

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedUnit],
        *,
        limit: int,
    ) -> list[RetrievedUnit]:
        if not candidates:
            return []
        pairs = [
            (query, candidate.unit.embedding_text())
            for candidate in candidates
        ]
        scores = await asyncio.to_thread(self._model.predict, pairs)
        ranked = [
            candidate.model_copy(update={"rerank_score": float(score)})
            for candidate, score in zip(candidates, scores, strict=True)
        ]
        return sorted(
            ranked,
            key=lambda item: item.rerank_score
            if item.rerank_score is not None
            else float("-inf"),
            reverse=True,
        )[:limit]
