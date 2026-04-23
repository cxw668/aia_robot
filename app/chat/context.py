from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.database import ChatMessage, MessageRole

PRONOUN_HINTS = ("它", "这个", "那个", "上面", "之前", "刚才", "该", "其", "这些", "那些")
GENERIC_FOLLOW_UP_HINTS = (
    "怎么办",
    "怎么弄",
    "怎么操作",
    "怎么申请",
    "怎么下",
    "怎么下载",
    "入口",
    "链接",
    "流程",
    "材料",
    "条件",
    "步骤",
    "要什么",
)
DEFAULT_CLARIFICATION_OPTIONS = ("办理条件", "所需材料", "下载入口", "申请流程")


@dataclass(frozen=True)
class ChatContext:
    topic: str = ""
    service_name: str = ""
    service_url: str = ""
    collection: str = ""
    last_user_query: str = ""
    recent_user_queries: tuple[str, ...] = ()
    summary: str = ""
    clarification_options: tuple[str, ...] = DEFAULT_CLARIFICATION_OPTIONS

    @property
    def has_topic(self) -> bool:
        return bool(self.topic or self.service_name)


@dataclass(frozen=True)
class FallbackDecision:
    answer: str
    kind: str
    clarification_options: tuple[str, ...] = ()


def build_chat_context(messages: Sequence[ChatMessage], *, max_turns: int) -> ChatContext:
    turns = [message for message in messages if message.role != MessageRole.SYSTEM]
    if max_turns > 0:
        turns = turns[-(max_turns * 2):]

    recent_user_queries = tuple(
        query
        for query in (_extract_user_query(message.content) for message in turns if message.role == MessageRole.USER)
        if query
    )[-3:]
    last_user_query = recent_user_queries[-1] if recent_user_queries else ""

    topic = ""
    service_name = ""
    service_url = ""
    collection = ""
    clarification_options = DEFAULT_CLARIFICATION_OPTIONS

    for message in reversed(turns):
        if message.role != MessageRole.ASSISTANT:
            continue
        citations = _extract_citations(message.citations)
        if not citations:
            continue
        citation = citations[0]
        topic = _clean_topic(str(citation.get("title") or citation.get("service_name") or ""))
        service_name = _clean_topic(str(citation.get("service_name") or citation.get("title") or ""))
        service_url = str(citation.get("service_url") or "").strip()
        collection = str(citation.get("collection") or "").strip()
        clarification_options = _build_clarification_options(topic or service_name)
        break

    if not topic:
        topic = _infer_topic_from_queries(recent_user_queries)
        clarification_options = _build_clarification_options(topic)

    summary_parts: list[str] = []
    if topic:
        summary_parts.append(f"当前主话题：{topic}")
    if last_user_query:
        summary_parts.append(f"上一轮用户问题：{last_user_query}")
    if service_name and service_name != topic:
        summary_parts.append(f"相关服务：{service_name}")
    if len(recent_user_queries) >= 2:
        summary_parts.append(f"最近追问：{' -> '.join(recent_user_queries[-2:])}")

    return ChatContext(
        topic=topic,
        service_name=service_name,
        service_url=service_url,
        collection=collection,
        last_user_query=last_user_query,
        recent_user_queries=recent_user_queries,
        summary="；".join(part for part in summary_parts if part)[:220],
        clarification_options=clarification_options,
    )


def select_context_messages(
    messages: Sequence[ChatMessage],
    *,
    query: str,
    context: ChatContext,
    max_turns: int,
) -> list[ChatMessage]:
    if max_turns <= 0:
        return []

    turns = _group_messages_into_turns(messages)
    if len(turns) <= max_turns:
        return [message for turn in turns for message in turn]

    pinned_turn_indexes = {len(turns) - 1}
    remaining_slots = max_turns - len(pinned_turn_indexes)
    ranked_turns = sorted(
        (
            (
                _score_turn(turn, turn_index=turn_index, total_turns=len(turns), query=query, context=context),
                turn_index,
            )
            for turn_index, turn in enumerate(turns)
            if turn_index not in pinned_turn_indexes
        ),
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )

    selected_turn_indexes = set(pinned_turn_indexes)
    for _, turn_index in ranked_turns[: max(remaining_slots, 0)]:
        selected_turn_indexes.add(turn_index)

    selected_messages: list[ChatMessage] = []
    for turn_index, turn in enumerate(turns):
        if turn_index in selected_turn_indexes:
            selected_messages.extend(turn)
    return selected_messages


def build_context_system_note(context: ChatContext) -> str:
    if not context.summary:
        return ""

    note_parts = [f"【对话上下文摘要】\n{context.summary}"]
    if context.has_topic:
        slots = [f"主题={context.topic or context.service_name}"]
        if context.service_name:
            slots.append(f"服务={context.service_name}")
        if context.collection:
            slots.append(f"知识库={context.collection}")
        note_parts.append(f"【已识别槽位】\n{'；'.join(slots)}")
    return "\n\n".join(note_parts)


def rewrite_query_with_context(query: str, context: ChatContext) -> str:
    normalized_query = query.strip()
    if not normalized_query or not context.has_topic:
        return normalized_query

    if _contains_explicit_topic(normalized_query, context):
        return normalized_query

    if not is_ambiguous_query(normalized_query, context):
        return normalized_query

    prefixes = [value for value in (context.topic, context.service_name) if value]
    rewritten = " ".join(prefixes + [normalized_query]).strip()
    return rewritten[:160]


def build_support_fallback_decision(
    query: str,
    citations: Sequence[object],
    context: ChatContext,
    *,
    low_confidence_threshold: float,
) -> FallbackDecision | None:
    top_score = max((_citation_score(citation) for citation in citations), default=0.0)
    if citations and top_score >= low_confidence_threshold:
        return None

    if is_ambiguous_query(query, context):
        return FallbackDecision(
            answer=_build_clarification_answer(context),
            kind="clarify",
            clarification_options=context.clarification_options,
        )

    return FallbackDecision(
        answer=_build_handoff_answer(),
        kind="handoff",
    )


def is_ambiguous_query(query: str, context: ChatContext) -> bool:
    normalized_query = query.strip()
    if not normalized_query:
        return True

    if any(hint in normalized_query for hint in PRONOUN_HINTS):
        return True

    explicit_topic = _contains_explicit_topic(normalized_query, context)
    short_query = len(normalized_query) <= 16
    generic_follow_up = any(hint in normalized_query for hint in GENERIC_FOLLOW_UP_HINTS)
    return short_query and generic_follow_up and not explicit_topic


def _build_clarification_answer(context: ChatContext) -> str:
    options = "、".join(context.clarification_options[:4])
    if context.topic:
        return (
            f"我理解您可能在继续咨询“{context.topic}”，但这一问还缺少关键限定信息。"
            f"请补充您想确认的是{options}；如果方便，也可以直接说明保单类型、表单名称或所在分公司。"
        )
    return (
        "这个问题目前还不够具体。请补充您要咨询的业务名称、产品/表单名称、办理环节或所在分公司，"
        f"例如说明想确认的是{options}，我再继续帮您查。"
    )


def _build_handoff_answer() -> str:
    return (
        "我暂时没有从当前知识库里找到足够直接的依据来准确回答这个问题。"
        "建议您补充业务名称、保单类型、表单名称或所在分公司后再问；"
        "如需尽快确认，请拨打友邦客服热线 95519 或前往官网 www.aia.com.cn。"
    )


def _extract_user_query(content: str) -> str:
    text = str(content or "").strip()
    if "【用户问题】" in text:
        return text.split("【用户问题】", 1)[-1].strip()
    return text


def _extract_citations(payload: object) -> list[dict]:
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _clean_topic(value: str) -> str:
    return value.strip().strip("。！？!?；;：:")


def _infer_topic_from_queries(queries: Sequence[str]) -> str:
    for query in reversed(queries):
        cleaned = _clean_topic(query)
        if not cleaned:
            continue
        if len(cleaned) <= 16 and any(hint in cleaned for hint in GENERIC_FOLLOW_UP_HINTS):
            continue
        return cleaned[:40]
    return ""


def _build_clarification_options(topic: str) -> tuple[str, ...]:
    if "表单" in topic:
        return ("适用范围", "下载入口", "填写要求", "提交方式")
    if "分公司" in topic:
        return ("网点地址", "联系电话", "营业时间", "办理范围")
    if "产品" in topic:
        return ("保障责任", "适用人群", "投保条件", "官方资料")
    return DEFAULT_CLARIFICATION_OPTIONS


def _contains_explicit_topic(query: str, context: ChatContext) -> bool:
    for candidate in (context.topic, context.service_name):
        if len(candidate) >= 2 and candidate in query:
            return True
    return False


def _citation_score(citation: object) -> float:
    if isinstance(citation, dict):
        value = citation.get("score", 0.0)
    else:
        value = getattr(citation, "score", 0.0)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _group_messages_into_turns(messages: Sequence[ChatMessage]) -> list[list[ChatMessage]]:
    turns: list[list[ChatMessage]] = []
    pending_user: ChatMessage | None = None

    for message in messages:
        if message.role == MessageRole.SYSTEM:
            continue
        if message.role == MessageRole.USER:
            if pending_user is not None:
                turns.append([pending_user])
            pending_user = message
            continue
        if pending_user is not None:
            turns.append([pending_user, message])
            pending_user = None
        else:
            turns.append([message])

    if pending_user is not None:
        turns.append([pending_user])
    return turns


def _score_turn(
    turn: Sequence[ChatMessage],
    *,
    turn_index: int,
    total_turns: int,
    query: str,
    context: ChatContext,
) -> float:
    score = (turn_index + 1) / max(total_turns, 1)
    turn_text = _build_turn_text(turn)
    primary_terms = {value for value in (context.topic, context.service_name) if value}
    for term in _build_relevance_terms(query, context):
        if term in turn_text:
            score += 2.5 if term in primary_terms else 0.8
    if any(message.role == MessageRole.ASSISTANT and _extract_citations(message.citations) for message in turn):
        score += 0.2
    return score


def _build_turn_text(turn: Sequence[ChatMessage]) -> str:
    parts: list[str] = []
    for message in turn:
        parts.append(_extract_user_query(message.content))
        if message.role != MessageRole.ASSISTANT:
            continue
        for citation in _extract_citations(message.citations):
            for field in ("title", "service_name", "content"):
                value = str(citation.get(field) or "").strip()
                if value:
                    parts.append(value)
    return "\n".join(parts)


def _build_relevance_terms(query: str, context: ChatContext) -> tuple[str, ...]:
    terms: list[str] = []
    for candidate in (context.topic, context.service_name):
        cleaned = _clean_topic(candidate)
        if len(cleaned) >= 2 and cleaned not in terms:
            terms.append(cleaned)

    if not is_ambiguous_query(query, context) or _contains_explicit_topic(query, context):
        for candidate in _extract_match_terms(query):
            if candidate not in terms:
                terms.append(candidate)
    return tuple(terms)


def _extract_match_terms(text: str) -> list[str]:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", text or "")
    if len(normalized) < 2:
        return []

    stop_terms = {
        "怎么",
        "如何",
        "请问",
        "可以",
        "现在",
        "哪里",
        "什么",
        "这个",
        "那个",
        "一下",
        "办理",
        "申请",
        "下载",
        "查询",
        "多少",
    }
    terms: list[str] = []
    seen: set[str] = set()
    max_length = min(4, len(normalized))
    for length in range(max_length, 1, -1):
        for index in range(0, len(normalized) - length + 1):
            candidate = normalized[index:index + length]
            if candidate in stop_terms or candidate in seen:
                continue
            if any(candidate in pronoun for pronoun in PRONOUN_HINTS):
                continue
            seen.add(candidate)
            terms.append(candidate)
    return terms[:12]
