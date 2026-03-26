"""Chat router — DB-backed chat session + message persistence."""
from __future__ import annotations

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.index import chat_completion
from app.database import ChatMessage, ChatSession, MessageRole, User, get_db
from app.knowledge_base.rag import retrieve
from app.routers.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "你是友邦保险（AIA）的智能客服助手。"
    "请严格依据提供的知识库内容回答用户问题，不得编造信息。"
    "如知识库内容不足以回答，请如实告知并建议用户联系人工客服。"
    "回答应简洁、准确，使用规范中文。"
)


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    top_k: int = 3


class Citation(BaseModel):
    title: str
    content: str
    score: float
    service_name: str = ""
    service_url: str = ""


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    session_id: str


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


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """Multi-turn RAG chat endpoint with database persistence."""
    # 1) Get / create session bound to current user
    session_id = req.session_id or str(uuid.uuid4())
    session = await _get_user_session(db, current_user.id, session_id)
    if not session:
        session = ChatSession(id=session_id, user_id=current_user.id)
        db.add(session)
        await db.flush()

    # 2) Load existing history from DB
    history = await _load_session_messages(db, session.id)

    llm_messages: list[dict[str, str]] = [
        {"role": m.role.value, "content": m.content}
        for m in history
    ]

    # 3) Initialize system prompt if first turn
    if not history:
        sys_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.SYSTEM,
            content=SYSTEM_PROMPT,
        )
        db.add(sys_msg)
        llm_messages.append({"role": MessageRole.SYSTEM.value, "content": SYSTEM_PROMPT})

    # 4) Retrieve relevant docs
    docs = retrieve(req.query, top_k=req.top_k)
    citations = [
        Citation(
            title=d["title"],
            content=d["content"],
            score=d["score"],
            service_name=d.get("service_name", ""),
            service_url=d.get("service_url", ""),
        )
        for d in docs
    ]

    # 5) Build user message (inject RAG context)
    if docs:
        ctx_parts = []
        for i, d in enumerate(docs, 1):
            ctx_parts.append(f"[参考{i}] {d['title']}\n{d['content']}")
        context_block = "\n\n".join(ctx_parts)
        user_message = (
            f"【知识库参考】\n{context_block}\n\n"
            f"【用户问题】\n{req.query}"
        )
    else:
        user_message = req.query

    # 6) Persist user turn
    user_msg = ChatMessage(
        session_id=session.id,
        role=MessageRole.USER,
        content=user_message,
    )
    db.add(user_msg)
    llm_messages.append({"role": MessageRole.USER.value, "content": user_message})

    # 7) Call LLM
    try:
        answer = chat_completion(llm_messages)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # 8) Persist assistant turn
    assistant_msg = ChatMessage(
        session_id=session.id,
        role=MessageRole.ASSISTANT,
        content=answer,
        citations=[c.model_dump() for c in citations],
    )
    db.add(assistant_msg)

    # 9) Update session metadata
    session.last_message_at = datetime.utcnow()
    if not session.title:
        session.title = req.query[:20]

    return ChatResponse(
        answer=answer,
        citations=citations,
        session_id=session.id,
    )


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
    """Return message history for a session."""
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
