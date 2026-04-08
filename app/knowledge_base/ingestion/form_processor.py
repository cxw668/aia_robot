"""表单 PDF 特殊处理流程。"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests

from app.config import settings
from app.knowledge_base.config import DEFAULT_COLLECTION, _BATCH
from app.knowledge_base.core._storage_impl import (
    ensure_buckets,
    upload_raw,
    upload_parsed,
    raw_object_exists,
    content_hash,
    clear_source_tag,
)
from app.knowledge_base.core.vector_store import ensure_collection
from app.knowledge_base.core.embedding import get_model
from app.knowledge_base.processing.parser import extract_pdf_markdown
from app.knowledge_base.processing.chunker import chunk_markdown
from app.knowledge_base.processing.normalizer import normalize_category

logger = logging.getLogger(__name__)


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


def ingest_forms_pdf(
    data: dict,
    source_file: str = "",
    *,
    collection_name: str = DEFAULT_COLLECTION,
    source_tag: str = "aia-form",
    progress_cb=None,
) -> dict:
    """Ingest a forms JSON whose items contain PDF URLs."""
    from qdrant_client import QdrantClient, models
    from app.knowledge_base.core.vector_store import get_client

    ensure_buckets()
    client = get_client()
    ensure_collection(client, collection_name)
    model = get_model()

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
            skipped += 1
            continue
        if ".pdf" not in full_url.lower():
            logger.info(f"[ingest] skip non-PDF form '{filename}': {full_url}")
            skipped += 1
            continue

        safe_name = filename.strip("《》").replace("/", "-").replace(" ", "_") + ".pdf"

        try:
            logger.info(f"[ingest] downloading {filename} ...")
            pdf_bytes = _download_pdf(full_url)
        except Exception as exc:
            logger.warning(f"[ingest] download failed '{filename}': {exc}")
            failed += 1
            continue

        doc_hash = content_hash(pdf_bytes)
        existing_raw_key = raw_object_exists(doc_hash, safe_name, source_tag=source_tag)

        raw_key = existing_raw_key or ""
        if not existing_raw_key:
            try:
                raw_key = upload_raw(pdf_bytes, safe_name, doc_hash, source_tag=source_tag)
                logger.info(f"[ingest] raw -> minio://{settings.minio_bucket_raw}/{raw_key}")
            except Exception as exc:
                logger.warning(f"[ingest] MinIO raw upload failed '{filename}': {exc}")

        try:
            markdown = extract_pdf_markdown(pdf_bytes)
        except Exception as exc:
            logger.warning(f"[ingest] PDF parse failed '{filename}': {exc}")
            failed += 1
            continue

        if not markdown.strip():
            logger.warning(f"[ingest] no markdown extracted from '{filename}', skipping")
            failed += 1
            continue

        parsed_key = ""
        try:
            parsed_key = upload_parsed(
                markdown, safe_name, doc_hash,
                source_tag=source_tag, suffix=".md",
                content_type="text/markdown; charset=utf-8",
            )
            logger.info(f"[ingest] parsed -> minio://{settings.minio_bucket_parsed}/{parsed_key}")
        except Exception as exc:
            logger.warning(f"[ingest] MinIO parsed upload failed '{filename}': {exc}")

        chunks = chunk_markdown(markdown)
        if not chunks:
            skipped += 1
            continue

        vectors = model.encode(
            chunks, batch_size=_BATCH, normalize_embeddings=True, show_progress_bar=False
        )

        import hashlib

        def _doc_id(text: str) -> int:
            return int(hashlib.md5(text.encode()).hexdigest()[:16], 16) % (2 ** 63)

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
                    "category_canonical": normalize_category(page_name),
                    "schema": "forms_markdown",
                    "source_file": source_file,
                    "source_url": full_url,
                    "source_tag": source_tag,
                    "doc_hash": doc_hash,
                    "raw_object_key": raw_key,
                    "parsed_object_key": parsed_key,
                    "chunk_index": i,
                    "chunk_total": len(chunks),
                    "format": "markdown",
                },
            )
            for i in range(len(chunks))
        ]
        client.upsert(collection_name, points=points)
        total_chunks += len(chunks)
        logger.info(f"[ingest] '{filename}' -> {len(chunks)} markdown chunks upserted")

        if progress_cb:
            progress_cb(idx + 1, len(items), filename)

    return {
        "file": source_file,
        "schema": "forms_markdown",
        "doc_count": total_chunks,
        "skipped": skipped,
        "failed": failed,
        "source_tag": source_tag,
    }


def clear_form_knowledge(
    *,
    collection_name: str,
    source_file: str,
    source_tag: str,
) -> dict[str, int]:
    """Remove existing form knowledge from Qdrant and MinIO before re-import."""
    from qdrant_client import models as qmodels
    from app.knowledge_base.core.vector_store import get_client

    client = get_client()
    deleted_points = 0
    try:
        client.delete(
            collection_name=collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    should=[
                        qmodels.FieldCondition(key="source_file", match=qmodels.MatchValue(value=source_file)),
                        qmodels.FieldCondition(key="source_tag", match=qmodels.MatchValue(value=source_tag)),
                    ]
                )
            ),
        )
    except Exception as exc:
        logger.warning(f"[ingest] failed clearing Qdrant dirty data for {source_file}: {exc}")
    else:
        deleted_points = -1

    deleted_objects = clear_source_tag(source_tag)
    return {
        "qdrant_points": deleted_points,
        "raw_objects": deleted_objects.get(settings.minio_bucket_raw, 0),
        "parsed_objects": deleted_objects.get(settings.minio_bucket_parsed, 0),
    }


__all__ = ["ingest_forms_pdf", "clear_form_knowledge"]
