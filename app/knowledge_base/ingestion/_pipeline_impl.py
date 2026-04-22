"""通用导入工具 —— 支持 JSON 数据和带 PDF 链接的表单。

支持的数据导入模式
----------------------
1. JSON 知识文件 (保单服务, 产品, 分公司, 菜单 …)  — 现有功能
2. 表单 JSON (表单下载-个险/团险.json)  — 新功能
   每个条目都包含一个指向 aia.com.cn 上 PDF 文件的 ``full_url``。
   处理流程：下载 PDF → 将原始文件存入 MinIO → 解析文本 (使用 PyMuPDF + OCR)
   → 将解析后的文本存入 MinIO → 切片 → 向量化 → 更新至 Qdrant。

防重复机制
-----------
系统会计算内容的哈希值（基于原始字节的 MD5），并将其作为 ``doc_hash`` 存入 Qdrant 的有效负载中。
如果在重新导入时哈希值没有变化，该文件就会被跳过。

自动识别的分类
---------------------
1. service_categories
2. forms / items with full_url  <- 会触发 PDF 下载流程
3. products
4. branches
5. menu
6. generic (list or dict)
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from qdrant_client import QdrantClient, models

from app.config import settings
from app.knowledge_base.config import MODEL_NAME, VECTOR_SIZE
from app.knowledge_base.core.embedding import get_model
from app.knowledge_base.processing.chunker import chunk_text
from app.knowledge_base.processing.normalizer import normalize_category

logger = logging.getLogger(__name__)

COLLECTION_NAME = "aia_knowledge_base"
DEFAULT_COLLECTION = COLLECTION_NAME
_BATCH = 32


# ── Qdrant / model singletons ─────────────────────────────────────────────────

def _client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrantclient_url,
        api_key=settings.qdrantclient_key or None,
    )


def _model():
    return get_model()


def _doc_id(text: str) -> int:
    """Stable uint64 id from content MD5."""
    return int(hashlib.md5(text.encode()).hexdigest()[:16], 16) % (2 ** 63)


def _ensure_collection(client: QdrantClient, name: str = COLLECTION_NAME) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if name in existing:
        info = client.get_collection(name)
        vectors = getattr(getattr(info.config, "params", None), "vectors", None)
        current_size = (
            getattr(vectors, "size", None)
            if not isinstance(vectors, dict)
            else next(
                (
                    value.get("size") if isinstance(value, dict) else getattr(value, "size", None)
                    for value in vectors.values()
                ),
                None,
            )
        )
        if current_size is not None and int(current_size) != VECTOR_SIZE:
            raise RuntimeError(
                f"Collection '{name}' vector size is {current_size}, but embedding model "
                f"'{MODEL_NAME}' requires {VECTOR_SIZE}. Please recreate the collection and re-ingest data."
            )
        return
    client.create_collection(
        name,
        vectors_config=models.VectorParams(
            size=VECTOR_SIZE, distance=models.Distance.COSINE
        ),
    )


def _embedding_chunk_size() -> int:
    return max(80, settings.embedding_max_input_chars or settings.pdf_chunk_size)


def _embedding_chunk_overlap(chunk_size: int) -> int:
    return min(settings.pdf_chunk_overlap, max(chunk_size // 5, 0))


def _split_docs_for_embedding_limit(docs: list[dict]) -> list[dict]:
    chunk_size = _embedding_chunk_size()
    overlap = _embedding_chunk_overlap(chunk_size)
    expanded: list[dict] = []

    for doc in docs:
        text = str(doc.get("text") or "").strip()
        payload = dict(doc.get("payload") or {})
        if not text:
            continue

        title = str(payload.get("title") or "").strip()
        content = payload.get("content")
        if isinstance(content, str) and content.strip():
            content_chunks = chunk_text(content, chunk_size=chunk_size, overlap=overlap)
            text_chunks = [
                f"「{title}」\n{chunk}" if title else chunk
                for chunk in content_chunks
            ]
        else:
            text_chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
            content_chunks = text_chunks

        if not text_chunks:
            continue

        original_chunk_index = payload.get("chunk_index")
        original_chunk_total = payload.get("chunk_total")
        split_required = len(text_chunks) > 1 or len(text) > chunk_size

        for index, text_chunk in enumerate(text_chunks):
            item_payload = dict(payload)
            item_payload["content"] = content_chunks[index]
            item_payload["chunk_index"] = index
            item_payload["chunk_total"] = len(text_chunks)
            if split_required:
                item_payload["embedding_chunked"] = True
                if original_chunk_index is not None:
                    item_payload["source_chunk_index"] = original_chunk_index
                if original_chunk_total is not None:
                    item_payload["source_chunk_total"] = original_chunk_total
            expanded.append({"text": text_chunk, "payload": item_payload})

    return expanded


# ── Schema detection ──────────────────────────────────────────────────────────

def _detect_schema(data: Any) -> str:
    if isinstance(data, dict):
        keys = set(data.keys())
        if "service_categories" in keys:
            return "service_categories"
        # 表单下载 JSON: top-level "items" list with "full_url" or "filename" fields
        if "items" in keys and isinstance(data.get("items"), list):
            sample = data["items"][:1]
            if sample and isinstance(sample[0], dict):
                if "full_url" in sample[0] or "filename" in sample[0]:
                    return "forms"
                # 客户服务菜单: items with title+url but no full_url/filename
                if "title" in sample[0] and "url" in sample[0] and "full_url" not in sample[0]:
                    return "menu"
        if "forms" in keys or "form_categories" in keys:
            return "forms"
        # 个险+团险产品页
        if "personal_insurance_menu" in keys or "group_insurance_menu" in keys:
            return "products_page"
        if "personal_insurance_recommended_products" in keys:
            return "personal_insurance_recommended_products"
        if "group_insurance_recommended_products" in keys:
            return "group_insurance_recommended_products"
        if "on_sale_products_list" in keys and isinstance(data.get("on_sale_products_list"), list):
            sample = data["on_sale_products_list"][:1]
            if sample and isinstance(sample[0], dict) and "productName" in sample[0]:
                return "products_list"
        if "products" in keys or any("product" in k for k in keys):
            return "products"
        # 分公司页面（含 regions 数组）
        if "regions" in keys:
            return "branches"
        if "branch" in keys:
            return "branches"
        if "menu" in keys or "menus" in keys:
            return "menu"
    if isinstance(data, list):
        # 在售产品基本信息：数组元素含 productName
        if data and isinstance(data[0], dict) and "productName" in data[0]:
            return "products_list"
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
            base_text = f"「{title}」\n{content}"

            # 记录完整属性：分类级 + 条目级全部字段
            payload = {
                "title": title,
                "content": content,
                "service_name": sname,
                "service_url": surl,
                "category": sname,
                "schema": "service_categories",
                "service_category": cat,
                "item": item,
                "chunk_enabled": len(content) > settings.pdf_chunk_size,
            }

            if len(content) > settings.pdf_chunk_size:
                chunks = chunk_text(content)
                for idx, chunk in enumerate(chunks):
                    text = f"「{title}」\n{chunk}"
                    docs.append({
                        "text": text,
                        "payload": {
                            **payload,
                            "content": chunk,
                            "chunk_index": idx,
                            "chunk_total": len(chunks),
                        },
                    })
            else:
                docs.append({
                    "text": base_text,
                    "payload": {
                        **payload,
                        "chunk_index": 0,
                        "chunk_total": 1,
                    },
                })
    return docs


def _flatten_generic(data: Any, source_file: str = "") -> list[dict]:
    """通用数据清洗与提取"""
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


def _flatten_products_list(data: list, source_file: str = "") -> list[dict]:
    """在售产品基本信息.json — 顶层数组，每条含 productName/productStatus/productGroup 等字段。"""
    docs = []
    file_url_prefix = (
        "https://www.aia.com.cn/etc.clientlibs/cn-wise/clientlibs/"
        "clientlib-base/resources/pdfviewer/viewer.html?file=/content/dam/cn/zh-cn/docs/public-disclosure/"
    )
    for obj in data:
        name = obj.get("productName", "")
        status = obj.get("productStatus", "")
        group = obj.get("productGroup", "")

        file_fields = {
            "productItem": obj.get("productItem"),
            "ratesTable": obj.get("ratesTable"),
            "cashValueTable": obj.get("cashValueTable"),
            "productInstruction": obj.get("productInstruction"),
            "followUpService": obj.get("followUpService"),
        }
        full_urls = {
            key: f"{file_url_prefix}{value}" if value else ""
            for key, value in file_fields.items()
        }

        parts = [f"产品名称：{name}", f"状态：{status}"]
        if group:
            parts.append(f"产品组：{group}")
        for key in ("productItem", "ratesTable", "cashValueTable", "productInstruction", "followUpService"):
            value = file_fields.get(key)
            if value:
                parts.append(f"{key}：{value}")
                parts.append(f"{key}链接：{full_urls[key]}")
        content = "\n".join(parts)
        text = f"「{name}」\n{content}"
        docs.append({"text": text, "payload": {
            "title": name,
            "content": content,
            "service_name": source_file,
            "service_url": full_urls.get("productInstruction") or full_urls.get("productItem") or "",
            "category": "在售产品",
            "product_status": status,
            "product_group": group,
            "product_item": file_fields.get("productItem") or "",
            "rates_table": file_fields.get("ratesTable") or "",
            "cash_value_table": file_fields.get("cashValueTable") or "",
            "product_instruction": file_fields.get("productInstruction") or "",
            "follow_up_service": file_fields.get("followUpService") or "",
            "product_item_url": full_urls.get("productItem") or "",
            "rates_table_url": full_urls.get("ratesTable") or "",
            "cash_value_table_url": full_urls.get("cashValueTable") or "",
            "product_instruction_url": full_urls.get("productInstruction") or "",
            "follow_up_service_url": full_urls.get("followUpService") or "",
            "schema": "products_list",
        }})
    return docs


def _flatten_products_page(data: dict, source_file: str = "") -> list[dict]:
    """个险+团险产品.json — 含 personal_insurance_menu / group_insurance_menu 分类描述列表。"""
    docs = []
    for section_key, section_label in (
        ("personal_insurance_menu", "个险"),
        ("group_insurance_menu", "团险"),
    ):
        for item in data.get(section_key, []):
            name = item.get("name", "")
            desc = item.get("description", "")
            text = f"「{section_label}·{name}」\n{desc}"
            docs.append({"text": text, "payload": {
                "title": name,
                "content": desc,
                "service_name": section_label,
                "service_url": "",
                "category": f"{section_label}产品",
                "schema": "products_page",
                "source_file": source_file,
            }})
    return docs


def _flatten_personal_insurance_recommended_products(data: dict, source_file: str = "") -> list[dict]:
    """个险-推荐产品.json — 按推荐分类展开产品卡片信息。"""
    docs = []
    for category_name, items in (data.get("personal_insurance_recommended_products") or {}).items():
        for item in items:
            name = item.get("name") or ""
            attributes = item.get("productAttributes") or {}
            text = f"「{category_name}·{name}」\n{attributes}"
            docs.append({"text": text, "payload": {
                "title": name,
                "content": attributes,
                "service_name": category_name,
                "service_url": "",
                "category": "个险推荐产品",
                "schema": "recommended_products",
                "source_file": source_file,
            }})
    return docs

def _flatten_group_insurance_recommended_products(data: dict, source_file: str = "") -> list[dict]:
    """团险-推荐产品.json — 按推荐分类展开产品卡片信息。"""
    docs = []
    for category_name, items in (data.get("group_insurance_recommended_products") or {}).items():
        for item in items:
            name = item.get("name") or ""
            attributes = item.get("productAttributes") or {}
            text = f"「{category_name}·{name}」\n{attributes}"
            docs.append({"text": text, "payload": {
                "title": name,
                "content": attributes,
                "service_name": category_name,
                "service_url": "",
                "category": "团险推荐产品",
                "schema": "recommended_products",
                "source_file": source_file,
            }})
    return docs

def _flatten_branches(data: dict, source_file: str = "") -> list[dict]:
    """分公司页面 JSON — 含 regions 数组，每个 region 有 flexitems 或 news_items。"""
    docs = []
    for region in data.get("regions", []):
        rname = region.get("region_name", "")
        rurl = region.get("region_url", "")
        # 分公司基本信息（地址、电话、服务时间）
        flex = region.get("flexitems")
        if flex and isinstance(flex, dict):
            full_text = flex.get("full_text", "")
            address = flex.get("address", "")
            phone = flex.get("phone", "")
            service_time = flex.get("service_time", "")
            content = full_text or f"地址：{address}\n服务时间：{service_time}\n电话：{phone}"
            text = f"「{rname}分公司」\n{content}"
            docs.append({"text": text, "payload": {
                "title": f"{rname}分公司",
                "content": content,
                "service_name": rname,
                "service_url": f"https://www.aia.com.cn{rurl}",
                "category": "分公司",
                "address": address,
                "phone": phone,
                "schema": "branches",
                "source_file": source_file,
            }})
        # 分公司新闻/活动条目
        for news in region.get("news_items", []):
            title = news.get("title", "")
            desc = news.get("description", "")
            full_url = news.get("full_url", "")
            if not (title or desc):
                continue
            content = f"{title}\n{desc}".strip()
            text = f"「{rname}·{title}」\n{desc}"
            docs.append({"text": text, "payload": {
                "title": title,
                "content": content,
                "service_name": rname,
                "service_url": full_url,
                "category": "分公司动态",
                "schema": "branches",
                "source_file": source_file,
            }})
    return docs


def _flatten_forms_text(data: dict, source_file: str = "") -> list[dict]:
    """表单下载 JSON — ingest form names + download URLs as text (no PDF download)."""
    docs = []
    page_name = data.get("page_name", source_file)
    for item in data.get("items", []):
        filename = item.get("filename", "")
        full_url = item.get("full_url", "")
        url = item.get("url", full_url)
        content = f"表单名称：{filename}\n下载地址：{full_url or url}"
        text = f"\u300c{filename}\u300d\n{content}"
        docs.append({"text": text, "payload": {
            "title": filename,
            "content": content,
            "service_name": page_name,
            "service_url": full_url or url,
            "category": page_name,
            "schema": "forms_text",
            "source_file": source_file,
        }})
    return docs


def _flatten_menu(data: Any, source_file: str = "") -> list[dict]:
    """客户服务菜单 JSON — flat list of navigation items."""
    docs = []
    items = data.get("items", []) if isinstance(data, dict) else data
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "")
        url = item.get("url", "")
        text_val = item.get("text", title)
        content = f"菜单项：{title}\n链接：https://www.aia.com.cn{url}"
        text = f"\u300c{title}\u300d\n{content}"
        docs.append({"text": text, "payload": {
            "title": title,
            "content": content,
            "service_name": "客户服务导航",
            "service_url": f"https://www.aia.com.cn{url}",
            "category": "客户服务导航",
            "schema": "menu",
            "source_file": source_file,
        }})
    return docs


def flatten_json(data: Any, source_file: str = "") -> list[dict]:
    """Auto-detect schema and return list of {text, payload} dicts."""
    schema = _detect_schema(data)
    if schema == "service_categories":
        return _flatten_service_categories(data)
    if schema == "forms":
        return _flatten_forms_text(data, source_file=source_file)
    if schema == "products_list":
        products_data = data.get("on_sale_products_list", data) if isinstance(data, dict) else data
        return _flatten_products_list(products_data, source_file=source_file)
    if schema == "products_page":
        return _flatten_products_page(data, source_file=source_file)
    if schema == "personal_insurance_recommended_products":
        return _flatten_personal_insurance_recommended_products(data, source_file=source_file)
    if schema == "group_insurance_recommended_products":
        return _flatten_group_insurance_recommended_products(data, source_file=source_file)
    if schema == "branches":
        return _flatten_branches(data, source_file=source_file)
    if schema == "menu":
        return _flatten_menu(data, source_file=source_file)
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
    source_tag: str = "aia-form",
    progress_cb=None,
) -> dict:
    """Ingest a forms JSON whose items contain PDF URLs.

    For each supported PDF item:
      1. Download PDF
      2. Store raw PDF in MinIO
      3. Parse document into Markdown via DeepSeek-OCR
      4. Store Markdown in MinIO
      5. Chunk semantically
      6. Embed and upsert into Qdrant
    """
    from app.knowledge_base.processing.parser import extract_pdf_markdown
    from app.knowledge_base.processing.chunker import chunk_markdown
    from app.knowledge_base.core.storage import (
        ensure_buckets,
        upload_raw,
        upload_parsed,
        raw_object_exists,
        content_hash,
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
                markdown,
                safe_name,
                doc_hash,
                source_tag=source_tag,
                suffix=".md",
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
            chunks,
            batch_size=_BATCH,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

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
    from app.knowledge_base.core.storage import clear_source_tag

    client = _client()
    deleted_points = 0
    try:
        client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    should=[
                        models.FieldCondition(
                            key="source_file",
                            match=models.MatchValue(value=source_file),
                        ),
                        models.FieldCondition(
                            key="source_tag",
                            match=models.MatchValue(value=source_tag),
                        ),
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


# ── Text file ingestor (.txt) ────────────────────────────────────────────────

def ingest_text_file(
    file_path: str,
    *,
    collection_name: str,
    title: str = "",
) -> dict:
    """Chunk a plain-text file and ingest into Qdrant.

    Used for files like 反保险欺诈提示及举报渠道.txt.
    """
    from app.knowledge_base.processing.chunker import chunk_text

    path = Path(file_path)
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {"file": path.name, "schema": "text", "doc_count": 0}

    chunks = chunk_text(text)
    if not chunks:
        return {"file": path.name, "schema": "text", "doc_count": 0}

    client = _client()
    _ensure_collection(client, collection_name)
    model = _model()

    vectors = model.encode(
        chunks, batch_size=_BATCH, normalize_embeddings=True, show_progress_bar=False
    )
    # Use the file title/name as the service/category so we don't attribute
    # text chunks to the Qdrant collection name (e.g. "aia_knowledge_base").
    display_name = title or path.stem
    points = [
        models.PointStruct(
            id=_doc_id(chunks[i] + path.name),
            vector=vectors[i].tolist(),
            payload={
                "title": title or path.stem,
                "content": chunks[i],
                "service_name": display_name,
                "service_url": "",
                "category": display_name,
                "category_canonical": normalize_category(display_name),
                "schema": "text",
                "source_file": path.name,
                "chunk_index": i,
                "chunk_total": len(chunks),
            },
        )
        for i in range(len(chunks))
    ]
    client.upsert(collection_name, points=points)
    logger.info(f"[ingest] '{collection_name}' <- {len(points)} chunks from {path.name}")
    return {"file": path.name, "schema": "text", "doc_count": len(points)}


# ── 全量 AIA 数据入库入口 ──────────────────────────────────────────────────────

def ingest_all_aia_data(aia_data_dir: str = "") -> list[dict]:
    """One-shot: ingest all cleaned aia_data files into local Qdrant.

    Skips 表单下载-个险/团险.json (PDF pipeline — already processed via MinIO).
    For service_categories/ files, each JSON is ingested into its own named
    collection matching the Chinese service_name.

    Call this from a script or the FastAPI knowledge router.
    """
    import os
    base = Path(aia_data_dir) if aia_data_dir else (
        Path(__file__).resolve().parent.parent.parent / "aia_data"
    )
    results: list[dict] = []

    # ── 1. service_categories/ — 8 个分类，各自独立 collection ────────────────
    sc_dir = base / "service_categories"
    if sc_dir.exists():
        for p in sorted(sc_dir.glob("*.json")):
            try:
                r = ingest_file(str(p))
                results.append(r)
                logger.info(f"[ingest_all] {p.name}: {r}")
            except Exception as exc:
                results.append({"file": p.name, "schema": "error", "doc_count": 0, "error": str(exc)})
                logger.error(f"[ingest_all] {p.name} FAILED: {exc}")

    # ── 2. 在售产品基本信息.json → '在售产品' collection ──────────────────────
    for fname, cname in [
        ("在售产品基本信息.json", "在售产品"),
    ]:
        p = base / fname
        if p.exists():
            try:
                r = ingest_file(str(p), collection_name=cname)
                results.append(r)
                logger.info(f"[ingest_all] {fname}: {r}")
            except Exception as exc:
                results.append({"file": fname, "schema": "error", "doc_count": 0, "error": str(exc)})
                logger.error(f"[ingest_all] {fname} FAILED: {exc}")

    # ── 3. 个险+团险产品.json → '产品分类' collection ──────────────────────────
    for fname, cname in [
        ("个险+团险产品.json", "产品分类"),
    ]:
        p = base / fname
        if p.exists():
            try:
                r = ingest_file(str(p), collection_name=cname)
                results.append(r)
                logger.info(f"[ingest_all] {fname}: {r}")
            except Exception as exc:
                results.append({"file": fname, "schema": "error", "doc_count": 0, "error": str(exc)})
                logger.error(f"[ingest_all] {fname} FAILED: {exc}")

    # ── 4. 分公司数据 → '分公司' collection ──────────────────────────────────
    for fname in ("所有分公司页面.json", "分公司页面.json"):
        p = base / fname
        if p.exists():
            try:
                r = ingest_file(str(p), collection_name="分公司")
                results.append(r)
                logger.info(f"[ingest_all] {fname}: {r}")
            except Exception as exc:
                results.append({"file": fname, "schema": "error", "doc_count": 0, "error": str(exc)})
                logger.error(f"[ingest_all] {fname} FAILED: {exc}")
            break  # 优先用 所有分公司页面.json，存在则跳过另一个

    # ── 5. 表单下载-个险.json → '个险表单' collection ────────────────────────
    for fname, cname in [
        ("表单下载-个险.json", "个险表单"),
        ("表单下载-团险.json", "团险表单"),
    ]:
        p = base / fname
        if p.exists():
            try:
                r = ingest_file(str(p), collection_name=cname)
                results.append(r)
                logger.info(f"[ingest_all] {fname}: {r}")
            except Exception as exc:
                results.append({"file": fname, "schema": "error", "doc_count": 0, "error": str(exc)})
                logger.error(f"[ingest_all] {fname} FAILED: {exc}")

    # ── 6. 客户服务菜单.json → '客户服务导航' collection ─────────────────────
    p = base / "客户服务菜单.json"
    if p.exists():
        try:
            r = ingest_file(str(p), collection_name="客户服务导航")
            results.append(r)
            logger.info(f"[ingest_all] 客户服务菜单.json: {r}")
        except Exception as exc:
            results.append({"file": "客户服务菜单.json", "schema": "error", "doc_count": 0, "error": str(exc)})
            logger.error(f"[ingest_all] 客户服务菜单.json FAILED: {exc}")

    # ── 7. 反保险欺诈提示及举报渠道.txt → '反欺诈' collection ────────────────
    p = base / "反保险欺诈提示及举报渠道.txt"
    if p.exists():
        try:
            r = ingest_text_file(
                str(p),
                collection_name="反欺诈",
                title="反保险欺诈提示及举报渠道",
            )
            results.append(r)
            logger.info(f"[ingest_all] 反保险欺诈提示及举报渠道.txt: {r}")
        except Exception as exc:
            results.append({"file": "反保险欺诈提示及举报渠道.txt", "schema": "error", "doc_count": 0, "error": str(exc)})
            logger.error(f"[ingest_all] 反保险欺诈提示及举报渠道.txt FAILED: {exc}")

    # ── 汇总 ──────────────────────────────────────────────────────────────────
    total = sum(r.get("doc_count", 0) for r in results)
    errors = [r for r in results if r.get("schema") == "error"]
    logger.info(f"[ingest_all] DONE — {len(results)} files, {total} docs, {len(errors)} errors")
    return results


# ── Core ingest function ──────────────────────────────────────────────────────

def ingest_file(file_path: str, *, collection_name: str = DEFAULT_COLLECTION, progress_cb=None) -> dict:
    """Parse a JSON file and ingest into Qdrant.

    For forms schema (items with full_url): triggers PDF download pipeline.
    For service_categories schema: writes all category documents into the
      single collection named by collection_name.
    For all other schemas: embeds JSON text directly into collection_name.

    Returns: {"file": str, "schema": str, "doc_count": int}
    """
    path = Path(file_path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    schema = _detect_schema(data)

    # service_categories: ingest all categories into the same collection
    if schema == "service_categories":
        qdrant = _client()
        model = _model()
        total = 0
        _ensure_collection(qdrant, collection_name)
        cat_docs: list[dict] = []
        for cat in data.get("service_categories", []):
            cat_docs.extend(_flatten_service_categories({"service_categories": [cat]}))
        cat_docs = _split_docs_for_embedding_limit(cat_docs)
        if not cat_docs:
            return {"file": path.name, "schema": schema, "doc_count": 0, "collections": [collection_name]}

        texts = [d["text"] for d in cat_docs]
        vectors = model.encode(
            texts, batch_size=_BATCH, normalize_embeddings=True, show_progress_bar=False
        )
        points = []
        for i in range(len(cat_docs)):
            payload = {**cat_docs[i]["payload"], "source_file": path.name}
            payload["category_canonical"] = normalize_category(
                payload.get("category") or payload.get("service_name") or path.name
            )
            points.append(
                models.PointStruct(
                    id=_doc_id(cat_docs[i]["text"]),
                    vector=vectors[i].tolist(),
                    payload=payload,
                )
            )
        qdrant.upsert(collection_name, points=points)
        total += len(points)
        logger.info(f"[ingest] '{collection_name}' <- {len(points)} docs from {path.name}")
        return {
            "file": path.name,
            "schema": schema,
            "doc_count": total,
            "collections": [collection_name],
        }

    # forms: reprocess via DeepSeek-OCR Markdown pipeline
    if schema == "forms":
        source_tag = "aia-form-group" if "团险" in path.name else "aia-form-personal"
        return ingest_forms_pdf(
            data,
            source_file=path.name,
            collection_name=collection_name,
            source_tag=source_tag,
            progress_cb=progress_cb,
        )

    # Standard JSON text ingestion
    docs = flatten_json(data, source_file=path.name)
    docs = _split_docs_for_embedding_limit(docs)
    if not docs:
        return {"file": path.name, "schema": schema, "doc_count": 0}

    client = _client()
    _ensure_collection(client, collection_name)
    model = _model()

    texts = [d["text"] for d in docs]
    vectors = model.encode(
        texts, batch_size=_BATCH, normalize_embeddings=True, show_progress_bar=False
    )

    points = []
    for i in range(len(docs)):
        payload = {**docs[i]["payload"], "source_file": path.name}
        payload["category_canonical"] = normalize_category(
            payload.get("category") or payload.get("service_name") or path.name
        )
        points.append(
            models.PointStruct(
                id=_doc_id(docs[i]["text"]),
                vector=vectors[i].tolist(),
                payload=payload,
            )
        )
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
