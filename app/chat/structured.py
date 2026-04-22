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
) -> StructuredAnswer:
    summary = answer.strip() or "暂无回答。"
    evidence = [
        StructuredEvidence(
            title=_citation_value(citation, "title") or _citation_value(citation, "service_name") or "参考资料",
            snippet=_truncate(_citation_value(citation, "content"), 120),
            score=float(_citation_value(citation, "score") or 0.0),
            url=_citation_value(citation, "service_url"),
        )
        for citation in citations[:3]
    ]

    next_actions = _build_next_actions(citations, support_mode=support_mode)
    risk_tips = _build_risk_tips(support_mode=support_mode, has_evidence=bool(evidence))

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
) -> list[StructuredAction]:
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
        return [
            StructuredAction(label="如需进一步协助，可拨打友邦客服热线 95519"),
            StructuredAction(label="也可前往友邦官网继续查询", url="https://www.aia.com.cn"),
        ]

    return [
        StructuredAction(label="如涉及保险条款或办理流程，请以友邦官方信息为准", url="https://www.aia.com.cn"),
    ]


def _build_risk_tips(*, support_mode: bool, has_evidence: bool) -> list[str]:
    risk_tips: list[str] = []
    if support_mode:
        risk_tips.append("具体保障责任、费率、等待期及除外责任请以正式合同和官方说明为准。")
    else:
        risk_tips.append("当前为日常聊天模式，涉及保险条款等专业内容时请以官方信息为准。")

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
