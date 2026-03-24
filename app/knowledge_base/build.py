import os
import json
import hashlib
from qdrant_client import QdrantClient
from qdrant_client import models
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()
model_path = os.getenv("MODEL_CACHE_PATH")
DATA_PATH = os.path.join(os.path.dirname(__file__), "../../aia_data/保单服务.json")
COLLECTION_NAME = "knowledge_base"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"  # 中文小模型，向量维度 512
VECTOR_SIZE = 512


def load_documents(path: str) -> list[dict]:
    """
    将 保单服务.json 展平为文档列表。
    每条文档包含：
      - id        : 基于内容的 MD5 哈希（确保幂等重建）
      - text      : 用于向量化的文本（标题 + 内容）
      - metadata  : 原始字段，供检索后透传给 LLM
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    docs = []
    for category in data.get("service_categories", []):
        service_name = category.get("service_name", "")
        service_url = category.get("url", "")
        for item in category.get("items", []):
            title = item.get("title", "")
            content = item.get("content", "")
            # 拼接为一段完整文本送入 embedding
            text = f"【{title}】\n{content}"
            doc_id = hashlib.md5(text.encode("utf-8")).hexdigest()
            docs.append(
                {
                    "id": doc_id,
                    "text": text,
                    "metadata": {
                        "title": title,
                        "content": content,
                        "service_name": service_name,
                        "service_url": service_url,
                    },
                }
            )
    return docs


def build_knowledge_base():
    # 1. 连接 Qdrant
    client = QdrantClient(
        url=os.getenv("QdrantClient_url"),
        api_key=os.getenv("QdrantClient_key"),
    )

    # 2. 创建 collection（若已存在则跳过）
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE,
                distance=models.Distance.COSINE,
            ),
        )
        print(f"[build] Collection '{COLLECTION_NAME}' created.")
    else:
        print(
            f"[build] Collection '{COLLECTION_NAME}' already exists, skipping creation."
        )


    if model_path:
        os.environ["HF_HOME"] = model_path
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = model_path

    # 3. 加载 embedding 模型
    print(f"[build] Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    # 4. 加载并向量化文档
    docs = load_documents(DATA_PATH)
    print(f"[build] Loaded {len(docs)} documents from 保单服务.json")

    texts = [d["text"] for d in docs]
    print("[build] Encoding documents...")
    vectors = model.encode(
        texts, batch_size=32, show_progress_bar=True, normalize_embeddings=True
    )

    # 5. 构造 PointStruct 列表并 upsert
    points = [
        models.PointStruct(
            id=int(d["id"][:8], 16),  # 取 MD5 前 8 位转为 uint64
            vector=vectors[i].tolist(),
            payload=d["metadata"],
        )
        for i, d in enumerate(docs)
    ]

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
    )
    print(f"[build] Upserted {len(points)} points into '{COLLECTION_NAME}'.")
    print("[build] Knowledge base build complete.")


if __name__ == "__main__":
    build_knowledge_base()
