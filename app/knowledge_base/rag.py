import os
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()
custom_model_dir = os.getenv("MODEL_CACHE_PATH")

os.environ["HF_HOME"] = custom_model_dir
os.environ["TRANSFORMERS_CACHE"] = custom_model_dir
os.environ["SENTENCE_TRANSFORMERS_HOME"] = custom_model_dir
    
COLLECTION_NAME = "knowledge_base"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
TOP_K = 3

_client: QdrantClient | None = None
_model: SentenceTransformer | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=os.getenv("QdrantClient_url"),
            api_key=os.getenv("QdrantClient_key"),
        )
    return _client


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


# ── 核心检索函数 ──────────────────────────────────
def retrieve(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    对 query 进行向量检索，返回最相关的 top_k 条知识条目。

    返回値格式：
    [
        {
            "score":        float,   # 余弦相似度（越高越相关）
            "title":        str,
            "content":      str,
            "service_name": str,
            "service_url":  str,
        },
        ...
    ]
    """
    model = _get_model()
    client = _get_client()

    query_vector = model.encode(query, normalize_embeddings=True).tolist()

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    )
    hits = response.points
    results = []
    for hit in hits:
        payload = hit.payload or {}
        results.append({
            "score": round(hit.score, 4),
            "title": payload.get("title", ""),
            "content": payload.get("content", ""),
            "service_name": payload.get("service_name", ""),
            "service_url": payload.get("service_url", ""),
        })
    return results


# ── RAG 组合函数：检索 + 拼接上下文 ──────────────────
def build_rag_context(query: str, top_k: int = TOP_K) -> str:
    """
    检索相关知识并拼接为可直接注入 LLM prompt 的上下文字符串。
    """
    docs = retrieve(query, top_k=top_k)
    if not docs:
        return "未找到相关知识库内容。"

    parts = []
    for i, doc in enumerate(docs, 1):
        parts.append(
            f"[参考{i}] 服务项目：{doc['title']}\n"
            f"{doc['content']}"
        )
    return "\n\n".join(parts)


# ── 便捷：检索 + 调用 LLM 一步完成 ────────────────────
def rag_query(query: str, top_k: int = TOP_K) -> str:
    """
    完整的 RAG 流程：
      1. 向量检索相关保单服务知识
      2. 构造带上下文的 prompt
      3. 调用 LLM 生成回答
    """
    from app.chat.index import query_llm

    context = build_rag_context(query, top_k=top_k)

    prompt = (
        "你是友邦保险（AIA）的智能客服助手，请根据以下知识库内容回答用户问题。\n"
        "如果知识库内容无法完整回答问题，请如实告知，不要编造信息。\n\n"
        f"【知识库内容】\n{context}\n\n"
        f"【用户问题】\n{query}\n\n"
        "请用简洁、准确的中文回答："
    )

    return query_llm(prompt)


# ── 命令行快速测试 ──────────────────────────────────
if __name__ == "__main__":
    import sys

    test_query = sys.argv[1] if len(sys.argv) > 1 else "如何变更投保人？"
    print(f"\n查询: {test_query}\n{'='*50}")

    print("\n── 检索结果 ──")
    for r in retrieve(test_query):
        print(f"[{r['score']}] {r['title']}")
        print(f"  {r['content'][:80]}...\n")

    print("\n── RAG 回答 ──")
    answer = rag_query(test_query)
    print(answer)
