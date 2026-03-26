"""Universal ingestor — JSON data + PDF-link forms support.

Supported ingest modes
----------------------
1. JSON knowledge files  (保单服务, 产品, 分公司, 菜单 …)  — existing behaviour
2. Forms JSON  (表单下载-个险/团险.json)  — NEW
   Each item contains a ``full_url`` pointing to a PDF on aia.com.cn.
   Pipeline: download PDF → store raw in MinIO → parse text (PyMuPDF + OCR)
   → store parsed text in MinIO → chunk → embed → upsert Qdrant.

Idempotency
-----------
A content-hash (MD5 of raw bytes) is stored as Qdrant payload ``doc_hash``.
If the hash is unchanged on re-ingest the file is skipped.

Schemas auto-detected
---------------------
1. service_categories
2. forms / items with full_url  <- triggers PDF download pipeline
3. products
4. branches
5. menu
6. generic (list or dict)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

from app.config import settings

load_dotenv()

logger = logging.getLogger(__name__)

COLLECTION_NAME = "knowledge_base"
DEFAULT_COLLECTION = COLLECTION_NAME
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
VECTOR_SIZE = 512
_BATCH = 32


# ── Qdrant / model singletons ─────────────────────────────────────────────────

def _client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrantclient_url or os.getenv("QdrantClient_url", ""),
        api_key=settings.qdrantclient_key or os.getenv("QdrantClient_key") or None,
    )


def _model() -> SentenceTransformer:
    mp = settings.model_cache_path or os.getenv("MODEL_CACHE_PATH", "")
    if mp:
        os.environ["HF_HOME"] = mp
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = mp
    return SentenceTransformer(MODEL_NAME)


def _doc_id(text: str) -> int:
    """Stable uint64 id from content MD5."""
    return int(hashlib.md5(text.encode()).hexdigest()[:16], 16) % (2 ** 63)


def _ensure_collection(client: QdrantClient, name: str = COLLECTION_NAME) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        client.create_collection(
            name,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE, distance=models.Distance.COSINE
            ),
        )


# ── Schema detection ──────────────────────────────────────────────────────────

def _detect_schema(data: Any) -> str:
    if isinstance(data, dict):
        keys = set(data.keys())
        if "service_categories" in keys:
            return "service_categories"
        # 表单下载 JSON: top-level "items" list with "full_url" fields
        if "items" in keys and isinstance(data.get("items"), list):
            sample = data["items"][:1]
            if sample and isinstance(sample[0], dict) and "full_url" in sample[0]:
                return "forms"
        if "forms" in keys or "form_categories" in keys:
            return "forms"
        if "products" in keys or any("product" in k for k in keys):
            return "products"
        if "branches" in keys or "branch" in keys:
            return "branches"
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
            text = f"\u300c{title}\u300d\n{content}"
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
        title = (
            obj.get("title") or obj.get("name") or obj.get("\u4ea7\u54c1\u540d\u79f0") or
            obj.get("branch_name") or obj.get("form_name") or ""
        )
        content_parts = []
        for k, v in obj.items():
            if isinstance(v, str) and len(v) > 10 and k not in ("url", "id", "source", "full_url"):
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
        text = f"\u300c{title}\u300d\n{content}" if title else content
        docs.append({"text": text, "payload": {
            "title": str(title), "content": content,
            "service_name": source_file, "service_url": "",
            "category": source_file, "schema": "generic",
        }})
    return docs


def flatten_json(data: Any, source_file: str = "") -> list[dict]:
    """Auto-detect schema and return list of {text, payload} dicts.
    Returns empty list for forms schema — those go through PDF pipeline.
    """
    schema = _detect_schema(data)
    if schema == "service_categories":
        return _flatten_service_categories(data)
    if schema == "forms":
        return []  # handled by ingest_forms_pdf
    return _flatten_generic(data, source_file=source_file)


# ── PDF download helpers ──────────────────────────────────────────────────────

def _is_allowed_host(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host in settings.pdf_allowed_host_list


def _download_pdf(url: str) -> bytes:
    """Download a PDF from url with size + host validation."""
    if not _is_allowed_host(url):
        raise ValueError(f"Host not in whitelist: {url}")
    resp = requests.get(
        url,
        timeout=settings.pdf_download_timeout,
        headers={"User-Agent": "AIA-Robot/1.0 (knowledge-ingestor)"},
        stream=True,
    )
    resp.raise_for_status()
    buf: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > settings.pdf_max_bytes:
            raise ValueError(f"PDF too large (>{settings.pdf_max_bytes} bytes): {url}")
        buf.append(chunk)
    return b"".join(buf)


# ── Forms PDF pipeline ────────────────────────────────────────────────────────

def ingest_forms_pdf(
    data: dict,
    source_file: str = "",
    *,
    collection_name: str = DEFAULT_COLLECTION,
    progress_cb=None,
) -> dict:
    """Ingest a forms JSON whose items contain PDF URLs.

    For each item:
      1. Download PDF
      2. Hash for idempotency — skip if unchanged
      3. Upload raw bytes to MinIO kb-raw
      4. Extract text (PyMuPDF + DeepSeek-OCR fallback)
      5. Upload parsed text to MinIO kb-parsed
      6. Chunk → embed → upsert Qdrant
    """
    from app.knowledge_base.pdf_parser import extract_pdf_text, chunk_text
    from app.knowledge_base.storage import (
        ensure_buckets, upload_raw, upload_parsed,
        raw_object_exists, content_hash,
    )

    ensure_buckets()
    client = _client()
    _ensure_collection(client, collection_name)
    model = _model()

    items = data.get("items", [])
    page_name = data.get("page_name", source_file)
    total_chunks = 0
    skipped = 0
    failed = 0

    for idx, item in enumerate(items):
        filename: str = item.get("filename", f"form_{idx}")
        full_url: str = item.get("full_url", "")
        if not full_url:
            logger.warning(f"[ingest] no full_url for '{filename}', skipping")
            continue

        safe_name = filename.strip("\u300a\u300b").replace("/", "-").replace(" ", "_") + ".pdf"

        # 1. Download
        try:
            logger.info(f"[ingest] downloading {filename} ...")
            pdf_bytes = _download_pdf(full_url)
        except Exception as exc:
            logger.warning(f"[ingest] download failed '{filename}': {exc}")
            failed += 1
            continue

        doc_hash = content_hash(pdf_bytes)

        # 2. Idempotency (raw file may already exist, but embedding should still proceed)
        existing_raw_key = raw_object_exists(doc_hash, safe_name, source_tag="aia-form")

        # 3. Store raw PDF (only when absent)
        raw_key = existing_raw_key or ""
        if existing_raw_key:
            logger.info(
                f"[ingest] '{filename}' raw already exists (hash={doc_hash[:8]}), reuse object"
            )
        else:
            try:
                raw_key = upload_raw(pdf_bytes, safe_name, doc_hash, source_tag="aia-form")
                logger.info(f"[ingest] raw -> minio://kb-raw/{raw_key}")
            except Exception as exc:
                logger.warning(f"[ingest] MinIO raw upload failed '{filename}': {exc}")

        # 4. Parse PDF text
        try:
            full_text = extract_pdf_text(pdf_bytes)
        except Exception as exc:
            logger.warning(f"[ingest] PDF parse failed '{filename}': {exc}")
            failed += 1
            continue

        if not full_text.strip():
            logger.warning(f"[ingest] no text extracted from '{filename}', skipping")
            failed += 1
            continue

        # 5. Store parsed text
        parsed_key = ""
        try:
            parsed_key = upload_parsed(full_text, safe_name, doc_hash, source_tag="aia-form")
            logger.info(f"[ingest] parsed -> minio://kb-parsed/{parsed_key}")
        except Exception as exc:
            logger.warning(f"[ingest] MinIO parsed upload failed '{filename}': {exc}")

        # 6. Chunk
        chunks = chunk_text(full_text)
        if not chunks:
            continue

        # 7. Embed
        vectors = model.encode(
            chunks, batch_size=_BATCH, normalize_embeddings=True, show_progress_bar=False,
        )

        # 8. Upsert Qdrant
        points = [
            models.PointStruct(
                id=_doc_id(chunks[i] + doc_hash),
                vector=vectors[i].tolist(),
                payload={
                    "title": filename,
                    "content": chunks[i],
                    "service_name": page_name,
                    "service_url": full_url,
                    "category": page_name,
                    "schema": "forms_pdf",
                    "source_file": source_file,
                    "source_url": full_url,
                    "doc_hash": doc_hash,
                    "raw_object_key": raw_key,
                    "parsed_object_key": parsed_key,
                    "chunk_index": i,
                    "chunk_total": len(chunks),
                },
            )
            for i in range(len(chunks))
        ]
        client.upsert(collection_name, points=points)
        total_chunks += len(chunks)
        logger.info(f"[ingest] '{filename}' -> {len(chunks)} chunks upserted")

        if progress_cb:
            progress_cb(idx + 1, len(items), filename)

    return {
        "file": source_file,
        "schema": "forms_pdf",
        "doc_count": total_chunks,
        "skipped": skipped,
        "failed": failed,
    }


# ── Core ingest function ──────────────────────────────────────────────────────

def ingest_file(file_path: str, *, collection_name: str = DEFAULT_COLLECTION, progress_cb=None) -> dict:
    """Parse a JSON file and ingest into Qdrant.

    For forms schema (items with full_url): triggers PDF download pipeline.
    For service_categories schema: each category is ingested into its own
      collection named after the Chinese service_name (e.g. "保单服务").
      The caller-supplied collection_name is used as fallback only when a
      category's service_name is empty.
    For all other schemas: embeds JSON text directly into collection_name.

    Returns: {"file": str, "schema": str, "doc_count": int}
    """
    path = Path(file_path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    schema = _detect_schema(data)

    # Route forms JSON to PDF pipeline
    if schema == "forms":
        return ingest_forms_pdf(
            data,
            source_file=path.name,
            collection_name=collection_name,
            progress_cb=progress_cb,
        )

    # service_categories: ingest each category into its own named collection
    if schema == "service_categories":
        qdrant = _client()
        model = _model()
        total = 0
        collections_created: list[str] = []
        for cat in data.get("service_categories", []):
            cat_name: str = cat.get("service_name") or collection_name
            cat_docs = _flatten_service_categories({"service_categories": [cat]})
            if not cat_docs:
                continue
            _ensure_collection(qdrant, cat_name)
            texts = [d["text"] for d in cat_docs]
            vectors = model.encode(
                texts, batch_size=_BATCH, normalize_embeddings=True, show_progress_bar=False
            )
            points = [
                models.PointStruct(
                    id=_doc_id(cat_docs[i]["text"]),
                    vector=vectors[i].tolist(),
                    payload={**cat_docs[i]["payload"], "source_file": path.name},
                )
                for i in range(len(cat_docs))
            ]
            qdrant.upsert(cat_name, points=points)
            total += len(points)
            collections_created.append(cat_name)
            logger.info(f"[ingest] '{cat_name}' <- {len(points)} docs from {path.name}")
        return {
            "file": path.name,
            "schema": schema,
            "doc_count": total,
            "collections": collections_created,
        }

    # Standard JSON text ingestion
    docs = flatten_json(data, source_file=path.name)
    if not docs:
        return {"file": path.name, "schema": schema, "doc_count": 0}

    client = _client()
    _ensure_collection(client, collection_name)
    model = _model()

    texts = [d["text"] for d in docs]
    vectors = model.encode(
        texts, batch_size=_BATCH, normalize_embeddings=True, show_progress_bar=False
    )

    points = [
        models.PointStruct(
            id=_doc_id(docs[i]["text"]),
            vector=vectors[i].tolist(),
            payload={**docs[i]["payload"], "source_file": path.name},
        )
        for i in range(len(docs))
    ]
    client.upsert(collection_name, points=points)
    return {"file": path.name, "schema": schema, "doc_count": len(docs)}


def ingest_directory(dir_path: str, *, collection_name: str = DEFAULT_COLLECTION) -> list[dict]:
    """Ingest all JSON files in a directory."""
    results = []
    for p in Path(dir_path).glob("*.json"):
        try:
            r = ingest_file(str(p), collection_name=collection_name)
            results.append(r)
        except Exception as exc:
            results.append({"file": p.name, "schema": "error", "doc_count": 0, "error": str(exc)})
    return results
