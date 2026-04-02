"""MinIO 对象存储助手。

存储桶 (Buckets)
-------
kb-raw    : 原始下载的文件（如 PDF 等）
kb-parsed : 解析后的 Markdown 文件

对象键 (Object key) 命名约定
---------------------
  {source_tag}/{yyyy}/{mm}/{doc_hash[:8]}/{filename}
  例如：aia-form/2026/03/ab12cd34/保险合同内容变更申请书.pdf

所有公共函数都是同步的（从后台线程调用）。
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime
from functools import lru_cache
from typing import Optional

from minio import Minio
from minio.error import S3Error

from app.config import settings


# ── Client singleton ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_buckets() -> None:
    client = get_minio_client()
    for bucket in (settings.minio_bucket_raw, settings.minio_bucket_parsed):
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                print(f"[minio] created bucket: {bucket}")
        except S3Error as exc:
            print(f"[minio] warn — could not ensure bucket '{bucket}': {exc}")


# ── Object key helpers ────────────────────────────────────────────────────────

def _make_key(filename: str, doc_hash: str, source_tag: str = "aia-form") -> str:
    now = datetime.utcnow()
    return f"{source_tag}/{now.year}/{now.month:02d}/{doc_hash[:8]}/{filename}"


def content_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def normalize_form_filename(filename: str, suffix: str = ".pdf") -> str:
    """Normalize AIA form display name into stored object filename."""
    safe_name = filename.strip("《》").replace("/", "-").replace(" ", "_")
    return safe_name if safe_name.lower().endswith(suffix.lower()) else f"{safe_name}{suffix}"


# ── Upload helpers ────────────────────────────────────────────────────────────

def upload_raw(
    data: bytes,
    filename: str,
    doc_hash: str,
    source_tag: str = "aia-form",
    content_type: str = "application/pdf",
) -> str:
    client = get_minio_client()
    key = _make_key(filename, doc_hash, source_tag)
    client.put_object(
        bucket_name=settings.minio_bucket_raw,
        object_name=key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
        metadata={"doc_hash": doc_hash, "source_tag": source_tag},
    )
    return key


def upload_parsed(
    text: str,
    filename: str,
    doc_hash: str,
    source_tag: str = "aia-form",
    suffix: str = ".md",
    content_type: str = "text/markdown; charset=utf-8",
) -> str:
    client = get_minio_client()
    base = filename.rsplit(".", 1)[0] if "." in filename else filename
    normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    key = _make_key(f"{base}{normalized_suffix}", doc_hash, source_tag)
    encoded = text.encode("utf-8")
    client.put_object(
        bucket_name=settings.minio_bucket_parsed,
        object_name=key,
        data=io.BytesIO(encoded),
        length=len(encoded),
        content_type=content_type,
        metadata={"doc_hash": doc_hash, "source_tag": source_tag},
    )
    return key


# ── Idempotency / lookup helpers ──────────────────────────────────────────────

def raw_object_exists(doc_hash: str, filename: str, source_tag: str = "aia-form") -> Optional[str]:
    client = get_minio_client()
    key = _make_key(filename, doc_hash, source_tag)
    try:
        client.stat_object(settings.minio_bucket_raw, key)
        return key
    except S3Error:
        return None


def find_parsed_object_key(
    filename: str,
    source_tag: str = "aia-form",
    suffixes: tuple[str, ...] = (".md", ".txt"),
) -> Optional[str]:
    client = get_minio_client()
    normalized_pdf = normalize_form_filename(filename, suffix=".pdf")
    normalized_names = {
        f"{normalized_pdf.rsplit('.', 1)[0]}{suffix}"
        for suffix in suffixes
    }
    prefix = f"{source_tag}/"

    try:
        for obj in client.list_objects(
            settings.minio_bucket_parsed,
            prefix=prefix,
            recursive=True,
        ):
            if obj.object_name.rsplit("/", 1)[-1] in normalized_names:
                return obj.object_name
    except S3Error:
        return None
    return None


def download_parsed_text(object_key: str) -> str:
    client = get_minio_client()
    resp = client.get_object(settings.minio_bucket_parsed, object_key)
    try:
        return resp.read().decode("utf-8")
    finally:
        resp.close()
        resp.release_conn()


# ── Cleanup helpers ───────────────────────────────────────────────────────────

def remove_objects_by_prefix(bucket: str, prefix: str) -> int:
    client = get_minio_client()
    deleted = 0
    try:
        for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
            client.remove_object(bucket, obj.object_name)
            deleted += 1
    except S3Error as exc:
        print(f"[minio] warn — could not remove objects under '{bucket}/{prefix}': {exc}")
    return deleted


def clear_source_tag(source_tag: str) -> dict[str, int]:
    """Remove all raw and parsed objects belonging to a source tag."""
    prefix = f"{source_tag}/"
    return {
        settings.minio_bucket_raw: remove_objects_by_prefix(settings.minio_bucket_raw, prefix),
        settings.minio_bucket_parsed: remove_objects_by_prefix(settings.minio_bucket_parsed, prefix),
    }


# ── Presigned URL (optional, for debug / preview) ─────────────────────────────

def presigned_url(bucket: str, key: str, expires_seconds: int = 3600) -> str:
    """Return a presigned GET URL valid for *expires_seconds*."""
    from datetime import timedelta

    client = get_minio_client()
    return client.presigned_get_object(
        bucket_name=bucket,
        object_name=key,
        expires=timedelta(seconds=expires_seconds),
    )