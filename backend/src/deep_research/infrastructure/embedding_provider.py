from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any


class SentenceTransformerEmbeddingProvider:
    def __init__(
        self,
        model: Any,
        *,
        expected_dimension: int | None = None,
    ) -> None:
        self._model = model
        dimension = model.get_sentence_embedding_dimension()
        if not isinstance(dimension, int) or dimension < 1:
            raise ValueError("embedding model must report a positive dimension")
        if expected_dimension is not None and dimension != expected_dimension:
            raise ValueError(
                f"embedding model dimension {dimension} does not match "
                f"QDRANT_VECTOR_SIZE={expected_dimension}"
            )
        self._dimension = dimension

    @classmethod
    def from_model_name(
        cls,
        model_name: str,
        *,
        expected_dimension: int | None = None,
    ) -> SentenceTransformerEmbeddingProvider:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "Literature embeddings require the optional 'rag' dependencies."
            ) from None
        return cls(
            SentenceTransformer(model_name),
            expected_dimension=expected_dimension,
        )

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


class DashScopeEmbeddingProvider:
    _BATCH_SIZE = 10

    def __init__(
        self,
        *,
        client: Any,
        model_name: str,
        api_key: str,
        expected_dimension: int | None = None,
    ) -> None:
        self._client = client
        self._model_name = model_name
        self._api_key = api_key
        self._expected_dimension = expected_dimension
        self._dimension = expected_dimension

    @classmethod
    def from_model_name(
        cls,
        model_name: str,
        *,
        api_key: str | None,
        base_url: str | None,
        expected_dimension: int | None = None,
    ) -> DashScopeEmbeddingProvider:
        if not api_key:
            raise RuntimeError(
                "EMBED_API_KEY is required when EMBED_MODEL_TYPE=dashscope."
            )
        try:
            import dashscope
        except ImportError:
            raise RuntimeError(
                "DashScope embeddings require the optional 'rag' dependencies."
            ) from None
        if base_url:
            dashscope.base_http_api_url = base_url
        return cls(
            client=dashscope.TextEmbedding,
            model_name=model_name,
            api_key=api_key,
            expected_dimension=expected_dimension,
        )

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            raise RuntimeError("embedding dimension is unavailable before the first request")
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._BATCH_SIZE):
            vectors.extend(
                await asyncio.to_thread(
                    self._embed,
                    texts[start : start + self._BATCH_SIZE],
                    "document",
                )
            )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await asyncio.to_thread(self._embed, [text], "query")
        return vectors[0]

    def _embed(self, texts: list[str], text_type: str) -> list[list[float]]:
        arguments: dict[str, object] = {
            "model": self._model_name,
            "input": texts,
            "api_key": self._api_key,
            "text_type": text_type,
        }
        if self._expected_dimension is not None:
            arguments["dimension"] = self._expected_dimension
        response = self._client.call(**arguments)
        status_code = self._value(response, "status_code")
        if status_code != 200:
            raise RuntimeError(f"DashScope embedding request failed: {response}")
        output = self._value(response, "output")
        entries = self._value(output, "embeddings")
        if not isinstance(entries, list) or len(entries) != len(texts):
            raise RuntimeError("DashScope returned an invalid embedding response")
        vectors = [self._vector(entry) for entry in entries]
        dimension = len(vectors[0]) if vectors else 0
        if dimension < 1 or any(len(vector) != dimension for vector in vectors):
            raise RuntimeError("DashScope returned inconsistent embedding dimensions")
        if self._expected_dimension is not None and dimension != self._expected_dimension:
            raise RuntimeError(
                f"DashScope returned dimension {dimension}, expected "
                f"QDRANT_VECTOR_SIZE={self._expected_dimension}"
            )
        if self._dimension is not None and dimension != self._dimension:
            raise RuntimeError("DashScope returned a changed embedding dimension")
        self._dimension = dimension
        return vectors

    @staticmethod
    def _value(value: object, key: str) -> object:
        if isinstance(value, Mapping):
            return value.get(key)
        return getattr(value, key, None)

    @classmethod
    def _vector(cls, entry: object) -> list[float]:
        values = cls._value(entry, "embedding")
        if not isinstance(values, list):
            raise TypeError("DashScope returned an embedding without vector values")
        return [float(value) for value in values]