"""RAG 检索引擎 —— 基于单一 Qdrant 集合的语义搜索。"""
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

# embedding 本地模型路径
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


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.qdrantclient_url or None,
            api_key=settings.qdrantclient_key or None,
        )
    return _client


def _get_model() -> SentenceTransformer:
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

        for cand in local_candidates:
            if os.path.exists(os.path.join(cand, "config.json")) or os.path.exists(os.path.join(cand, "modules.json")):
                logger.info(f"[rag] using local embedding model path: {cand}")
                _model = SentenceTransformer(cand, local_files_only=True)
                break

        if _model is None:
            _model = SentenceTransformer(MODEL_NAME)
    return _model


def _query_collection(
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
                "collection": collection_name,
            }
        )
    return rows


# ── Core retrieval ────────────────────────────────────────────────────────────

def retrieve(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
    only_on_sale: bool = False,
) -> list[dict]:
    """Semantic retrieval on single collection."""
    t_total = time.perf_counter()
    model = _get_model()
    client = _get_client()

    target_collection = collection_name or DEFAULT_COLLECTION
    t_enc = time.perf_counter()
    query_vector = model.encode(query, normalize_embeddings=True).tolist()
    logger.debug(f"[rag] encode: {(time.perf_counter() - t_enc) * 1000:.1f}ms")

    q_filter: qmodels.Filter | None = None
    if only_on_sale:
        q_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="product_status",
                    match=qmodels.MatchValue(value="在售"),
                )
            ]
        )

    hits = _query_collection(
        client,
        target_collection,
        query_vector,
        top_k,
        query_filter=q_filter,
    )

    logger.debug(
        f"[rag] total {(time.perf_counter() - t_total) * 1000:.1f}ms "
        f"| collection={target_collection} | hits={len(hits)}"
    )
    return hits


# ── RAG context builder ───────────────────────────────────────────────────────

def build_rag_context(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
) -> str:
    """Retrieve and format docs into an LLM-injectable context string."""
    product_keywords = ["在售", "产品", "保险计划", "推荐"]
    only_on_sale = any(kw in query for kw in product_keywords)

    docs = retrieve(query, top_k=top_k, collection_name=collection_name, only_on_sale=only_on_sale)
    if not docs:
        return "未找到相关知识库内容。"

    parts = []
    for i, doc in enumerate(docs, 1):
        coll_hint = f" [{doc.get('collection', '')}]" if doc.get("collection") else ""
        parts.append(
            f"[参考{i}]{coll_hint} 服务项目：{doc['title']}\n"
            f"{doc['content']}"
        )
    return "\n\n".join(parts)


# ── Convenience: retrieve + LLM in one call ───────────────────────────────────

def rag_query(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
) -> str:
    """Full RAG flow: retrieve → build prompt → call LLM."""
    from app.chat.index import query_llm

    context = build_rag_context(query, top_k=top_k, collection_name=collection_name)
    prompt = (
        "你是友邦保险（AIA）的智能客服助手，请根据以下知识库内容回答用户问题。\n"
        "如果知识库内容无法完整回答问题，请如实告知，不要编造信息。\n\n"
        f"《知识库内容》\n{context}\n\n"
        f"《用户问题》\n{query}\n\n"
        "请用简洁、准确的中文回答："
    )
    return query_llm(prompt)


# ── CLI quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging as _logging
    import sys

    _logging.basicConfig(level=_logging.DEBUG)

    test_query = sys.argv[1] if len(sys.argv) > 1 else "如何变更投保人？"
    print(f"\n查询: {test_query}\n{'=' * 50}")
    for r in retrieve(test_query):
        print(f"[{r['score']}] {r['title']} ({r.get('collection', '')})")
        print(f"  {r['content'][:80]}...\n")
