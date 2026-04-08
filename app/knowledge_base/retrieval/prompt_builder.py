"""Prompt templates for LLM rescoring（从 prompt_templates 迁移）。"""
from __future__ import annotations

import json
from typing import Iterable

def _value_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def build_scoring_prompt(query: str, candidates: Iterable[dict]) -> str:
    """构造用于 LLM 精筛的 prompt。"""
    parts = [
        "你是一个文档相关性评估助手。",
        "给定用户的原始问题和若干候选知识库文档，请为每个候选评估与用户问题的相关性。",
        "输出必须是严格的 JSON 数组 (list)，每个元素为对象 {id, relevance_score, verdict, explanation}。",
        "- `id`: 与候选文档对应的唯一标识符（来自知识库）。",
        "- `relevance_score`: 相关性分数，浮点数，范围 0 到 1，1 表示完全相关。",
        "- `verdict`: 'use' 或 'skip'，表示是否应被用于回答该问题。",
        "- `explanation`: 一句简短说明为何打分（1-2 句），不能编造事实，只能基于候选内容。",
        "不要输出除 JSON 以外的任何文本，且不要使用代码块。",
        "注意：如果候选内容与用户问题无关，请将 relevance_score 设为 0 并给出简短说明。",
        "现在开始：",
    ]
    parts.append(f"用户问题: {query}")
    parts.append("候选文档列表:")
    for c in candidates:
        cid = c.get("id") or c.get("payload", {}).get("id") or c.get("title") or "<no-id>"
        title = _value_to_text(c.get("title", "")).strip()
        snippet = _value_to_text(c.get("content", "")).strip().replace("\n", " ")[:800]
        parts.append(f"- id: {cid}\n  title: {title}\n  snippet: {snippet}")
    parts.append(
        "请按照上述约定，返回 JSON 数组。每个对象的 relevance_score 精确到小数点后 3 位即可。"
    )
    return "\n\n".join(parts)


__all__ = ["build_scoring_prompt"]
