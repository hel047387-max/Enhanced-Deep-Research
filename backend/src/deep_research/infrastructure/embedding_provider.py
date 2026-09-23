from __future__ import annotations

import asyncio
from typing import Any


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model: Any) -> None:
        self._model = model
        dimension = model.get_sentence_embedding_dimension()
        if not isinstance(dimension, int) or dimension < 1:
            raise ValueError("embedding model must report a positive dimension")
        self._dimension = dimension

    @classmethod
    def from_model_name(cls, model_name: str) -> SentenceTransformerEmbeddingProvider:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "Literature embeddings require the optional 'rag' dependencies."
            ) from None
        return cls(SentenceTransformer(model_name))

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = await asyncio.to_thread(
            self._model.encode_document,
            texts,
            normalize_embeddings=True,
        )
        values = vectors.tolist() if hasattr(vectors, "tolist") else vectors
        return [[float(value) for value in vector] for vector in values]

    async def embed_query(self, text: str) -> list[float]:
        vector = await asyncio.to_thread(
            self._model.encode_query,
            text,
            normalize_embeddings=True,
        )
        values = vector.tolist() if hasattr(vector, "tolist") else vector
        return [float(value) for value in values]
