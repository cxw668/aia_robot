from __future__ import annotations

from dataclasses import dataclass

from app.knowledge_base.intent_rules import (
    INTENT_BONUS_RULES,
    INTENT_KEYWORDS,
    INTENT_MAP,
    RetrievalIntent,
    normalize_query_text,
)


@dataclass(frozen=True)
class IntentCandidate:
    key: str
    score: int
    confidence: float
    intent: RetrievalIntent


@dataclass(frozen=True)
class IntentRecognitionResult:
    intent: RetrievalIntent | None
    scores: dict[str, int]
    normalized_query: str
    confidence: float
    candidates: list[IntentCandidate]
    needs_confirmation: bool


def score_query_intents(query: str) -> dict[str, int]:
    """
    根据查询文本计算各种意图的得分
    
    参数:
        query (str): 输入的查询文本
    
    返回:
        dict[str, int]: 包含各种意图及其对应得分的字典
    """
    text = normalize_query_text(query)
    scores: dict[str, int] = {key: 0 for key in INTENT_MAP}

    for key, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text:
                scores[key] += max(1, len(keyword) // 2)

    if "分公司" in text and any(token in text for token in ("电话", "地址", "信访", "服务时间", "营业时间")):
        scores["branch"] += 4
    if "推荐" in text or "适合" in text:
        scores["recommended_product"] += 3

    for key, tokens, bonus in INTENT_BONUS_RULES:
        if any(token in text for token in tokens):
            scores[key] += bonus

    return scores

""" 将原始的意图得分字典处理成一个结构化的、按置信度排序的候选意图列表 """
def _build_candidates(scores: dict[str, int]) -> list[IntentCandidate]:
    total = sum(max(score, 0) for score in scores.values())
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    candidates: list[IntentCandidate] = []

    for key, score in ranked:
        if score <= 0:
            continue
        """ 计算得分有效的意图的置信度，置信度是该意图得分占总分 total 的比例，并四舍五入到小数点后四位。 """
        confidence = round(score / total, 4) if total > 0 else 0.0
        candidates.append(
            IntentCandidate(
                key=key,
                score=score,
                confidence=confidence,
                intent=INTENT_MAP[key],
            )
        )
    return candidates

""" 根据候选意图列表的状态，决定是否需要向用户请求确认，以确保意图识别的准确性.根据candidates来判断 """
def _needs_confirmation(candidates: list[IntentCandidate]) -> bool:
    if not candidates:
        return True
    if len(candidates) == 1:
        return candidates[0].confidence < 0.6

    best = candidates[0]
    second = candidates[1]
    if best.confidence < 0.55:
        return True
    if best.score - second.score <= 1:
        return True
    if best.confidence - second.confidence < 0.15:
        return True
    return False


def classify_query_intent(query: str) -> RetrievalIntent | None:
    result = classify_query_intent_with_scores(query)
    return result.intent


def classify_query_intent_with_scores(query: str) -> IntentRecognitionResult:
    text = normalize_query_text(query)
    scores = score_query_intents(query)
    candidates = _build_candidates(scores)
    best_candidate = candidates[0] if candidates else None
    confidence = best_candidate.confidence if best_candidate else 0.0
    intent = best_candidate.intent if best_candidate else None
    needs_confirmation = _needs_confirmation(candidates)
    return IntentRecognitionResult(
        intent=intent,
        scores=scores,
        normalized_query=text,
        confidence=confidence,
        candidates=candidates,
        needs_confirmation=needs_confirmation,
    )
