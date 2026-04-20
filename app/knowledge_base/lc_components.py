"""LangChain 原生组件层。

继承 LangChain 抽象基类，让自研实现可直接接入 LangChain 生态（LCEL 链、Agent、工具）。

组件：
- AIAEmbeddings   : langchain_core.embeddings.Embeddings 子类
- AIARetriever    : langchain_core.retrievers.BaseRetriever 子类
- AIAChatModel    : langchain_core.language_models.BaseChatModel 子类（同步封装）
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterator, List, Optional

from langchain_core.callbacks.manager import (
    CallbackManagerForLLMRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.retrievers import BaseRetriever

from app.knowledge_base.config import DEFAULT_COLLECTION, TOP_K
from app.knowledge_base.core.embedding import get_model
from app.knowledge_base.retrieval.engine import retrieve

# 共用线程池，用于在 async 代码中执行同步阻塞调用
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="lc_sync")


# ── 1. Embeddings ────────────────────────────────────────────────────────────

class AIAEmbeddings(Embeddings):
    """友邦本地 SentenceTransformer 嵌入模型（LangChain Embeddings 接口）。"""

    def __init__(self) -> None:
        self._model = get_model()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]

    def embed_query(self, text: str) -> List[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_EXECUTOR, self.embed_documents, texts)

    async def aembed_query(self, text: str) -> List[float]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_EXECUTOR, self.embed_query, text)


# ── 2. Retriever ─────────────────────────────────────────────────────────────

class AIARetriever(BaseRetriever):
    """友邦知识库检索器（LangChain BaseRetriever 接口）。

    每个检索结果转换为 `Document`，原始 payload 保存在 `metadata` 中，
    方便后续 LangChain 链或 Agent 工具消费。
    """

    collection_name: str = DEFAULT_COLLECTION
    top_k: int = TOP_K
    only_on_sale: bool = False
    category: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:
        hits = retrieve(
            query,
            top_k=self.top_k,
            collection_name=self.collection_name,
            only_on_sale=self.only_on_sale,
            category=self.category,
        )
        docs: List[Document] = []
        for hit in hits:
            content = hit.get("content") or hit.get("title") or ""
            meta = {k: v for k, v in hit.items() if k != "content"}
            docs.append(Document(page_content=content, metadata=meta))
        return docs

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _EXECUTOR,
            lambda: self._get_relevant_documents(query, run_manager=run_manager),
        )


# ── 3. ChatModel ─────────────────────────────────────────────────────────────

class AIAChatModel(BaseChatModel):
    """封装友邦自研 LLM 客户端，实现 LangChain BaseChatModel 接口。

    支持：
    - 同步 / 异步调用 (_generate / _agenerate)
    - 流式 token 输出 (_stream / _astream)
    """

    model_name: str = "aia-llm"  # 对外标识，不影响实际调用

    @property
    def _llm_type(self) -> str:
        return "aia-custom"

    def _messages_to_text(self, messages: List[BaseMessage]) -> List[dict]:
        role_map = {"human": "user", "ai": "assistant", "system": "system"}
        result: List[dict] = []
        for m in messages:
            role = role_map.get(m.type, "user")
            result.append({"role": role, "content": m.content})
        return result

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        from app.chat.index import chat_completion

        raw = self._messages_to_text(messages)
        content = chat_completion(raw)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _EXECUTOR,
            lambda: self._generate(messages, stop=stop, **kwargs),
        )

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        from app.chat.index import chat_completion_stream

        raw = self._messages_to_text(messages)
        for token in chat_completion_stream(raw):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=token))
            if run_manager:
                run_manager.on_llm_new_token(token, chunk=chunk)
            yield chunk

    async def _astream(  # type: ignore[override]
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ):
        """Async 流式：通过线程池执行同步 generator 并逐 token yield。"""
        import queue
        import threading

        q: queue.Queue = queue.Queue()
        _SENTINEL = object()

        def _producer() -> None:
            try:
                for chunk in self._stream(messages, stop=stop, run_manager=run_manager, **kwargs):
                    q.put(chunk)
            finally:
                q.put(_SENTINEL)

        thread = threading.Thread(target=_producer, daemon=True)
        thread.start()
        loop = asyncio.get_event_loop()
        while True:
            chunk = await loop.run_in_executor(_EXECUTOR, q.get)
            if chunk is _SENTINEL:
                break
            yield chunk


__all__ = ["AIAEmbeddings", "AIARetriever", "AIAChatModel"]
