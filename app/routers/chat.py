"""Chat router — POST /chat, DELETE /chat/{session_id}"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.session import store
from app.knowledge_base.rag import retrieve, build_rag_context
from app.chat.index import chat_completion

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


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Multi-turn RAG chat endpoint."""
    # 1. Get / create session
    sess = store.get_or_create(req.session_id)

    # 2. Initialise system prompt on first turn
    if not sess.messages:
        sess.add("system", SYSTEM_PROMPT)

    # 3. Retrieve relevant docs
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

    # 4. Build RAG context string
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

    # 5. Append user turn
    sess.add("user", user_message)

    # 6. Call LLM with full history
    try:
        answer = chat_completion(sess.to_openai_messages())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # 7. Store assistant reply (store clean query, not context-injected)
    sess.add("assistant", answer)

    return ChatResponse(
        answer=answer,
        citations=citations,
        session_id=sess.session_id,
    )


@router.delete("/{session_id}")
async def clear_session(session_id: str) -> dict:
    """Clear a conversation session."""
    deleted = store.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "cleared", "session_id": session_id}


@router.get("/{session_id}/history")
async def get_history(session_id: str) -> dict:
    """Return message history for a session."""
    sess = store.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    msgs = [
        {"role": m.role, "content": m.content}
        for m in sess.messages
        if m.role != "system"
    ]
    return {"session_id": session_id, "messages": msgs}
