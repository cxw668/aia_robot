"""主检索入口（原 rag.py 的核心逻辑）。"""
from __future__ import annotations

import logging
import time

from app.knowledge_base.config import DEFAULT_COLLECTION, TOP_K
from app.knowledge_base.core.vector_store import get_client, query_collection
from app.knowledge_base.core.embedding import get_model
from app.knowledge_base.retrieval.rescorer import llm_rescore_candidates

logger = logging.getLogger(__name__)


def retrieve(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
    only_on_sale: bool = False,
    category: str | None = None,
) -> list[dict]:
    """在单个集合上进行语义检索。"""
    t_total = time.perf_counter()
    model = get_model()
    client = get_client()

    target_collection = collection_name or DEFAULT_COLLECTION
    _ = (only_on_sale, category)

    t_enc = time.perf_counter()
    query_vector = model.encode(query, normalize_embeddings=True).tolist()
    logger.debug(f"[rag] encode: {(time.perf_counter() - t_enc) * 1000:.1f}ms")

    hits = query_collection(client, target_collection, query_vector, top_k, query_filter=None)

    try:
        max_cand = min(len(hits), max(3, top_k, 10))
        hits = llm_rescore_candidates(query, hits, max_candidates=max_cand)
    except Exception:
        logger.exception("[rag] llm rescoring step failed, continuing with existing hits")

    logger.debug(
        f"[rag] total {(time.perf_counter() - t_total) * 1000:.1f}ms "
        f"| collection={target_collection} | hits={len(hits)}"
    )
    return hits


def rag_query(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
) -> str:
    """Full RAG flow: retrieve → build prompt → call LLM."""
    from app.chat.index import query_llm
    from app.knowledge_base.intent.classifier import classify_query_intent
    from app.knowledge_base.retrieval.context_builder import build_rag_context

    intent = classify_query_intent(query)
    context = build_rag_context(query, top_k=top_k, collection_name=collection_name)
    official_hint = ""
    if intent and intent.name == "服务指南" and intent.official_url:
        official_hint = f"\n如果适合，优先引导用户前往官方服务入口：{intent.official_url}\n"
    prompt = (
        "你是友邦保险（AIA）的智能客服助手，请根据以下知识库内容回答用户问题。\n"
        "如果知识库内容无法完整回答问题，请如实告知，不要编造信息。\n"
        "对于服务指南类问题，优先给出官方办理入口链接。\n"
        f"{official_hint}\n"
        f"《知识库内容》\n{context}\n\n"
        f"《用户问题》\n{query}\n\n"
        "请用简洁、准确的中文回答："
    )
    return query_llm(prompt)


__all__ = ["retrieve", "rag_query"]
