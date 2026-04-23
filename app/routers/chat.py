"""Chat router — DB-backed multi-turn RAG chat with SSE streaming.

Endpoints
---------
POST /chat            — standard JSON response (non-streaming)
POST /chat/stream     — SSE streaming response (text/event-stream)
DELETE /chat/{id}     — delete a session
GET  /chat/{id}/history — return message history
"""
from __future__ import annotations

import enum
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_json as cache_get_json, set_json as cache_set_json
from app.chat.context import (
    ChatContext,
    FallbackDecision,
    build_chat_context,
    build_context_system_note,
    build_support_fallback_decision,
    select_context_messages,
    rewrite_query_with_context,
)
from app.chat.index import chat_completion, chat_completion_stream
from app.chat.structured import StructuredAnswer, build_structured_answer
from app.config import settings
from app.database import ChatMessage, ChatSession, MessageRole, User, get_db
from app.knowledge_base.retrieval.engine import retrieve, retrieve_with_progress
from app.rate_limit import build_rate_limit_dependency
from app.request_context import get_request_id
from app.routers.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)
chat_rate_limit = build_rate_limit_dependency(
    scope="chat",
    limit=settings.chat_rate_limit_count,
    window_seconds=settings.chat_rate_limit_window_seconds,
    message="Too many chat requests. Please slow down and try again shortly.",
)

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_HISTORY_TURNS = 5   # keep last N user+assistant pairs in LLM context

SUPPORT_SYSTEM_PROMPT = (
    "你是友邦保险（AIA）的专业智能客服助手，名字叫小邦。\n"
    "职责：\n"
    "1. 严格依据提供的【知识库参考】内容回答用户问题，不得编造信息。\n"
    "2. 如知识库内容不足，请如实告知并建议用户拨打客服热线 95519 或前往官网 www.aia.com.cn。\n"
    "3. 保持上下文连贯，能理解用户在多轮对话中的指代（如“它”“这个”“上面提到的”等）。\n"
    "4. 回答简洁、准确，使用规范中文，适当使用段落和列表提升可读性。\n"
    "5. 涉及具体产品条款、费率等敏感信息时，提示用户以正式合同为准。"
)

CASUAL_SYSTEM_PROMPT = (
    "你是友邦保险（AIA）的智能助手，名字叫小邦。\n"
    "当前处于【日常聊天】模式，可以像自然、友好的中文助手一样与用户交流。\n"
    "要求：\n"
    "1. 优先直接理解并回答用户问题，保持自然、清晰、简洁。\n"
    "2. 不依赖知识库引用，可以进行一般性闲聊、说明和建议。\n"
    "3. 涉及医疗、法律、投资、保险条款等高风险或强专业内容时，明确说明仅供参考，并建议用户以官方信息或专业人士意见为准。"
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class ChatMode(str, enum.Enum):
    CASUAL = "casual"
    SUPPORT = "support"


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    top_k: int = 5
    category: str | None = None
    mode: ChatMode = ChatMode.SUPPORT


class Citation(BaseModel):
    title: str
    content: str
    score: float
    llm_score: float | None = None
    llm_verdict: str = ""
    service_name: str = ""
    service_url: str = ""
    collection: str = ""


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    structured_answer: StructuredAnswer
    session_id: str


@dataclass(frozen=True)
class PreparedChatTurn:
    user_message: str
    citations: list[Citation]
    cache_key: str
    cache_hit: bool
    cache_lookup_ms: float
    context: ChatContext
    fallback_decision: FallbackDecision | None = None
    cached_answer: str | None = None


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_user_session(
    db: AsyncSession,
    user_id: int,
    session_id: str,
) -> ChatSession | None:
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _load_session_messages(db: AsyncSession, session_id: str) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ── Context builders ──────────────────────────────────────────────────────────

def _get_system_prompt(mode: ChatMode) -> str:
    return CASUAL_SYSTEM_PROMPT if mode == ChatMode.CASUAL else SUPPORT_SYSTEM_PROMPT


def _trim_to_window(
    messages: list[ChatMessage],
    mode: ChatMode,
    *,
    query: str,
    context: ChatContext,
    context_note: str = "",
) -> list[dict]:
    """Convert DB messages to OpenAI format, keeping current system prompt + recent turns."""
    turns = select_context_messages(
        messages,
        query=query,
        context=context,
        max_turns=MAX_HISTORY_TURNS,
    )
    combined = [{"role": MessageRole.SYSTEM.value, "content": _get_system_prompt(mode)}]
    if context_note:
        combined.append({"role": MessageRole.SYSTEM.value, "content": context_note})
    combined.extend({"role": m.role.value, "content": m.content} for m in turns)
    return combined


def _build_user_message(query: str, docs: list[dict]) -> str:
    """Inject RAG context into the user turn."""
    if not docs:
        return query
    ctx_parts = []
    for i, d in enumerate(docs, 1):
        coll = f" [{d.get('collection', '')}]" if d.get("collection") else ""
        ctx_parts.append(f"[参考{i}]{coll} {d['title']}\n{d['content']}")
    context_block = "\n\n".join(ctx_parts)
    return (
        f"【知识库参考】\n{context_block}\n\n"
        f"【用户问题】\n{query}"
    )


def _build_citations(docs: list[dict]) -> list[Citation]:
    return [
        Citation(
            title=d["title"],
            content=d["content"],
            score=d["score"],
            llm_score=d.get("llm_score"),
            llm_verdict=d.get("llm_verdict", ""),
            service_name=d.get("service_name", ""),
            service_url=d.get("service_url", ""),
            collection=d.get("collection", ""),
        )
        for d in docs
    ]


def _serialize_citations(citations: list[Citation]) -> list[dict]:
    return [citation.model_dump() for citation in citations]


def _serialize_structured_answer(structured_answer: StructuredAnswer) -> dict:
    return structured_answer.model_dump()


def _sse_payload(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _progress_event(stage: str, label: str, detail: str = "") -> str:
    payload = {
        "type": "progress",
        "stage": stage,
        "label": label,
    }
    if detail:
        payload["detail"] = detail
    return _sse_payload(payload)


def _deserialize_citations(payload: object) -> list[Citation]:
    if not isinstance(payload, list):
        return []
    citations: list[Citation] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            citations.append(Citation(**item))
        except Exception:
            continue
    return citations


def _build_history_signature(history: list[dict]) -> str:
    normalized = [
        {
            "role": str(message.get("role", "")),
            "content": str(message.get("content", "")),
        }
        for message in history
    ]
    digest = hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return digest[:16]


def _build_structured_answer_for_response(
    answer: str,
    citations: list[Citation],
    mode: ChatMode,
    *,
    fallback_decision: FallbackDecision | None = None,
    context: ChatContext | None = None,
) -> StructuredAnswer:
    return build_structured_answer(
        answer,
        citations,
        support_mode=mode == ChatMode.SUPPORT,
        fallback_kind=fallback_decision.kind if fallback_decision else None,
        clarification_options=fallback_decision.clarification_options if fallback_decision else (),
        context_topic=context.topic if context else "",
    )


def _build_chat_cache_key(
    *,
    query: str,
    retrieval_query: str,
    mode: ChatMode,
    category: str | None,
    top_k: int,
    history: list[dict],
) -> str:
    # Include the rewritten retrieval query and recent history fingerprint so
    # short follow-up questions like "它怎么办" do not reuse an answer from a
    # different conversation context.
    payload = {
        "version": 1,
        "query": query.strip(),
        "retrieval_query": retrieval_query,
        "mode": mode.value,
        "category": category or "",
        "top_k": top_k,
        "history_signature": _build_history_signature(history),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"aia:chat:{digest}"


async def _load_cached_turn(cache_key: str) -> tuple[str, str, list[Citation]] | None:
    if not settings.chat_cache_enabled:
        return None
    cached = await cache_get_json(cache_key)
    if not isinstance(cached, dict):
        return None
    answer = cached.get("answer")
    user_message = cached.get("user_message")
    citations = _deserialize_citations(cached.get("citations"))
    if not isinstance(answer, str) or not isinstance(user_message, str):
        return None
    return answer, user_message, citations


async def _store_cached_turn(
    cache_key: str,
    *,
    answer: str,
    user_message: str,
    citations: list[Citation],
) -> None:
    if not settings.chat_cache_enabled:
        return
    await cache_set_json(
        cache_key,
        {
            "answer": answer,
            "user_message": user_message,
            "citations": _serialize_citations(citations),
        },
        settings.chat_cache_ttl_seconds,
    )


async def _prepare_chat_turn(
    req: ChatRequest,
    llm_messages: list[dict],
    context: ChatContext,
) -> PreparedChatTurn:
    retrieval_query = rewrite_query_with_context(req.query, context)
    cache_key = _build_chat_cache_key(
        query=req.query,
        retrieval_query=retrieval_query,
        mode=req.mode,
        category=req.category,
        top_k=req.top_k,
        history=llm_messages,
    )
    cache_started_at = time.perf_counter()
    cached = await _load_cached_turn(cache_key)
    cache_lookup_ms = (time.perf_counter() - cache_started_at) * 1000
    if cached:
        # Reuse the cached user_message together with the answer so persisted
        # history stays identical to the non-cached path.
        answer, user_message, citations = cached
        fallback_decision = (
            build_support_fallback_decision(
                req.query,
                citations,
                context,
                low_confidence_threshold=settings.chat_low_confidence_score,
            )
            if req.mode == ChatMode.SUPPORT
            else None
        )
        return PreparedChatTurn(
            user_message=req.query.strip() if fallback_decision else user_message,
            citations=citations,
            cache_key=cache_key,
            cache_hit=True,
            cache_lookup_ms=cache_lookup_ms,
            context=context,
            fallback_decision=fallback_decision,
            cached_answer=answer,
        )

    docs = (
        retrieve(retrieval_query, top_k=req.top_k, category=req.category)
        if req.mode == ChatMode.SUPPORT
        else []
    )
    citations = _build_citations(docs)
    fallback_decision = (
        build_support_fallback_decision(
            req.query,
            citations,
            context,
            low_confidence_threshold=settings.chat_low_confidence_score,
        )
        if req.mode == ChatMode.SUPPORT
        else None
    )
    return PreparedChatTurn(
        user_message=req.query.strip() if fallback_decision else _build_user_message(req.query, docs),
        citations=citations,
        cache_key=cache_key,
        cache_hit=False,
        cache_lookup_ms=cache_lookup_ms,
        context=context,
        fallback_decision=fallback_decision,
    )


def _create_user_message(session_id: str, user_message: str) -> ChatMessage:
    return ChatMessage(
        session_id=session_id,
        role=MessageRole.USER,
        content=user_message,
    )


def _create_assistant_message(
    session_id: str,
    answer: str,
    citations: list[Citation],
) -> ChatMessage:
    return ChatMessage(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=answer,
        citations=_serialize_citations(citations),
    )


def _log_chat_result(
    *,
    session_id: str,
    query: str,
    mode: ChatMode,
    cache_hit: bool,
    answer_source: str,
    citations_count: int,
    duration_ms: float,
    cache_lookup_ms: float,
) -> None:
    logger.info(
        "[chat] completed | request_id=%s | session_id=%s | mode=%s | query=%s | answer_source=%s | cache_hit=%s | citations=%s | cache_lookup_ms=%.1f | duration_ms=%.1f",
        get_request_id(),
        session_id,
        mode.value,
        query,
        answer_source,
        cache_hit,
        citations_count,
        cache_lookup_ms,
        duration_ms,
    )


# ── Standard (non-streaming) endpoint ─────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(chat_rate_limit),
) -> ChatResponse:
    """Multi-turn RAG chat with DB persistence (non-streaming)."""
    started_at = time.perf_counter()
    session_id = req.session_id or str(uuid.uuid4())
    session = await _get_user_session(db, current_user.id, session_id)
    if not session:
        session = ChatSession(id=session_id, user_id=current_user.id)
        db.add(session)
        await db.flush()

    history = await _load_session_messages(db, session.id)
    context = build_chat_context(history, max_turns=MAX_HISTORY_TURNS)
    llm_messages = _trim_to_window(
        history,
        req.mode,
        query=req.query,
        context=context,
        context_note=build_context_system_note(context) if req.mode == ChatMode.SUPPORT else "",
    )
    prepared_turn = await _prepare_chat_turn(req, llm_messages, context)

    db.add(_create_user_message(session.id, prepared_turn.user_message))
    llm_messages.append({"role": MessageRole.USER.value, "content": prepared_turn.user_message})

    if prepared_turn.fallback_decision is not None:
        answer = prepared_turn.fallback_decision.answer
        if not prepared_turn.cache_hit or prepared_turn.cached_answer != answer:
            await _store_cached_turn(
                prepared_turn.cache_key,
                answer=answer,
                user_message=prepared_turn.user_message,
                citations=prepared_turn.citations,
            )
    elif prepared_turn.cache_hit and prepared_turn.cached_answer is not None:
        answer = prepared_turn.cached_answer
    else:
        try:
            answer = chat_completion(llm_messages)
        except Exception as exc:
            logger.exception("[chat] llm call failed | request_id=%s", get_request_id(), exc_info=exc)
            raise HTTPException(status_code=502, detail="聊天模型调用失败，请稍后重试。") from exc
        await _store_cached_turn(
            prepared_turn.cache_key,
            answer=answer,
            user_message=prepared_turn.user_message,
            citations=prepared_turn.citations,
        )

    db.add(_create_assistant_message(session.id, answer, prepared_turn.citations))
    session.last_message_at = datetime.utcnow()
    if not session.title:
        session.title = req.query[:20]

    _log_chat_result(
        session_id=session.id,
        query=req.query,
        mode=req.mode,
        cache_hit=prepared_turn.cache_hit,
        answer_source=(
            "fallback_cache"
            if prepared_turn.fallback_decision is not None and prepared_turn.cache_hit
            else "fallback"
            if prepared_turn.fallback_decision is not None
            else "cache"
            if prepared_turn.cache_hit
            else "llm"
        ),
        citations_count=len(prepared_turn.citations),
        duration_ms=(time.perf_counter() - started_at) * 1000,
        cache_lookup_ms=prepared_turn.cache_lookup_ms,
    )
    structured_answer = _build_structured_answer_for_response(
        answer,
        prepared_turn.citations,
        req.mode,
        fallback_decision=prepared_turn.fallback_decision,
        context=prepared_turn.context,
    )
    return ChatResponse(
        answer=answer,
        citations=prepared_turn.citations,
        structured_answer=structured_answer,
        session_id=session.id,
    )


# ── Streaming SSE endpoint ────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(chat_rate_limit),
) -> StreamingResponse:
    """Multi-turn RAG chat with SSE streaming response.

    SSE event format::

        data: {"type": "citations", "citations": [...], "session_id": "..."}
        data: {"type": "delta", "text": "..."}
        data: {"type": "done"}
    """
    started_at = time.perf_counter()
    session_id = req.session_id or str(uuid.uuid4())
    session = await _get_user_session(db, current_user.id, session_id)
    if not session:
        session = ChatSession(id=session_id, user_id=current_user.id)
        db.add(session)
        await db.flush()

    history = await _load_session_messages(db, session.id)
    context = build_chat_context(history, max_turns=MAX_HISTORY_TURNS)
    llm_messages = _trim_to_window(
        history,
        req.mode,
        query=req.query,
        context=context,
        context_note=build_context_system_note(context) if req.mode == ChatMode.SUPPORT else "",
    )

    async def event_generator():
        retrieval_query = rewrite_query_with_context(req.query, context)
        cache_key = _build_chat_cache_key(
            query=req.query,
            retrieval_query=retrieval_query,
            mode=req.mode,
            category=req.category,
            top_k=req.top_k,
            history=llm_messages,
        )

        yield _progress_event(
            "context_ready",
            "已整理多轮上下文",
            f"当前纳入 {max(len(llm_messages) - 1, 0)} 条历史消息",
        )
        yield _progress_event("cache_lookup_start", "正在检查会话缓存")
        cache_started_at = time.perf_counter()
        cached = await _load_cached_turn(cache_key)
        cache_lookup_ms = (time.perf_counter() - cache_started_at) * 1000

        citations: list[Citation] = []
        fallback_decision: FallbackDecision | None = None
        cache_hit = False
        cached_answer: str | None = None
        user_message = req.query.strip()

        if cached:
            cached_answer, cached_user_message, citations = cached
            cache_hit = True
            fallback_decision = (
                build_support_fallback_decision(
                    req.query,
                    citations,
                    context,
                    low_confidence_threshold=settings.chat_low_confidence_score,
                )
                if req.mode == ChatMode.SUPPORT
                else None
            )
            user_message = req.query.strip() if fallback_decision else cached_user_message
            yield _progress_event(
                "cache_hit",
                "命中会话缓存",
                f"耗时 {cache_lookup_ms:.0f} ms，直接复用历史答案",
            )
        else:
            yield _progress_event(
                "cache_miss",
                "缓存未命中",
                f"耗时 {cache_lookup_ms:.0f} ms，开始检索知识库",
            )
            docs: list[dict] = []
            if req.mode == ChatMode.SUPPORT:
                for step in retrieve_with_progress(
                    retrieval_query,
                    top_k=req.top_k,
                    category=req.category,
                ):
                    step_type = str(step.get("type", ""))
                    if step_type == "embedding_start":
                        yield _progress_event("embedding_start", "正在编码查询向量")
                    elif step_type == "embedding_done":
                        yield _progress_event(
                            "embedding_done",
                            "已完成查询向量编码",
                            f"耗时 {float(step.get('duration_ms') or 0.0):.0f} ms",
                        )
                    elif step_type == "vector_search_start":
                        yield _progress_event(
                            "vector_search_start",
                            "正在查询向量库候选文档",
                            f"候选上限 {int(step.get('candidate_limit') or 0)} 条",
                        )
                    elif step_type == "vector_search_done":
                        yield _progress_event(
                            "vector_search_done",
                            "向量库已返回候选文档",
                            f"候选 {int(step.get('candidate_hits') or 0)} 条",
                        )
                    elif step_type == "rerank_start":
                        yield _progress_event(
                            "rerank_start",
                            "正在进行 LLM 重排",
                            f"重排候选 {int(step.get('candidate_hits') or 0)} 条",
                        )
                    elif step_type == "rerank_done":
                        strategy = str(step.get("strategy") or "")
                        label = (
                            "LLM 重排完成"
                            if strategy.startswith("llm_rerank")
                            else "已回退向量排序结果"
                        )
                        yield _progress_event(
                            "rerank_done",
                            label,
                            f"当前策略 {strategy or 'vector_fallback'}",
                        )
                    elif step_type == "complete":
                        docs = list(step.get("hits") or [])
                        yield _progress_event(
                            "retrieval_done",
                            "检索阶段完成",
                            f"策略 {step.get('strategy') or 'unknown'}，命中 {int(step.get('hit_count') or 0)} 条",
                        )
            citations = _build_citations(docs)
            fallback_decision = (
                build_support_fallback_decision(
                    req.query,
                    citations,
                    context,
                    low_confidence_threshold=settings.chat_low_confidence_score,
                )
                if req.mode == ChatMode.SUPPORT
                else None
            )
            user_message = req.query.strip() if fallback_decision else _build_user_message(req.query, docs)

        db.add(_create_user_message(session.id, user_message))
        llm_messages.append({"role": MessageRole.USER.value, "content": user_message})
        session.last_message_at = datetime.utcnow()
        if not session.title:
            session.title = req.query[:20]
        await db.flush()

        if fallback_decision is not None:
            answer = fallback_decision.answer
            yield _progress_event("fallback", "依据不足，转入低置信兜底")
            db.add(_create_assistant_message(session.id, answer, citations))
            if not cache_hit or cached_answer != answer:
                await _store_cached_turn(
                    cache_key,
                    answer=answer,
                    user_message=user_message,
                    citations=citations,
                )
            try:
                await db.commit()
            except Exception:
                await db.rollback()

            _log_chat_result(
                session_id=session.id,
                query=req.query,
                mode=req.mode,
                cache_hit=cache_hit,
                answer_source="fallback_cache" if cache_hit else "fallback",
                citations_count=len(citations),
                duration_ms=(time.perf_counter() - started_at) * 1000,
                cache_lookup_ms=cache_lookup_ms,
            )
            structured_answer = _build_structured_answer_for_response(
                answer,
                citations,
                req.mode,
                fallback_decision=fallback_decision,
                context=context,
            )
            yield _sse_payload(
                {"type": "citations", "citations": _serialize_citations(citations), "session_id": session.id}
            )
            yield _sse_payload({"type": "delta", "text": answer})
            yield _sse_payload(
                {"type": "structured", "structured_answer": _serialize_structured_answer(structured_answer)}
            )
            yield _sse_payload({"type": "done"})
            return

        if cache_hit and cached_answer is not None:
            yield _progress_event("cache_answer", "已从缓存返回答案")
            db.add(_create_assistant_message(session.id, cached_answer, citations))
            try:
                await db.commit()
            except Exception:
                await db.rollback()

            _log_chat_result(
                session_id=session.id,
                query=req.query,
                mode=req.mode,
                cache_hit=True,
                answer_source="cache",
                citations_count=len(citations),
                duration_ms=(time.perf_counter() - started_at) * 1000,
                cache_lookup_ms=cache_lookup_ms,
            )
            structured_answer = _build_structured_answer_for_response(
                cached_answer,
                citations,
                req.mode,
                context=context,
            )
            yield _sse_payload(
                {"type": "citations", "citations": _serialize_citations(citations), "session_id": session.id}
            )
            yield _sse_payload({"type": "delta", "text": cached_answer})
            yield _sse_payload(
                {"type": "structured", "structured_answer": _serialize_structured_answer(structured_answer)}
            )
            yield _sse_payload({"type": "done"})
            return

        yield _progress_event(
            "generation_start",
            "已整理知识依据，开始生成回答",
            f"将引用 {len(citations)} 条知识依据",
        )
        yield _sse_payload(
            {"type": "citations", "citations": _serialize_citations(citations), "session_id": session.id}
        )

        full_answer: list[str] = []
        try:
            for chunk in chat_completion_stream(llm_messages):
                full_answer.append(chunk)
                yield _sse_payload({"type": "delta", "text": chunk})
        except Exception as exc:
            logger.exception("[chat] streaming llm call failed | request_id=%s", get_request_id(), exc_info=exc)
            yield _sse_payload(
                {
                    "type": "error",
                    "code": "upstream_error",
                    "message": "聊天模型调用失败，请稍后重试。",
                    "request_id": get_request_id(),
                }
            )
            return

        answer_text = "".join(full_answer)
        structured_answer = _build_structured_answer_for_response(
            answer_text,
            citations,
            req.mode,
            context=context,
        )
        db.add(_create_assistant_message(session.id, answer_text, citations))
        await _store_cached_turn(
            cache_key,
            answer=answer_text,
            user_message=user_message,
            citations=citations,
        )
        try:
            await db.commit()
        except Exception:
            await db.rollback()

        _log_chat_result(
            session_id=session.id,
            query=req.query,
            mode=req.mode,
            cache_hit=False,
            answer_source="llm_stream",
            citations_count=len(citations),
            duration_ms=(time.perf_counter() - started_at) * 1000,
            cache_lookup_ms=cache_lookup_ms,
        )
        yield _progress_event("generation_done", "回答生成完成")
        yield _sse_payload(
            {"type": "structured", "structured_answer": _serialize_structured_answer(structured_answer)}
        )
        yield _sse_payload({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Session management endpoints ──────────────────────────────────────────────

@router.delete("/{session_id}")
async def clear_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete a conversation session (and all its messages)."""
    session = await _get_user_session(db, current_user.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    return {"status": "cleared", "session_id": session_id}


@router.get("/{session_id}/history")
async def get_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return message history for a session (excludes system messages)."""
    session = await _get_user_session(db, current_user.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = await _load_session_messages(db, session_id)
    msgs = [
        {"role": m.role.value, "content": m.content}
        for m in rows
        if m.role != MessageRole.SYSTEM
    ]
    return {"session_id": session_id, "messages": msgs}
