"""Qdrant 向量数据库客户端封装 —— 连接、集合管理、基础搜索。"""
from __future__ import annotations

import logging
import time

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from app.config import settings
from app.knowledge_base.config import SCORE_THRESHOLD, VECTOR_SIZE

logger = logging.getLogger(__name__)

_client_instance: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = QdrantClient(
            url=settings.qdrantclient_url or None,
            api_key=settings.qdrantclient_key or None,
        )
    return _client_instance


def ensure_collection(client: QdrantClient, name: str, vector_size: int = VECTOR_SIZE) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if name in existing:
        info = client.get_collection(name)
        vectors = getattr(getattr(info.config, "params", None), "vectors", None)
        current_size = (
            getattr(vectors, "size", None)
            if not isinstance(vectors, dict)
            else next(
                (
                    value.get("size") if isinstance(value, dict) else getattr(value, "size", None)
                    for value in vectors.values()
                ),
                None,
            )
        )
        if current_size is not None and int(current_size) != vector_size:
            raise RuntimeError(
                f"Collection '{name}' vector size is {current_size}, but the current embedding model "
                f"requires {vector_size}. Please recreate the collection and re-ingest data."
            )
        return
    client.create_collection(
        name,
        vectors_config=qmodels.VectorParams(
            size=vector_size, distance=qmodels.Distance.COSINE
        ),
    )


def _match_any_condition(key: str, values: tuple[str, ...]) -> list[qmodels.FieldCondition]:
    return [
        qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=v))
        for v in values
    ]


def get_available_categories(collection_name: str = "aia_knowledge_base") -> set[str]:
    """获取向量库中可用的所有分类。"""
    from app.knowledge_base.processing.normalizer import get_point_category

    client = get_client()
    try:
        all_categories: set[str] = set()
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=collection_name,
                scroll_filter=None,
                limit=600,
                with_payload=["category", "category_canonical", "service_name", "source_file"],
                with_vectors=False,
                offset=offset,
            )
            if not records:
                break
            for record in records:
                payload = record.payload or {}
                category = get_point_category(payload)
                if category:
                    all_categories.add(category)
            if offset is None:
                break
        return all_categories
    except Exception as e:
        print(f"Warning: Could not fetch categories from vector DB: {e}")
        return set()


def query_collection(
    client: QdrantClient,
    collection_name: str,
    query_vector: list[float],
    top_k: int,
    score_threshold: float = SCORE_THRESHOLD,
    query_filter: qmodels.Filter | None = None,
) -> list[dict]:
    """向 Qdrant 向量数据库发起一次带过滤条件的相似度搜索请求。"""
    try:
        t0 = time.perf_counter()
        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k,
            with_payload=True,
            query_filter=query_filter,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug("[rag] %s: %s hits in %.1fms", collection_name, len(response.points), elapsed_ms)
    except UnexpectedResponse as exc:
        if exc.status_code == 404:
            logger.warning("[rag] collection not found: %s", collection_name)
            return []
        raise

    rows: list[dict] = []
    for hit in response.points:
        score = getattr(hit, "score", None) if not isinstance(hit, dict) else hit.get("score")
        if score is None:
            score = hit.get("payload", {}).get("_score") if isinstance(hit, dict) else None
        if score is None or score < score_threshold:
            continue
        payload = (
            getattr(hit, "payload", None)
            or (hit.get("payload") if isinstance(hit, dict) else {})
            or {}
        )
        _id = getattr(hit, "id", None) if not isinstance(hit, dict) else hit.get("id")
        rows.append(
            {
                "id": _id,
                "score": round(float(score), 4),
                "title": payload.get("title", ""),
                "content": payload.get("content", ""),
                "service_name": payload.get("service_name", ""),
                "service_url": payload.get("service_url", ""),
                "category": payload.get("category", ""),
                "schema": payload.get("schema", ""),
                "collection": collection_name,
                "payload": payload,
            }
        )
    return rows


__all__ = [
    "get_client",
    "ensure_collection",
    "get_available_categories",
    "query_collection",
    "_match_any_condition",
]
