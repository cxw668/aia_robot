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
class IntentRecognitionResult:
    intent: RetrievalIntent | None
    scores: dict[str, int]
    normalized_query: str


def score_query_intents(query: str) -> dict[str, int]:
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


def classify_query_intent(query: str) -> RetrievalIntent | None:
    result = classify_query_intent_with_scores(query)
    return result.intent


def classify_query_intent_with_scores(query: str) -> IntentRecognitionResult:
    text = normalize_query_text(query)
    scores = score_query_intents(query)
    best_key = max(scores, key=scores.get)
    intent = INTENT_MAP[best_key] if scores[best_key] > 0 else None
    return IntentRecognitionResult(intent=intent, scores=scores, normalized_query=text)
