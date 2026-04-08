"""MinIO 对象存储封装（原 storage.py 内容）。"""
# 直接从原模块重导出，保持 core/storage.py 作为规范路径。
# 原始实现位于 app/knowledge_base/storage.py（现已成为 shim）。
from app.knowledge_base.core._storage_impl import (
    get_minio_client,
    ensure_buckets,
    content_hash,
    normalize_form_filename,
    upload_raw,
    upload_parsed,
    raw_object_exists,
    find_parsed_object_key,
    download_parsed_text,
    remove_objects_by_prefix,
    clear_source_tag,
    presigned_url,
)

__all__ = [
    "get_minio_client",
    "ensure_buckets",
    "content_hash",
    "normalize_form_filename",
    "upload_raw",
    "upload_parsed",
    "raw_object_exists",
    "find_parsed_object_key",
    "download_parsed_text",
    "remove_objects_by_prefix",
    "clear_source_tag",
    "presigned_url",
]
