#!/usr/bin/env python3
"""重建表单下载知识库：先清脏数据，再用 DeepSeek-OCR 重新处理。

默认处理：
1) aia_data/表单下载-个险.json
2) aia_data/表单下载-团险.json

支持单表单重处理：
- 通过 --form-name 指定表单名，仅重跑该条 item（不清理整文件历史数据）
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.env_loader import EnvLoader

EnvLoader.load()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _resolve_default_paths() -> list[Path]:
    return [
        ROOT / "aia_data" / "表单下载-个险.json",
        ROOT / "aia_data" / "表单下载-团险.json",
    ]


def _source_tag_for_file(path: Path) -> str:
    return "aia-form-group" if "团险" in path.name else "aia-form-personal"


def _normalize_form_name(name: str) -> str:
    return (name or "").replace("《", "").replace("》", "").replace("（", "").replace("）", "").replace(" ", "").strip().lower()


def reprocess_one(file_path: Path, collection_name: str) -> dict:
    """重建整份表单 JSON（先清理旧数据，再全量重建）。"""
    from app.knowledge_base.ingestion.pipeline import clear_form_knowledge, ingest_file

    source_tag = _source_tag_for_file(file_path)
    cleanup = clear_form_knowledge(
        collection_name=collection_name,
        source_file=file_path.name,
        source_tag=source_tag,
    )
    logger.info(
        "[cleanup] %s -> qdrant=%s raw=%s parsed=%s",
        file_path.name,
        cleanup.get("qdrant_points"),
        cleanup.get("raw_objects"),
        cleanup.get("parsed_objects"),
    )

    result = ingest_file(str(file_path), collection_name=collection_name)
    result["cleanup"] = cleanup
    return result


def reprocess_single_form(file_path: Path, collection_name: str, form_name: str) -> dict:
    """仅重处理一个指定表单（不清理整文件历史数据）。"""
    from app.knowledge_base.ingestion.pipeline import ingest_forms_pdf

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", []) if isinstance(data, dict) else []
    if not items:
        raise ValueError(f"文件中未找到 items: {file_path}")

    target_norm = _normalize_form_name(form_name)
    target_item = None
    target_item = next(
        (item for item in items if _normalize_form_name(item.get("filename", "")) == target_norm),
        None
    )
    if target_item is None and target_norm:
        target_item = next(
            (item for item in items if target_norm in _normalize_form_name(item.get("filename", ""))),
            None
        )
    if target_item is None:
        raise ValueError(f"未匹配到表单: {form_name}")

    single_data = {
        "page_name": data.get("page_name", file_path.name),
        "items": [target_item],
    }
    source_tag = _source_tag_for_file(file_path)
    result = ingest_forms_pdf(
        single_data,
        source_file=file_path.name,
        collection_name=collection_name,
        source_tag=source_tag,
    )
    result["target_form"] = target_item.get("filename", "")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="重建表单下载知识库（DeepSeek-OCR Markdown）")
    parser.add_argument(
        "--collection-name",
        default="aia_knowledge_base",
        help="Qdrant collection 名称，默认 aia_knowledge_base",
    )
    parser.add_argument(
        "--form-name",
        default="",
        help="可选：仅重处理指定表单名（仅支持单个 JSON 文件）",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="可选：指定要处理的 JSON 文件路径；默认处理个险/团险两个文件",
    )
    args = parser.parse_args()

    file_paths = [Path(p) for p in args.files] if args.files else _resolve_default_paths()
    missing = [str(p) for p in file_paths if not p.exists()]
    if missing:
        raise SystemExit(f"以下文件不存在: {missing}")

    if args.form_name and len(file_paths) != 1:
        raise SystemExit("使用 --form-name 时，请只传入一个 JSON 文件路径")

    started = time.time()
    results: list[dict] = []

    for file_path in file_paths:
        logger.info("=" * 72)
        logger.info("开始重处理: %s", file_path.name)
        logger.info("=" * 72)
        try:
            if args.form_name:
                result = reprocess_single_form(file_path, args.collection_name, args.form_name)
                logger.info("[done] %s -> target=%s, %s chunks", file_path.name, result.get("target_form", ""), result.get("doc_count", 0))
            else:
                result = reprocess_one(file_path, args.collection_name)
                logger.info("[done] %s -> %s chunks", file_path.name, result.get("doc_count", 0))

            results.append(result)
        except Exception as exc:
            logger.exception("[failed] %s", file_path.name)
            results.append(
                {
                    "file": file_path.name,
                    "schema": "error",
                    "doc_count": 0,
                    "error": str(exc),
                }
            )            
    elapsed = time.time() - started

    print(f"\n{'=' * 90}")
    print(f"{'文件':<24} {'Schema':<20} {'Chunk数':>10} {'失败':>8}")
    print(f"{'-' * 90}")
    for row in results:
        print(
            f"{(row.get('file') or '')[:22]:<24} "
            f"{(row.get('schema') or '')[:18]:<20} "
            f"{row.get('doc_count', 0):>10} "
            f"{row.get('failed', 0):>8}"
        )
        if row.get("target_form"):
            print(f"  target -> {row['target_form']}")
        cleanup = row.get("cleanup") or {}
        if cleanup:
            print(
                f"  cleanup -> qdrant={cleanup.get('qdrant_points')} "
                f"raw={cleanup.get('raw_objects', 0)} parsed={cleanup.get('parsed_objects', 0)}"
            )
        if row.get("error"):
            print(f"  error -> {row['error']}")
    print(f"{'-' * 90}")
    print(f"总耗时: {elapsed:.1f}s")
    print(f"{'=' * 90}\n")


if __name__ == "__main__":
    main()
