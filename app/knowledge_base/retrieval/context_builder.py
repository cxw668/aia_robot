"""RAG 上下文构建（从 rag.py 迁移）。"""
from __future__ import annotations

from app.knowledge_base.config import DEFAULT_COLLECTION, TOP_K
from app.knowledge_base.intent.classifier import classify_query_intent


def build_rag_context(
    query: str,
    top_k: int = TOP_K,
    collection_name: str = DEFAULT_COLLECTION,
) -> str:
    """检索相关文档并将其格式化为可注入大语言模型的上下文字符串。"""
    from app.knowledge_base.retrieval.engine import retrieve

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


__all__ = ["build_rag_context"]
