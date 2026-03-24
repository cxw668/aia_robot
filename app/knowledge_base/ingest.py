"""Universal JSON ingestor — auto-detects schema and flattens to documents.

Supported schemas
-----------------
1. service_categories  (保单服务.json style)
2. products            (个险+团险产品.json style)
3. branches            (分公司页面.json style)
4. forms               (表单下载.json style)
5. menu                (客户服务菜单.json style)
6. generic             (list of objects — best-effort)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

load_dotenv()

COLLECTION_NAME = "knowledge_base"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
VECTOR_SIZE = 512
_BATCH = 32


# ── Qdrant / model singletons (reuse from rag.py) ────────────────────────────
def _client() -> QdrantClient:
    return QdrantClient(
        url=os.getenv("QdrantClient_url"),
        api_key=os.getenv("QdrantClient_key"),
    )


def _model() -> SentenceTransformer:
    mp = os.getenv("MODEL_CACHE_PATH")
    if mp:
        os.environ["HF_HOME"] = mp
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = mp
    return SentenceTransformer(MODEL_NAME)


def _doc_id(text: str) -> int:
    """Stable uint64 id from content MD5."""
    return int(hashlib.md5(text.encode()).hexdigest()[:16], 16) % (2 ** 63)


# ── Schema detectors ─────────────────────────────────────────────────────────

def _detect_schema(data: Any) -> str:
    if isinstance(data, dict):
        keys = set(data.keys())
        if "service_categories" in keys:
            return "service_categories"
        if "products" in keys or any("product" in k for k in keys):
            return "products"
        if "branches" in keys or "branch" in keys:
            return "branches"
        if "forms" in keys or "form_categories" in keys:
            return "forms"
        if "menu" in keys or "menus" in keys:
            return "menu"
    if isinstance(data, list):
        return "generic_list"
    return "generic"


# ── Schema-specific flatteners ────────────────────────────────────────────────

def _flatten_service_categories(data: dict) -> list[dict]:
    docs = []
    for cat in data.get("service_categories", []):
        sname = cat.get("service_name", "")
        surl = cat.get("url", "")
        for item in cat.get("items", []):
            title = item.get("title", "")
            content = item.get("content", "")
            text = f"【{title}】\n{content}"
            docs.append({"text": text, "payload": {
                "title": title, "content": content,
                "service_name": sname, "service_url": surl,
                "category": sname, "schema": "service_categories",
            }})
    return docs


def _flatten_generic(data: Any, source_file: str = "") -> list[dict]:
    """Best-effort: walk any nested structure and extract text fields."""
    docs = []
    items = data if isinstance(data, list) else [data]
    for obj in items:
        if not isinstance(obj, dict):
            continue
        # Try common title/content keys
        title = (
            obj.get("title") or obj.get("name") or obj.get("产品名称") or
            obj.get("branch_name") or obj.get("form_name") or ""
        )
        content_parts = []
        for k, v in obj.items():
            if isinstance(v, str) and len(v) > 10 and k not in ("url", "id", "source"):
                content_parts.append(f"{k}: {v}")
            elif isinstance(v, list):
                for sub in v:
                    if isinstance(sub, str):
                        content_parts.append(sub)
                    elif isinstance(sub, dict):
                        for sk, sv in sub.items():
                            if isinstance(sv, str) and len(sv) > 5:
                                content_parts.append(f"{sk}: {sv}")
        content = "\n".join(content_parts)
        if not content.strip():
            continue
        text = f"【{title}】\n{content}" if title else content
        docs.append({"text": text, "payload": {
            "title": str(title), "content": content,
            "service_name": source_file, "service_url": "",
            "category": source_file, "schema": "generic",
        }})
    return docs


def flatten_json(data: Any, source_file: str = "") -> list[dict]:
    """Auto-detect schema and return list of {text, payload} dicts."""
    schema = _detect_schema(data)
    if schema == "service_categories":
        return _flatten_service_categories(data)
    return _flatten_generic(data, source_file=source_file)


# ── Core ingest function ──────────────────────────────────────────────────────

def ingest_file(file_path: str, *, progress_cb=None) -> dict:
    """
    Parse a JSON file, embed its contents and upsert into Qdrant.

    Returns: {"file": str, "schema": str, "doc_count": int}
    """
    path = Path(file_path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    schema = _detect_schema(data)
    docs = flatten_json(data, source_file=path.name)
    if not docs:
        return {"file": path.name, "schema": schema, "doc_count": 0}

    client = _client()
    # Ensure collection exists
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            COLLECTION_NAME,
            vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
        )

    model = _model()
    texts = [d["text"] for d in docs]
    vectors = model.encode(texts, batch_size=_BATCH, normalize_embeddings=True, show_progress_bar=False)

    points = [
        models.PointStruct(
            id=_doc_id(docs[i]["text"]),
            vector=vectors[i].tolist(),
            payload={**docs[i]["payload"], "source_file": path.name},
        )
        for i in range(len(docs))
    ]
    client.upsert(COLLECTION_NAME, points=points)

    return {"file": path.name, "schema": schema, "doc_count": len(docs)}


def ingest_directory(dir_path: str) -> list[dict]:
    """Ingest all JSON files in a directory."""
    results = []
    for p in Path(dir_path).glob("*.json"):
        try:
            r = ingest_file(str(p))
            results.append(r)
        except Exception as exc:
            results.append({"file": p.name, "schema": "error", "doc_count": 0, "error": str(exc)})
    return results
