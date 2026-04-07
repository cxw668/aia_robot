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
import json
from app.knowledge_base.prompt_templates import build_scoring_prompt
from app.chat.index import query_llm

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

    # 特殊处理：明确的查询模式
    special_intent = None
    if "年缴" in query and "月缴" in query and "变更" in query:
        # 明确的保险费缴纳频率变更，应映射为保险计划变更意图（policy_change）
        special_intent = RetrievalIntent(
            key="policy_change",
            name="保险计划变更",
            schemas=("service_categories",),
            categories=("保险计划变更",),
        )
    elif ("表单" in query or "申请书" in query) and ("下载" in query or "变更" in query):
        # 表单下载相关查询
        special_intent = RetrievalIntent(
            key="form", 
            name="表单", 
            schemas=("forms_markdown",), 
            categories=("表单下载",)
        )

    if special_intent: 
        intent = special_intent
        confidence = 0.8  # 给特殊模式一个较高的置信度，q确保使用过滤检索实现优先匹配

    # 对查询文本进行向量化编码
    # 预处理：提取关键词/实体以便用于后续二次排序与更准确的向量化
    preprocessed_query, query_tokens = _preprocess_query(query)

    t_enc = time.perf_counter()
    # 使用预处理后的查询进行向量化
    query_vector = model.encode(preprocessed_query, normalize_embeddings=True).tolist()
    logger.debug(f"[rag] encode: {(time.perf_counter() - t_enc) * 1000:.1f}ms")

    # 置信度阈值（可调整）
    HIGH_CONF = 0.75
    MID_CONF = 0.55

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

    # 针对特殊意图的后处理：优先筛选更精确的匹配（例如表单或年缴/月缴变更）
    if hits:
        # 如果是表单类意图且抽取到 token，则优先保留 title/content 中包含 token 的条目
        try:
            intent_key = intent.key if intent else None
        except Exception:
            intent_key = None

        if intent_key == "form" and query_tokens:
            filtered = [h for h in hits if any(t in str(h.get("title", "")).lower() or t in str(h.get("content", "")).lower() for t in query_tokens)]
            if filtered:
                # 优先把标题中包含“申请书”的表单排在前面
                filtered.sort(key=lambda h: ("申请书" in str(h.get("title", "")).lower()), reverse=True)
                hits = filtered

        # 对缴费频率之类的关键短语做二次筛选
        freq_tokens = {"年缴", "月缴", "年改月", "年缴改月缴", "年付", "月付"}
        # 同义词映射：使得用户输入的 '年缴/月缴' 能匹配到文档中常见的 '年付/月付' 表述
        synonyms = {
            "年缴": ["年缴", "年付"],
            "月缴": ["月缴", "月付"],
            "年改月": ["年付", "月付", "变更保险费支付方式"],
            "年缴改月缴": ["年付", "月付", "变更保险费支付方式"],
            "年付": ["年付"],
            "月付": ["月付"],
        }

        if any(t in query_tokens for t in freq_tokens):
            def _matches_freq(h):
                txt = (str(h.get("title", "")) + "\n" + str(h.get("content", "")) + "\n" + str(h.get("service_name", "")) + "\n" + str(h.get("category", ""))).lower()
                for t in query_tokens:
                    for syn in synonyms.get(t, [t]):
                        if syn in txt:
                            return True
                return False

            freq_filtered = [h for h in hits if _matches_freq(h)]
            if freq_filtered:
                hits = freq_filtered

        # 最终重排序
        hits = _rescore_by_keyword_match(hits, query_tokens)

    # LLM 精筛：对 top N 候选使用 LLM 打分并融合得分（若配置或需要）
    try:
        # 控制最大候选数以限制 prompt 长度与成本
        max_cand = min(len(hits), max(3, top_k, 10))
        hits = llm_rescore_candidates(query, hits, max_candidates=max_cand)
    except Exception:
        logger.exception("[rag] llm rescoring step failed, continuing with existing hits")

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


def _preprocess_query(query: str) -> tuple[str, list[str]]:
    """简单预处理：去除多余空白，提取常见业务关键词用于后续匹配与向量化。

    返回 (preprocessed_text, tokens)
    """
    text = query or ""
    # 基于常见短语的提取（可扩展为实体识别）
    tokens = []
    lower = text.lower()
    candidates = [
        "年缴改月缴",
        "年缴",
        "月缴",
        "年改月",
        "理赔申请书",
        "理赔申请",
        "理赔",
        "第三方代缴",
        "申请书",
        "表单",
        "授权委托",
        "给付申请",
        "变更申请",
    ]
    for c in candidates:
        if c in lower:
            tokens.append(c)

    # 若没有抽取到明确短语，则不自动生成过多模糊 token（避免对二次排序产生误导）
    # 保留 tokens 为空表示不进行基于关键字的二次重排序
    # tokens = []

    # 构造预处理文本，保留原查询并把重要 token 前置以影响向量
    pre = (" ".join(tokens) + " " + text).strip()
    return pre, tokens


def _rescore_by_keyword_match(hits: list[dict], query_tokens: list[str]) -> list[dict]:
    """基于 query_tokens 对 hits 做轻量重打分（融合原始分数）。

    算法：match_score = (#token matches in title/content) / len(query_tokens)
    final_score = 0.8 * original_score + 0.2 * match_score
    """
    if not query_tokens:
        return hits

    def match_count(text: str) -> int:
        s = (text or "").lower()
        cnt = 0
        for t in query_tokens:
            if t and t in s:
                cnt += 1
        return cnt

    rescored = []
    # 额外的 token->优先 category 映射，用于把 "年缴/月缴" 之类的短语指向 "保险计划变更"
    special_map = {
        "年缴": "保险计划变更",
        "月缴": "保险计划变更",
        "年改月": "保险计划变更",
        "年缴改月缴": "保险计划变更",
        "理赔": "表单",
        "理赔申请": "表单",
        "第三方代缴": "表单",
    }

    for h in hits:
        orig = float(h.get("score") or 0)
        title = str(h.get("title", "") or "")
        content = str(h.get("content", "") or "")
        cnt = match_count(title) + match_count(content)
        match_score = cnt / max(1, len(query_tokens))
        final = 0.8 * orig + 0.2 * match_score

        # 对于特殊 token，如果命中指定 category/service_name，额外提升
        for t in query_tokens:
            mapped = special_map.get(t)
            if mapped and (mapped in str(h.get("service_name", "")) or mapped in str(h.get("category", ""))):
                final += 0.15

        final = round(final, 4)
        new = dict(h)
        new["score"] = final
        new["_orig_score"] = orig
        new["_match_count"] = cnt
        rescored.append(new)

    rescored.sort(key=lambda x: x.get("score", 0), reverse=True)
    return rescored


def llm_rescore_candidates(query: str, candidates: list[dict], max_candidates: int = 10) -> list[dict]:
    """使用 LLM 对候选文档进行逐条评分，并返回基于 LLM 分数融合后的候选列表。

    方法：构造评估型 prompt（严格要求 JSON 输出），一次性将最多 `max_candidates` 个候选发给 LLM，
    解析返回的 JSON（每项包含 `id`、`relevance_score`、`verdict`、`explanation`），
    将 LLM 得分与原始分数按比例融合（默认 60% 原始向量得分 + 40% LLM 得分），并返回按新分数排序的候选。
    """
    if not candidates:
        return candidates

    # 限制候选数量以控制 prompt 长度与成本
    slice_cands = candidates[: max(1, min(len(candidates), max_candidates))]
    prompt = build_scoring_prompt(query, slice_cands)
    try:
        resp = query_llm(prompt)
    except Exception as exc:
        logger.exception("[rag] llm_rescore failed: %s", exc)
        return candidates

    # 解析 JSON 输出
    try:
        parsed = json.loads(resp)
    except Exception:
        # 尝试从文本中抽取 JSON 数组子串
        try:
            start = resp.index("[")
            end = resp.rindex("]") + 1
            parsed = json.loads(resp[start:end])
        except Exception as exc:
            logger.exception("[rag] failed to parse llm response: %s", exc)
            return candidates

    # 构建 id -> score 映射
    score_map: dict[str, dict] = {}
    for item in parsed or []:
        try:
            cid = str(item.get("id"))
            s = float(item.get("relevance_score") or 0.0)
            verdict = item.get("verdict")
            expl = item.get("explanation")
            score_map[cid] = {
                "llm_score": max(0.0, min(1.0, s)),
                "verdict": verdict,
                "explanation": expl,
            }
        except Exception:
            continue

    # 将 llm 分数融合回候选列表
    fused: list[dict] = []
    for c in slice_cands:
        cid = str(c.get("id") or c.get("payload", {}).get("id") or c.get("title") or "")
        orig = float(c.get("score") or 0.0)
        meta = score_map.get(cid) or {}
        llm_s = float(meta.get("llm_score") or 0.0)
        # 融合策略：60% 原始向量分 + 40% LLM 分（可调整）
        combined = round(0.6 * orig + 0.4 * llm_s, 4)
        new = dict(c)
        new["llm_score"] = llm_s
        new["llm_verdict"] = meta.get("verdict")
        new["llm_explanation"] = meta.get("explanation")
        new["_orig_score"] = orig
        new["score"] = combined
        fused.append(new)

    # 保持原始列表后续条目（未进入 LLM 批次）的顺序与分数
    rest = candidates[len(slice_cands) :]
    full = fused + rest
    full.sort(key=lambda x: x.get("score", 0), reverse=True)
    return full

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
