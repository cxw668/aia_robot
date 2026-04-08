"""过滤器构建逻辑（从 retrieval_data_source 迁移）。"""
from __future__ import annotations

from qdrant_client.http import models as qmodels

from app.knowledge_base.models.intent import RetrievalIntent
from app.knowledge_base.processing.normalizer import (
    category_matches,
    normalize_category,
)
from app.knowledge_base.core.vector_store import (
    _match_any_condition,
    get_available_categories,
)


def build_filter(
    intent: RetrievalIntent | None,
    only_on_sale: bool = False,
    category: str | None = None,
) -> qmodels.Filter | None:
    """根据用户意图、显式分类和在售状态动态创建过滤器对象。"""
    must: list[qmodels.FieldCondition] = []
    should: list[qmodels.FieldCondition] = []
    available_categories: set[str] = set()

    if intent and intent.schemas:
        must.append(qmodels.FieldCondition(key="schema", match=qmodels.MatchAny(any=list(intent.schemas))))

    if only_on_sale or (intent and intent.only_on_sale):
        must.append(qmodels.FieldCondition(key="product_status", match=qmodels.MatchValue(value="在售")))

    normalized_category = normalize_category(category)
    if normalized_category:
        try:
            available_categories = get_available_categories()
        except Exception:
            available_categories = set()

        matched_categories = sorted(
            candidate for candidate in available_categories if category_matches(candidate, normalized_category)
        )
        category_values = matched_categories or [normalized_category]
        if len(category_values) == 1:
            must.append(
                qmodels.FieldCondition(
                    key="category",
                    match=qmodels.MatchValue(value=category_values[0]),
                )
            )
        else:
            must.append(
                qmodels.FieldCondition(
                    key="category",
                    match=qmodels.MatchAny(any=category_values),
                )
            )

    if intent and intent.categories:
        try:
            if not available_categories:
                available_categories = get_available_categories()
            filtered = [c for c in intent.categories if c in available_categories]
        except Exception:
            filtered = list(intent.categories)
        if filtered:
            should.extend(_match_any_condition("category", tuple(filtered)))

    if intent and intent.key == "form":
        should.extend(_match_any_condition("category", ("表单下载",)))
        try:
            should.append(qmodels.FieldCondition(key="title", match=qmodels.MatchValue(value="理赔申请")))
        except Exception:
            pass

    if not must and not should:
        return None
    return qmodels.Filter(must=must, should=should or None)


__all__ = ["build_filter"]
