"""RAG 检索引擎 —— 基于单一 Qdrant 集合的语义搜索。"""
from __future__ import annotations

import logging
import time

from app.knowledge_base.intent_recognition import classify_query_intent
from app.knowledge_base.intent_rules import RetrievalIntent
from app.knowledge_base.retrieval_data_source import (
    DEFAULT_COLLECTION,
    TOP_K,
    build_filter,
    get_client,
    get_model,
    query_collection,
)

logger = logging.getLogger(__name__)


# ── Core retrieval ────────────────────────────────────────────────────────────

def retrieve(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
    only_on_sale: bool = False,
) -> list[dict]:
    """Semantic retrieval on single collection with intent routing."""
    t_total = time.perf_counter()
    model = get_model()
    client = get_client()

    target_collection = collection_name or DEFAULT_COLLECTION
    intent = classify_query_intent(query)
    t_enc = time.perf_counter()
    query_vector = model.encode(query, normalize_embeddings=True).tolist()
    logger.debug(f"[rag] encode: {(time.perf_counter() - t_enc) * 1000:.1f}ms")

    q_filter = build_filter(intent, only_on_sale=only_on_sale)
    hits = query_collection(
        client,
        target_collection,
        query_vector,
        top_k,
        query_filter=q_filter,
    )
    if not hits and q_filter is not None:
        logger.info("[rag] no hits after intent filter, fallback to unfiltered retrieval: %s", query)
        hits = query_collection(client, target_collection, query_vector, top_k, query_filter=None)

    logger.debug(
        f"[rag] total {(time.perf_counter() - t_total) * 1000:.1f}ms "
        f"| collection={target_collection} | intent={(intent.name if intent else 'unknown')} | hits={len(hits)}"
    )
    return hits


def build_rag_context(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
) -> str:
    """Retrieve and format docs into an LLM-injectable context string."""
    intent = classify_query_intent(query)
    docs = retrieve(query, top_k=top_k, collection_name=collection_name)
    if not docs:
        if intent and intent.official_url:
            return f"未找到相关知识库内容。建议前往官方渠道：{intent.official_url}"
        return "未找到相关知识库内容。"

    parts: list[str] = []
    if intent and intent.name == "服务指南" and intent.official_url:
        parts.append(f"官方渠道：{intent.official_url}")

    for i, doc in enumerate(docs, 1):
        coll_hint = f" [{doc.get('collection', '')}]" if doc.get("collection") else ""
        url_hint = f"\n链接：{doc.get('service_url', '')}" if doc.get("service_url") else ""
        parts.append(
            f"[参考{i}]{coll_hint} 服务项目：{doc['title']}\n"
            f"{doc['content']}{url_hint}"
        )
    return "\n\n".join(parts)


def rag_query(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
) -> str:
    """Full RAG flow: retrieve → build prompt → call LLM."""
    from app.chat.index import query_llm

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


if __name__ == "__main__":
    import logging as _logging
    import sys

    _logging.basicConfig(level=_logging.DEBUG)

    test_query = sys.argv[1] if len(sys.argv) > 1 else "如何变更投保人？"
    print(f"\n查询: {test_query}\n{'=' * 50}")
    detected = classify_query_intent(test_query)
    print(f"intent: {detected.name if detected else 'unknown'}")
    for r in retrieve(test_query):
        print(f"[{r['score']}] {r['title']} ({r.get('schema', '')})")
        print(f"  {str(r['content'])[:80]}...\n")
