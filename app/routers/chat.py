"""Chat router — DB-backed multi-turn RAG chat with SSE streaming.

Endpoints
---------
POST /chat            — standard JSON response (non-streaming)
POST /chat/stream     — SSE streaming response (text/event-stream)
DELETE /chat/{id}     — delete a session
GET  /chat/{id}/history — return message history
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.index import chat_completion, chat_completion_stream
from app.database import ChatMessage, ChatSession, MessageRole, User, get_db
from app.knowledge_base.retrieval.engine import retrieve
from app.routers.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_HISTORY_TURNS = 5   # keep last N user+assistant pairs in LLM context

SYSTEM_PROMPT = (
    "你是友邦保险（AIA）的专业智能客服助手，名字叫小邦。\n"
    "职责：\n"
    "1. 严格依据提供的【知识库参考】内容回答用户问题，不得编造信息。\n"
    "2. 如知识库内容不足，请如实告知并建议用户拨打客服热线 95519 或前往官网 www.aia.com.cn。\n"
    "3. 保持上下文连贯，能理解用户在多轮对话中的指代（如“它”“这个”“上面提到的”等）。\n"
    "4. 回答简洁、准确，使用规范中文，适当使用段落和列表提升可读性。\n"
    "5. 涉及具体产品条款、费率等敏感信息时，提示用户以正式合同为准。"
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    top_k: int = 5
    category: str | None = None


class Citation(BaseModel):
    title: str
    content: str
    score: float
    service_name: str = ""
    service_url: str = ""
    collection: str = ""


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    session_id: str


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

def _trim_to_window(messages: list[ChatMessage]) -> list[dict]:
    """Convert DB messages to OpenAI format, keeping system + last MAX_HISTORY_TURNS pairs."""
    system = [m for m in messages if m.role == MessageRole.SYSTEM]
    turns = [m for m in messages if m.role != MessageRole.SYSTEM]
    # Keep only the last MAX_HISTORY_TURNS * 2 turn messages
    turns = turns[-(MAX_HISTORY_TURNS * 2):]
    combined = system + turns
    return [{"role": m.role.value, "content": m.content} for m in combined]


def _rewrite_query_with_history(query: str, history: list[dict]) -> str:
    """Prepend recent context summary to help retrieval when query contains pronouns.

    If the last assistant message exists and the query is short / contains
    pronouns, prefix the query with the last topic for better vector search.
    """
    pronoun_hints = ["它", "这个", "那个", "上面", "之前", "刚才", "该", "其", "这些", "那些"]
    has_pronoun = any(p in query for p in pronoun_hints)
    if not has_pronoun or len(query) > 40:
        return query

    # Find last user message to extract topic
    for msg in reversed(history):
        if msg["role"] == "user":
            prev = msg["content"]
            # Strip injected RAG block from previous user message
            if "【用户问题】" in prev:
                prev = prev.split("【用户问题】")[-1].strip()
            elif "【知识库参考】" in prev:
                prev = prev.split("【用户问题】")[-1].strip() if "【用户问题】" in prev else query
            # Combine previous context + current query for retrieval
            combined = f"{prev} {query}"
            return combined[:120]  # cap length
    return query


def _build_user_message(query: str, docs: list[dict]) -> str:
    """Inject RAG context into the user turn."""
    if not docs:
        return query
    ctx_parts = []
    for i, d in enumerate(docs, 1):
        coll = f" [{d.get('collection','')}]" if d.get("collection") else ""
        ctx_parts.append(f"[参考{i}]{coll} {d['title']}\n{d['content']}")
    context_block = "\n\n".join(ctx_parts)
    return (
        f"【知识库参考】\n{context_block}\n\n"
        f"【用户问题】\n{query}"
    )


# ── Standard (non-streaming) endpoint ─────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """Multi-turn RAG chat with DB persistence (non-streaming)."""
    session_id = req.session_id or str(uuid.uuid4())
    session = await _get_user_session(db, current_user.id, session_id)
    if not session:
        session = ChatSession(id=session_id, user_id=current_user.id)
        db.add(session)
        await db.flush()

    history = await _load_session_messages(db, session.id)

    # Init system prompt on first turn
    if not history:
        sys_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.SYSTEM,
            content=SYSTEM_PROMPT,
        )
        db.add(sys_msg)
        history = [sys_msg]

    # Build LLM context window
    llm_messages = _trim_to_window(history)

    # Rewrite query for retrieval (co-reference resolution)
    retrieval_query = _rewrite_query_with_history(req.query, llm_messages)

    # Retrieve relevant docs
    docs = retrieve(retrieval_query, top_k=req.top_k, category=req.category)
    citations = [
        Citation(
            title=d["title"],
            content=d["content"],
            score=d["score"],
            service_name=d.get("service_name", ""),
            service_url=d.get("service_url", ""),
            collection=d.get("collection", ""),
        )
        for d in docs
    ]

    # Build user message with RAG context injected
    user_message = _build_user_message(req.query, docs)

    # Persist user turn
    user_msg = ChatMessage(
        session_id=session.id,
        role=MessageRole.USER,
        content=user_message,
    )
    db.add(user_msg)
    llm_messages.append({"role": MessageRole.USER.value, "content": user_message})

    # Call LLM
    try:
        answer = chat_completion(llm_messages)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Persist assistant turn
    assistant_msg = ChatMessage(
        session_id=session.id,
        role=MessageRole.ASSISTANT,
        content=answer,
        citations=[c.model_dump() for c in citations],
    )
    db.add(assistant_msg)

    # Update session metadata
    session.last_message_at = datetime.utcnow()
    if not session.title:
        session.title = req.query[:20]

    return ChatResponse(answer=answer, citations=citations, session_id=session.id)


# ── Streaming SSE endpoint ────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Multi-turn RAG chat with SSE streaming response.

    SSE event format::

        data: {"type": "citations", "citations": [...], "session_id": "..."}
        data: {"type": "delta", "text": "..."}
        data: {"type": "done"}
    """
    session_id = req.session_id or str(uuid.uuid4())
    session = await _get_user_session(db, current_user.id, session_id)
    if not session:
        session = ChatSession(id=session_id, user_id=current_user.id)
        db.add(session)
        await db.flush()

    history = await _load_session_messages(db, session.id)

    if not history:
        sys_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.SYSTEM,
            content=SYSTEM_PROMPT,
        )
        db.add(sys_msg)
        history = [sys_msg]

    llm_messages = _trim_to_window(history)
    retrieval_query = _rewrite_query_with_history(req.query, llm_messages)

    docs = retrieve(retrieval_query, top_k=req.top_k, category=req.category)
    citations = [
        Citation(
            title=d["title"],
            content=d["content"],
            score=d["score"],
            service_name=d.get("service_name", ""),
            service_url=d.get("service_url", ""),
            collection=d.get("collection", ""),
        )
        for d in docs
    ]

    user_message = _build_user_message(req.query, docs)
    user_msg = ChatMessage(
        session_id=session.id,
        role=MessageRole.USER,
        content=user_message,
    )
    db.add(user_msg)
    llm_messages.append({"role": MessageRole.USER.value, "content": user_message})

    session.last_message_at = datetime.utcnow()
    if not session.title:
        session.title = req.query[:20]

    # Flush session + user message before streaming
    await db.flush()

    async def event_generator():
        # 1. Send citations immediately
        citations_payload = {
            "type": "citations",
            "citations": [c.model_dump() for c in citations],
            "session_id": session.id,
        }
        yield f"data: {json.dumps(citations_payload, ensure_ascii=False)}\n\n"

        # 2. Stream LLM delta chunks
        full_answer: list[str] = []
        try:
            for chunk in chat_completion_stream(llm_messages):
                full_answer.append(chunk)
                yield f"data: {json.dumps({'type': 'delta', 'text': chunk}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
            return

        # 3. Persist assistant message after streaming completes
        answer_text = "".join(full_answer)
        assistant_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=answer_text,
            citations=[c.model_dump() for c in citations],
        )
        db.add(assistant_msg)
        try:
            await db.commit()
        except Exception:
            await db.rollback()

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

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
