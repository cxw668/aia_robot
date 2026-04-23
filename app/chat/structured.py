from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel


class StructuredEvidence(BaseModel):
    title: str
    snippet: str
    score: float
    url: str = ""


class StructuredAction(BaseModel):
    label: str
    url: str = ""


class StructuredAnswer(BaseModel):
    summary: str
    evidence: list[StructuredEvidence]
    next_actions: list[StructuredAction]
    risk_tips: list[str]
    confidence: str


def build_structured_answer(
    answer: str,
    citations: Sequence[object],
    *,
    support_mode: bool,
    fallback_kind: str | None = None,
    clarification_options: Sequence[str] = (),
    context_topic: str = "",
) -> StructuredAnswer:
    summary = answer.strip() or "暂无回答。"
    evidence = [
        StructuredEvidence(
            title=_citation_value(citation, "title") or _citation_value(citation, "service_name") or "参考资料",
            snippet=_truncate(_citation_value(citation, "content"), 120),
            score=max(
                float(_citation_value(citation, "score") or 0.0),
                float(_citation_value(citation, "llm_score") or 0.0),
            ),
            url=_citation_value(citation, "service_url"),
        )
        for citation in citations[:3]
    ]

    next_actions = _build_next_actions(
        citations,
        support_mode=support_mode,
        fallback_kind=fallback_kind,
        clarification_options=clarification_options,
        context_topic=context_topic,
    )
    risk_tips = _build_risk_tips(
        support_mode=support_mode,
        has_evidence=bool(evidence),
        fallback_kind=fallback_kind,
    )

    return StructuredAnswer(
        summary=summary,
        evidence=evidence,
        next_actions=next_actions,
        risk_tips=risk_tips,
        confidence=_build_confidence(evidence),
    )


def _build_next_actions(
    citations: Sequence[object],
    *,
    support_mode: bool,
    fallback_kind: str | None,
    clarification_options: Sequence[str],
    context_topic: str,
) -> list[StructuredAction]:
    if fallback_kind == "clarify":
        actions: list[StructuredAction] = []
        if context_topic:
            actions.append(StructuredAction(label=f"确认是否继续咨询“{context_topic}”"))
        actions.extend(
            StructuredAction(label=f"补充{option}")
            for option in clarification_options[:4]
        )
        return actions[:4]

    actions: list[StructuredAction] = []
    seen_urls: set[str] = set()

    for citation in citations:
        url = _citation_value(citation, "service_url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        label_source = _citation_value(citation, "service_name") or _citation_value(citation, "title") or "官方入口"
        actions.append(
            StructuredAction(
                label=f"前往{label_source}相关入口继续查看或办理",
                url=url,
            )
        )
        if len(actions) >= 2:
            break

    if actions:
        return actions

    if support_mode:
        if fallback_kind == "handoff":
            return [
                StructuredAction(label="补充业务名称、保单类型或分公司后重新提问"),
                StructuredAction(label="如需进一步协助，可拨打友邦客服热线 95519"),
                StructuredAction(label="也可前往友邦官网继续查询", url="https://www.aia.com.cn"),
            ]
        return [
            StructuredAction(label="如需进一步协助，可拨打友邦客服热线 95519"),
            StructuredAction(label="也可前往友邦官网继续查询", url="https://www.aia.com.cn"),
        ]

    return [
        StructuredAction(label="如涉及保险条款或办理流程，请以友邦官方信息为准", url="https://www.aia.com.cn"),
    ]


def _build_risk_tips(*, support_mode: bool, has_evidence: bool, fallback_kind: str | None) -> list[str]:
    risk_tips: list[str] = []
    if support_mode:
        risk_tips.append("具体保障责任、费率、等待期及除外责任请以正式合同和官方说明为准。")
    else:
        risk_tips.append("当前为日常聊天模式，涉及保险条款等专业内容时请以官方信息为准。")

    if fallback_kind == "clarify":
        risk_tips.append("当前问题存在上下文省略或条件缺失，直接回答可能导致答非所问。")
    elif fallback_kind == "handoff":
        risk_tips.append("当前检索证据不足，建议补充业务信息或转人工确认。")

    if not has_evidence:
        risk_tips.append("当前回答缺少直接知识库证据，建议核对友邦官网或联系客服。")
    return risk_tips


def _build_confidence(evidence: Sequence[StructuredEvidence]) -> str:
    if not evidence:
        return "low"
    top_score = max(item.score for item in evidence)
    if top_score >= 0.85:
        return "high"
    if top_score >= 0.65:
        return "medium"
    return "low"


def _citation_value(citation: object, field: str) -> Any:
    if isinstance(citation, dict):
        return citation.get(field, "")
    return getattr(citation, field, "")


def _truncate(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."
