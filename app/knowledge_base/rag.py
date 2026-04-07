"""RAG 检索引擎 —— 基于单一 Qdrant 集合的语义搜索。"""
from __future__ import annotations

import logging
import time

from app.knowledge_base.intent_recognition import (
    classify_query_intent,
    classify_query_intent_with_scores,
)
import hashlib
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
    """
    在单个集合上进行语义检索，并支持意图路由
    
    Args:
        query (str): 查询字符串
        top_k (int): 返回结果的最大数量，默认使用TOP_K常量
        collection_name (str): 目标集合名称，默认使用DEFAULT_COLLECTION常量
        only_on_sale (bool): 是否只检索在售商品，默认为False
    
    Returns:
        list[dict]: 检索到的结果列表，每个元素为包含检索信息的字典
    
    """
    # 语义检索的主要实现流程
    t_total = time.perf_counter()
    model = get_model()
    client = get_client()

    target_collection = collection_name or DEFAULT_COLLECTION

    # 使用带分数的意图识别以获得置信度和候选
    intent_result = classify_query_intent_with_scores(query)
    intent = intent_result.intent if intent_result else None
    confidence = getattr(intent_result, "confidence", 0.0)

    # 对查询文本进行向量化编码
    t_enc = time.perf_counter()
    query_vector = model.encode(query, normalize_embeddings=True).tolist()
    logger.debug(f"[rag] encode: {(time.perf_counter() - t_enc) * 1000:.1f}ms")

    # 置信度阈值（可调整）
    HIGH_CONF = 0.7
    MID_CONF = 0.5

    hits: list[dict] = []
    used_fallback = False

    # 高置信：按首候选意图做单路过滤检索
    if intent and confidence >= HIGH_CONF:
        q_filter = build_filter(intent, only_on_sale=only_on_sale)
        hits = query_collection(client, target_collection, query_vector, top_k, query_filter=q_filter)
        if not hits and q_filter is not None:
            logger.info("[rag] no hits after high-conf intent filter, fallback to unfiltered retrieval: %s", query)
            hits = query_collection(client, target_collection, query_vector, top_k, query_filter=None)
            used_fallback = True

    # 中置信：Top2 双路检索（filtered + unfiltered）并合并去重
    elif intent and MID_CONF <= confidence < HIGH_CONF:
        q_filter = build_filter(intent, only_on_sale=only_on_sale)
        hits_filtered = query_collection(client, target_collection, query_vector, top_k, query_filter=q_filter)
        hits_unfiltered = query_collection(client, target_collection, query_vector, top_k, query_filter=None)
        hits = _merge_and_deduplicate([hits_filtered, hits_unfiltered], top_k)
        if not hits:
            logger.info("[rag] mid-conf dual-route produced no hits, fallback to unfiltered retrieval: %s", query)
            hits = query_collection(client, target_collection, query_vector, top_k, query_filter=None)
            used_fallback = True

    # 低置信或无法识别意图时：回退至全库检索
    else:
        hits = query_collection(client, target_collection, query_vector, top_k, query_filter=None)

    logger.debug(
        f"[rag] total {(time.perf_counter() - t_total) * 1000:.1f}ms "
        f"| collection={target_collection} | intent={(intent.name if intent else 'unknown')} | hits={len(hits)}"
    )
    return hits


def _merge_and_deduplicate(result_lists: list[list[dict]], top_k: int) -> list[dict]:
    """合并多路检索结果并去重，按 `score` 保留最高的条目。

    去重使用 `content` 的 md5 作为键；若无 `content`，使用 `title|collection` 作为备选键。
    """
    merged: dict[str, dict] = {}
    for results in result_lists:
        for r in results or []:
            content = str(r.get("content") or "")
            if content:
                key = hashlib.md5(content.encode("utf-8")).hexdigest()
            else:
                key = hashlib.md5((str(r.get("title") or "") + "|" + str(r.get("collection") or "")).encode("utf-8")).hexdigest()

            # 保留分数最高的结果
            if key not in merged or (r.get("score", 0) or 0) > (merged[key].get("score", 0) or 0):
                merged[key] = r

    sorted_results = sorted(merged.values(), key=lambda x: x.get("score", 0) or 0, reverse=True)
    return sorted_results[:top_k]

def build_rag_context(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
) -> str:
    """
    检索相关文档并将其格式化为可注入大语言模型的上下文字符串。
    
    该函数是 RAG 流程中的“增强”环节，负责将非结构化的检索结果
    转化为大语言模型易于理解的 Prompt 上下文。
    """
    # 1. 意图识别：分析用户查询的意图（例如是否包含特定服务或官方链接）
    intent = classify_query_intent(query)
    
    # 2. 向量检索：根据查询从知识库中获取最相关的文档片段
    docs = retrieve(query, top_k=top_k, collection_name=collection_name)
    
    # 3. 空结果处理：如果检索不到任何内容，根据是否有官方渠道返回不同的提示
    if not docs:
        if intent and intent.official_url:
            # 有官方渠道则引导用户去官网
            return f"未找到相关知识库内容。建议前往官方渠道：{intent.official_url}"
        # 否则返回通用的未找到提示
        return "未找到相关知识库内容。"

    parts: list[str] = []
    
    # 4. 头部信息构建：如果是“服务指南”类查询且有官网，优先在上下文头部展示官方链接
    if intent and intent.name == "服务指南" and intent.official_url:
        parts.append(f"官方渠道：{intent.official_url}")

    # 5. 遍历并格式化文档：将检索到的每个文档片段格式化为结构化的文本块
    for i, doc in enumerate(docs, 1):
        # 添加集合来源提示（如果文档属于特定集合）
        coll_hint = f" [{doc.get('collection', '')}]" if doc.get("collection") else ""
        # 添加服务链接提示（如果文档包含具体服务 URL）
        url_hint = f"\n链接：{doc.get('service_url', '')}" if doc.get("service_url") else ""
        
        # 组装引用块：包含引用编号、来源、标题和内容
        parts.append(
            f"[参考{i}]{coll_hint} 服务项目：{doc['title']}\n"
            f"{doc['content']}{url_hint}"
        )
        
    # 6. 拼接最终上下文：使用双换行符分隔不同的参考片段，形成最终的 Prompt 上下文
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
