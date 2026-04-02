#!/usr/bin/env python3
"""重建表单下载知识库：先清脏数据，再用 DeepSeek-OCR 重新处理。

默认处理：
1) aia_data/表单下载-个险.json
2) aia_data/表单下载-团险.json

行为：
- 清理 Qdrant 中对应 source_file/source_tag 的旧向量数据
- 清理 MinIO 中对应 source_tag 的 raw/parsed 旧对象
- 重新下载 PDF
- 用 DeepSeek-OCR 输出 Markdown
- Markdown 存入 MinIO
- Markdown 语义分块后入 Qdrant
"""
from __future__ import annotations

import argparse
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


def reprocess_one(file_path: Path, collection_name: str) -> dict:
    """重建表单下载知识库（DeepSeek-OCR Markdown）"""
    from app.knowledge_base.ingest import clear_form_knowledge, ingest_file

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

    result = ingest_file(str(file_path), collection_name=collection_name) # 导入
    result["cleanup"] = cleanup
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="重建表单下载知识库（DeepSeek-OCR Markdown）")
    parser.add_argument(
        "--collection-name",
        default="aia_knowledge_base",
        help="Qdrant collection 名称，默认 aia_knowledge_base",
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

    started = time.time()
    results: list[dict] = []

    for file_path in file_paths:
        logger.info("=" * 72)
        logger.info("开始重处理: %s", file_path.name)
        logger.info("=" * 72)
        try:
            result = reprocess_one(file_path, args.collection_name)
            results.append(result)
            logger.info("[done] %s -> %s chunks", file_path.name, result.get("doc_count", 0))
        except Exception as exc:
            logger.exception("[failed] %s", file_path.name)
            results.append({
                "file": file_path.name,
                "schema": "error",
                "doc_count": 0,
                "error": str(exc),
            })

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
