"""意图分类逻辑（从 intent_recognition 迁移）。"""
from __future__ import annotations

from app.knowledge_base.models.intent import (
    RetrievalIntent,
    IntentCandidate,
    IntentRecognitionResult,
)
from app.knowledge_base.intent.rules import (
    INTENT_BONUS_RULES,
    INTENT_KEYWORDS,
    INTENT_MAP,
    normalize_query_text,
)


def score_query_intents(query: str) -> dict[str, int]:
    """根据查询文本计算各种意图的得分。"""
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


def _build_candidates(scores: dict[str, int]) -> list[IntentCandidate]:
    total = sum(max(score, 0) for score in scores.values())
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    candidates: list[IntentCandidate] = []
    for key, score in ranked:
        if score <= 0:
            continue
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


__all__ = [
    "score_query_intents",
    "classify_query_intent",
    "classify_query_intent_with_scores",
]
