from __future__ import annotations

import logging
import os
import time

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.env_loader import EnvLoader
from app.knowledge_base.intent_rules import RetrievalIntent

_model_cache = settings.model_cache_path
if _model_cache:
    os.environ["HF_HOME"] = _model_cache
    os.environ["TRANSFORMERS_CACHE"] = _model_cache
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = _model_cache

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "aia_knowledge_base"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
TOP_K = 5
SCORE_THRESHOLD = 0.45

_client: QdrantClient | None = None
_model: SentenceTransformer | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.qdrantclient_url or None,
            api_key=settings.qdrantclient_key or None,
        )
    return _client


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        explicit_local = (EnvLoader.get("EMBEDDING_MODEL_PATH", "") or "").strip()
        local_candidates: list[str] = []

        if explicit_local:
            local_candidates.append(explicit_local)

        if _model_cache:
            direct = os.path.join(_model_cache, "models--BAAI--bge-small-zh-v1.5")
            if os.path.isdir(direct):
                local_candidates.append(direct)
                snapshots = os.path.join(direct, "snapshots")
                if os.path.isdir(snapshots):
                    for d in os.listdir(snapshots):
                        p = os.path.join(snapshots, d)
                        if os.path.isdir(p):
                            local_candidates.append(p)

        """在本地路径中查找并加载一个预训练的嵌入模型。"""
        for cand in local_candidates:
            if os.path.exists(os.path.join(cand, "config.json")) or os.path.exists(os.path.join(cand, "modules.json")):
                logger.info(f"[rag] using local embedding model path: {cand}")
                _model = SentenceTransformer(cand, local_files_only=True)
                break

        if _model is None:
            _model = SentenceTransformer(MODEL_NAME)
    return _model


def _match_any_condition(key: str, values: tuple[str, ...]) -> list[qmodels.FieldCondition]:
    return [qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value)) for value in values]

"""根据用户意图和在售状态动态创建过滤器对象"""
def build_filter(intent: RetrievalIntent | None, only_on_sale: bool = False) -> qmodels.Filter | None:
    must: list[qmodels.FieldCondition] = []
    if intent and intent.schemas:
        must.append(qmodels.FieldCondition(key="schema", match=qmodels.MatchAny(any=list(intent.schemas))))
    if only_on_sale or (intent and intent.only_on_sale):
        # 产品状态 product_status
        must.append(qmodels.FieldCondition(key="product_status", match=qmodels.MatchValue(value="在售")))
    should: list[qmodels.FieldCondition] = []
    if intent and intent.categories:
        should.extend(_match_any_condition("category", intent.categories))
    if not must and not should:
        return None
    return qmodels.Filter(must=must, should=should or None)

""" 向 Qdrant 向量数据库发起一次带过滤条件的相似度搜索请求"""
def query_collection(
    client: QdrantClient,
    collection_name: str,
    query_vector: list[float],
    top_k: int,
    score_threshold: float = SCORE_THRESHOLD,
    query_filter: qmodels.Filter | None = None,
) -> list[dict]:
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
        logger.debug(f"[rag] {collection_name}: {len(response.points)} hits in {elapsed_ms:.1f}ms")
    except UnexpectedResponse as exc:
        if exc.status_code == 404:
            logger.warning(f"[rag] collection not found: {collection_name}")
            return []
        raise

    rows: list[dict] = []
    for hit in response.points:
        if hit.score < score_threshold:
            continue
        payload = hit.payload or {}
        rows.append(
            {
                "score": round(hit.score, 4),
                "title": payload.get("title", ""),
                "content": payload.get("content", ""),
                "service_name": payload.get("service_name", ""),
                "service_url": payload.get("service_url", ""),
                "category": payload.get("category", ""),
                "schema": payload.get("schema", ""),
                "collection": collection_name,
            }
        )
    return rows
