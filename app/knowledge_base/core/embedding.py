"""Embedding API client for knowledge retrieval and ingestion."""
from __future__ import annotations

import math
import logging
from collections.abc import Sequence

import requests

from app.config import settings
from app.knowledge_base.config import MODEL_NAME

logger = logging.getLogger(__name__)

class EmbeddingVector(list[float]):
    def tolist(self) -> list[float]:
        return list(self)


class EmbeddingMatrix(list[EmbeddingVector]):
    def tolist(self) -> list[list[float]]:
        return [row.tolist() for row in self]


class SiliconFlowEmbeddingModel:
    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        model_name: str,
        timeout: int,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout

    def encode(
        self,
        sentences: str | Sequence[str],
        *,
        normalize_embeddings: bool = False,
        batch_size: int = 32,
        **_: object,
    ) -> EmbeddingVector | EmbeddingMatrix:
        if isinstance(sentences, str):
            texts = [sentences]
            single_input = True
        else:
            texts = [str(item) for item in sentences]
            single_input = False

        if not texts:
            return EmbeddingMatrix()

        vectors: list[EmbeddingVector] = []
        size = max(1, int(batch_size or 32))
        for start in range(0, len(texts), size):
            vectors.extend(
                self._embed_batch(
                    texts[start:start + size],
                    normalize_embeddings=normalize_embeddings,
                )
            )

        if single_input:
            return vectors[0]
        return EmbeddingMatrix(vectors)

    def _embed_batch(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool,
    ) -> list[EmbeddingVector]:
        payload = {
            "model": self.model_name,
            "input": texts[0] if len(texts) == 1 else texts,
        }
        response = requests.post(
            self.api_url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        if not response.ok:
            raise RuntimeError(f"Embedding API error {response.status_code}: {response.text}")

        data = response.json().get("data")
        if not isinstance(data, list):
            raise RuntimeError("Embedding API response missing data list")

        ordered_items = sorted(
            data,
            key=lambda item: int(item.get("index", 0)) if isinstance(item, dict) else 0,
        )
        vectors: list[EmbeddingVector] = []
        for item in ordered_items:
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise RuntimeError("Embedding API response item missing embedding")
            values = [float(value) for value in item["embedding"]]
            if normalize_embeddings:
                values = _normalize(values)
            vectors.append(EmbeddingVector(values))

        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Embedding API returned {len(vectors)} vectors for {len(texts)} texts"
            )
        return vectors

    def _headers(self) -> dict[str, str]:
        if not self.api_key.strip():
            raise RuntimeError(
                "Embedding API key is not set. Please set EMBEDDING_API_KEY in environment or app/.env"
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return values
    return [value / norm for value in values]


_model_instance: SiliconFlowEmbeddingModel | None = None


def get_model() -> SiliconFlowEmbeddingModel:
    global _model_instance
    if _model_instance is None:
        logger.info("[embedding] using SiliconFlow model: %s", MODEL_NAME)
        _model_instance = SiliconFlowEmbeddingModel(
            api_url=settings.embedding_api_url,
            api_key=settings.embedding_api_key,
            model_name=MODEL_NAME,
            timeout=settings.embedding_timeout,
        )
    return _model_instance


__all__ = ["get_model"]
