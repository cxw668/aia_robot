"""LangChain-compatible adapter 层（轻量封装现有自研实现）。

目标：逐步提供与 LangChain 同类接口（Embeddings, VectorStore, Retriever, LLM），
方便后续直接替换为 LangChain 对象或作为桥接层使用。
"""
from __future__ import annotations

from typing import Iterable, List, Dict, Generator

from app.knowledge_base.core.embedding import get_model
from app.knowledge_base.core.vector_store import get_client, query_collection
from app.knowledge_base.retrieval import engine as retrieval_engine
from app.knowledge_base.retrieval.rescorer import llm_rescore_candidates
from app.chat import index as chat_index


class EmbeddingsAdapter:
    """包装现有 embedding 服务，提供 embed_documents / embed_query 接口。"""

    def __init__(self) -> None:
        self._model = get_model()

    def embed_documents(self, texts: Iterable[str]) -> List[List[float]]:
        texts_list = list(texts)
        if not texts_list:
            return []
        vecs = self._model.encode(texts_list, normalize_embeddings=True)
        return [v.tolist() for v in vecs]

    def embed_query(self, text: str) -> List[float]:
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()


class VectorStoreAdapter:
    """轻量包装 Qdrant 查询接口，保持原有 payload 结构。"""

    def __init__(self, collection_name: str) -> None:
        self.collection_name = collection_name
        self._client = get_client()

    def search(self, query_vector: List[float], top_k: int = 10, query_filter=None) -> List[Dict]:
        return query_collection(
            self._client,
            self.collection_name,
            query_vector,
            top_k,
            query_filter=query_filter,
        )

    # 未来可扩展方法：upsert, delete, scroll


class LLMAdapter:
    """包装现有 LLM 客户端（同步）。提供简单的生成与流式生成接口。

    注意：当前封装为同步调用；在 async 环境下应通过线程池执行。
    """

    def generate(self, prompt: str) -> str:
        return chat_index.query_llm(prompt)

    def chat_completion(self, messages: List[Dict]) -> str:
        return chat_index.chat_completion(messages)

    def stream_chat(self, messages: List[Dict]) -> Generator[str, None, None]:
        return chat_index.chat_completion_stream(messages)


class RetrieverAdapter:
    """直接封装现有 retrieve / rag_query 函数，作为 LangChain Retriever 的替代。

    Methods mirror现有引擎：`retrieve`, `rag_query`。
    """

    def __init__(self, collection_name: str | None = None) -> None:
        self.collection_name = collection_name

    def retrieve(self, query: str, top_k: int = 5, only_on_sale: bool = False, category: str | None = None) -> List[Dict]:
        return retrieval_engine.retrieve(
            query,
            top_k=top_k,
            collection_name=self.collection_name,
            only_on_sale=only_on_sale,
            category=category,
        )

    def rag_query(self, query: str, top_k: int = 5) -> str:
        return retrieval_engine.rag_query(query, top_k=top_k, collection_name=self.collection_name)


class RerankerAdapter:
    """封装现有基于 LLM 的重排逻辑。"""

    def rescoring(self, query: str, candidates: List[Dict], max_candidates: int | None = None, min_llm_score: float | None = None, final_top_k: int | None = None) -> List[Dict]:
        return llm_rescore_candidates(
            query,
            candidates,
            max_candidates=max_candidates or (len(candidates) if candidates else 0),
            min_llm_score=min_llm_score,
            final_top_k=final_top_k,
        )


__all__ = [
    "EmbeddingsAdapter",
    "VectorStoreAdapter",
    "LLMAdapter",
    "RetrieverAdapter",
    "RerankerAdapter",
]
