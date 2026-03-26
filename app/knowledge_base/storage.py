"""MinIO object storage helper.

Buckets
-------
kb-raw    : original downloaded files (PDF, etc.)
kb-parsed : parsed text / JSON artefacts

Object key convention
---------------------
  {source_tag}/{yyyy}/{mm}/{doc_hash[:8]}/{filename}
  e.g.  aia-form/2026/03/ab12cd34/保险合同内容变更申请书.pdf

All public functions are synchronous (used from background threads).
"""
from __future__ import annotations

import hashlib
import io
import time
from datetime import datetime
from functools import lru_cache
from typing import Optional

from minio import Minio
from minio.error import S3Error

from app.config import settings


# ── Client singleton ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    """Return a cached MinIO client."""
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_buckets() -> None:
    """Create required buckets if they do not exist."""
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
    """Build a deterministic object key."""
    now = datetime.utcnow()
    return f"{source_tag}/{now.year}/{now.month:02d}/{doc_hash[:8]}/{filename}"


def content_hash(data: bytes) -> str:
    """Return hex MD5 of raw bytes — used as version fingerprint."""
    return hashlib.md5(data).hexdigest()


# ── Upload helpers ────────────────────────────────────────────────────────────

def upload_raw(
    data: bytes,
    filename: str,
    doc_hash: str,
    source_tag: str = "aia-form",
    content_type: str = "application/pdf",
) -> str:
    """Upload raw bytes to kb-raw bucket.  Returns the object key."""
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
) -> str:
    """Upload parsed text to kb-parsed bucket as UTF-8 .txt.  Returns the object key."""
    client = get_minio_client()
    # Store alongside the raw key but in the parsed bucket, with .txt extension
    base = filename.rsplit(".", 1)[0] if "." in filename else filename
    key = _make_key(f"{base}.txt", doc_hash, source_tag)
    encoded = text.encode("utf-8")
    client.put_object(
        bucket_name=settings.minio_bucket_parsed,
        object_name=key,
        data=io.BytesIO(encoded),
        length=len(encoded),
        content_type="text/plain; charset=utf-8",
        metadata={"doc_hash": doc_hash, "source_tag": source_tag},
    )
    return key


# ── Idempotency check ─────────────────────────────────────────────────────────

def raw_object_exists(doc_hash: str, filename: str, source_tag: str = "aia-form") -> Optional[str]:
    """Return the existing object key if a file with the same hash is already stored,
    otherwise return None.
    """
    client = get_minio_client()
    key = _make_key(filename, doc_hash, source_tag)
    try:
        client.stat_object(settings.minio_bucket_raw, key)
        return key
    except S3Error:
        return None


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
