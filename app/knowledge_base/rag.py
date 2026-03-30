"""RAG retrieval engine — semantic search over local Qdrant collections.

Improvements v2:
- TOP_K default raised to 5
- Score threshold 0.45: low-quality results filtered
- Diversity merge: no single collection dominates when multi-collection search
- Product filter: structured filter for 在售 status
- Per-call timing at DEBUG level
"""
from __future__ import annotations

import logging
import os
import time
from math import ceil

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http import models as qmodels
from sentence_transformers import SentenceTransformer

from app.config import settings

_model_cache = settings.model_cache_path
if _model_cache:
    os.environ["HF_HOME"] = _model_cache
    os.environ["TRANSFORMERS_CACHE"] = _model_cache
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = _model_cache

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "保单服务"
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
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _list_collection_names(client: QdrantClient) -> list[str]:
    try:
        return [c.name for c in client.get_collections().collections]
    except Exception:
        return []


def _contains_form_quote(query: str) -> bool:
    return "\u300a" in query or "\u300b" in query


def _resolve_target_collections(client: QdrantClient, collection_name: str) -> list[str]:
    """Resolve which collections to search.

    Rules:
    - Requested collection exists → search only that one.
    - Requested == DEFAULT but missing → search all.
    - Requested is non-default but missing → fallback to DEFAULT (if exists), else all.
    """
    names = _list_collection_names(client)
    if not names:
        return []
    if collection_name in names:
        return [collection_name]
    if collection_name == DEFAULT_COLLECTION:
        return names
    if DEFAULT_COLLECTION in names:
        return [DEFAULT_COLLECTION]
    return names


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
            return []
        raise

    rows: list[dict] = []
    for hit in response.points:
        if hit.score < score_threshold:
            continue
        payload = hit.payload or {}
        rows.append({
            "score": round(hit.score, 4),
            "title": payload.get("title", ""),
            "content": payload.get("content", ""),
            "service_name": payload.get("service_name", ""),
            "service_url": payload.get("service_url", ""),
            "category": payload.get("category", ""),
            "collection": collection_name,
        })
    return rows


def _diverse_merge(per_collection: dict[str, list[dict]], top_k: int) -> list[dict]:
    """Merge results from multiple collections with diversity control.

    No single collection can contribute more than ceil(top_k / 2) results
    when there are >= 2 collections with hits, so minority collections
    are not completely squeezed out.
    """
    if len(per_collection) <= 1:
        all_hits = [h for hits in per_collection.values() for h in hits]
        all_hits.sort(key=lambda x: x["score"], reverse=True)
        return all_hits[:top_k]

    cap = ceil(top_k / 2)
    # Round-robin by score until quota reached
    quota: dict[str, int] = {k: 0 for k in per_collection}
    merged: list[dict] = []
    pool = sorted(
        [h for hits in per_collection.values() for h in hits],
        key=lambda x: x["score"],
        reverse=True,
    )
    for hit in pool:
        if len(merged) >= top_k:
            break
        cname = hit["collection"]
        if quota[cname] < cap:
            merged.append(hit)
            quota[cname] += 1
    return merged


# ── Core retrieval ────────────────────────────────────────────────────────────

def retrieve(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
    only_on_sale: bool = False,
) -> list[dict]:
    """Semantic retrieval with fallback, diversity merge, and score filtering.

    Args:
        query:           User query text.
        top_k:           Maximum results to return.
        collection_name: Primary collection to search.
        only_on_sale:    When True, add payload filter productStatus=在售
                         (applies to 在售产品 collection only).
    """
    t_total = time.perf_counter()
    model = _get_model()
    client = _get_client()

    targets = _resolve_target_collections(client, collection_name)
    if not targets:
        logger.warning("[rag] No collections available in Qdrant.")
        return []

    # Form-quote boosting: prioritise form collections
    if _contains_form_quote(query):
        form_targets = [n for n in targets if "\u8868\u5355" in n]  # 表单
        if form_targets:
            non_form = [n for n in targets if "\u8868\u5355" not in n]
            targets = form_targets + non_form

    t_enc = time.perf_counter()
    query_vector = model.encode(query, normalize_embeddings=True).tolist()
    logger.debug(f"[rag] encode: {(time.perf_counter() - t_enc)*1000:.1f}ms")

    per_collection: dict[str, list[dict]] = {}
    for cname in targets:
        q_filter: qmodels.Filter | None = None
        if only_on_sale and "\u5728\u552e" in cname:  # 在售
            q_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="product_status",
                        match=qmodels.MatchValue(value="\u5728\u552e"),
                    )
                ]
            )
        hits = _query_collection(client, cname, query_vector, top_k, query_filter=q_filter)
        if hits:
            per_collection[cname] = hits

    merged = _diverse_merge(per_collection, top_k)
    logger.debug(
        f"[rag] total {(time.perf_counter() - t_total)*1000:.1f}ms "
        f"| collections={len(per_collection)} | hits={len(merged)}"
    )
    return merged


# ── RAG context builder ───────────────────────────────────────────────────────

def build_rag_context(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
) -> str:
    """Retrieve and format docs into an LLM-injectable context string."""
    # Auto-detect product queries and apply on-sale filter
    product_keywords = ["\u5728\u552e", "\u4ea7\u54c1", "\u4fdd\u9669\u8ba1\u5212", "\u5c71\u5d3e"]
    only_on_sale = any(kw in query for kw in product_keywords)

    docs = retrieve(query, top_k=top_k, collection_name=collection_name, only_on_sale=only_on_sale)
    if not docs:
        return "\u672a\u627e\u5230\u76f8\u5173\u77e5\u8bc6\u5e93\u5185\u5bb9\u3002"

    parts = []
    for i, doc in enumerate(docs, 1):
        coll_hint = f" [{doc.get('collection','')}]" if doc.get("collection") else ""
        parts.append(
            f"[\u53c2\u8003{i}]{coll_hint} \u670d\u52a1\u9879\u76ee\uff1a{doc['title']}\n"
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
        "\u4f60\u662f\u53cb\u90a6\u4fdd\u9669\uff08AIA\uff09\u7684\u667a\u80fd\u5ba2\u670d\u52a9\u624b"
        "\uff0c\u8bf7\u6839\u636e\u4ee5\u4e0b\u77e5\u8bc6\u5e93\u5185\u5bb9\u56de\u7b54\u7528\u6237\u95ee\u9898\u3002\n"
        "\u5982\u679c\u77e5\u8bc6\u5e93\u5185\u5bb9\u65e0\u6cd5\u5b8c\u6574\u56de\u7b54\u95ee\u9898\uff0c\u8bf7\u5982\u5b9e\u544a\u77e5"
        "\uff0c\u4e0d\u8981\u7f16\u9020\u4fe1\u606f\u3002\n\n"
        f"\u300a\u77e5\u8bc6\u5e93\u5185\u5bb9\u300b\n{context}\n\n"
        f"\u300a\u7528\u6237\u95ee\u9898\u300b\n{query}\n\n"
        "\u8bf7\u7528\u7b80\u6d01\u3001\u51c6\u786e\u7684\u4e2d\u6587\u56de\u7b54\uff1a"
    )
    return query_llm(prompt)


# ── CLI quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import logging as _logging
    _logging.basicConfig(level=_logging.DEBUG)

    test_query = sys.argv[1] if len(sys.argv) > 1 else "\u5982\u4f55\u53d8\u66f4\u6295\u4fdd\u4eba\uff1f"
    print(f"\n\u67e5\u8be2: {test_query}\n{'='*50}")
    for r in retrieve(test_query):
        print(f"[{r['score']}] {r['title']} ({r.get('collection','')})")
        print(f"  {r['content'][:80]}...\n")
