#!/usr/bin/env python3
"""全量入库脚本 — 将 aia_data/ 所有已清洗数据写入本地 Qdrant。

用法:
    python scripts/run_ingest_all.py
    python scripts/run_ingest_all.py --data-dir E:/aia_robot/aia_data
    python scripts/run_ingest_all.py --verify       # 入库后打印各 collection point count

注意:
    - 确保本地 Qdrant Docker 已启动 (http://localhost:6333)
    - 表单下载-个险/团险.json 的 PDF 已由 MinIO 处理，此脚本跳过 PDF 下载
      若需重新处理表单 PDF，单独调用 ingest_file() 即可
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# ── 确保项目根目录在 sys.path ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def verify_collections() -> None:
    """打印所有 collection 的名称和 point count。"""
    from qdrant_client import QdrantClient
    from app.config import settings

    client = QdrantClient(url=settings.qdrantclient_url or "http://localhost:6333")
    collections = client.get_collections().collections
    if not collections:
        print("\n[verify] Qdrant 中暂无 collection。")
        return

    print(f"\n{'='*55}")
    print(f"{'Collection 名称':<25} {'Point Count':>12}")
    print(f"{'-'*55}")
    total_points = 0
    for col in sorted(collections, key=lambda c: c.name):
        info = client.get_collection(col.name)
        count = info.points_count or 0
        total_points += count
        status = "✓" if count > 0 else "✗ EMPTY"
        print(f"{col.name:<25} {count:>12,}  {status}")
    print(f"{'-'*55}")
    print(f"{'TOTAL':<25} {total_points:>12,}")
    print(f"{'='*55}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="AIA Robot 全量知识库入库脚本")
    parser.add_argument(
        "--data-dir",
        default="",
        help="aia_data 目录路径（默认自动推断）",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="入库完成后打印各 collection 的 point count",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="仅打印 collection 状态，不执行入库",
    )
    args = parser.parse_args()

    if args.verify_only:
        verify_collections()
        return

    from app.knowledge_base.ingest import ingest_all_aia_data

    logger.info("="*55)
    logger.info(" AIA Robot 全量知识库入库开始")
    logger.info("="*55)

    t0 = time.time()
    results = ingest_all_aia_data(aia_data_dir=args.data_dir)
    elapsed = time.time() - t0

    # ── 结果汇总 ──────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"{'文件':<30} {'Schema':<16} {'Doc数':>6}")
    print(f"{'-'*55}")
    for r in results:
        fname = r.get("file", "")[:28]
        schema = r.get("schema", "")[:14]
        count = r.get("doc_count", 0)
        err = r.get("error", "")
        flag = "  ✗" if err else ""
        print(f"{fname:<30} {schema:<16} {count:>6}{flag}")
        if err:
            print(f"  错误: {err}")
        if r.get("collections"):
            print(f"  -> collections: {r['collections']}")
    print(f"{'-'*55}")
    total_docs = sum(r.get("doc_count", 0) for r in results)
    error_count = sum(1 for r in results if r.get("error"))
    print(f"总计: {len(results)} 文件  {total_docs} 条向量  {error_count} 个错误  耗时 {elapsed:.1f}s")
    print(f"{'='*55}\n")

    if args.verify or error_count == 0:
        verify_collections()

    if error_count > 0:
        logger.warning(f"{error_count} 个文件入库失败，请检查上方错误信息。")
        sys.exit(1)


if __name__ == "__main__":
    main()
