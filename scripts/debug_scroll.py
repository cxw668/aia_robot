from collections import Counter
from qdrant_client import QdrantClient
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.knowledge_base.processing.normalizer import get_point_category

client = QdrantClient(url="http://localhost:6333")
collection_name = "aia_knowledge_base"

def get_categories_scroll(client, collection_name, limit=600):
    categories = []
    try:
        points, next_page = client.scroll(
            collection_name=collection_name,
            limit=limit,
            with_payload=["category", "category_canonical", "service_name", "source_file"],
            with_vectors=False,
        )

        for point in points:
            payload = point.payload or {}
            cat = get_point_category(payload)
            if cat:
                categories.append(cat)
        return categories
    except Exception as e:
        print(f"获取数据失败: {e}")
        return []


# 执行获取
if __name__ == "__main__":
    result_categories = get_categories_scroll(client, collection_name)
    counts = Counter(result_categories)
    total = sum(counts.values())
    print(f"成功获取 {total} 个分类数据，{len(counts)} 个不同分类")
    for cat, cnt in counts.most_common(20):
        print(f"{cat}: {cnt}")
