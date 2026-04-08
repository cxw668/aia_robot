#!/usr/bin/env python3
"""将 AIA 知识库数据统一入库到 Qdrant 集合 `aia_knowledge_base`。

当前支持：
1) `aia_data/service_categories/*.json`
2) `aia_data/分公司页面.json`（若不存在则回退到 `aia_data/所有分公司页面.json`）
3) `aia_data/个险+团险产品.json`
4) `aia_data/个险-推荐产品.json`
5) `aia_data/团险-推荐产品.json`
6) `aia_data/在售产品基本信息.json`
7) `aia_data/分公司新闻.json`
8) `aia_data/反保险欺诈提示及举报渠道.txt`

实现要点：
1) 所有文档统一写入集合 `aia_knowledge_base`
2) 文本按现有 ingest.py 中的 schema 自动识别并扁平化
3) 纯文本文件通过 `ingest_text_file` 切分后写入同一集合

用法：
    python scripts/run_ingest_all.py
    python scripts/run_ingest_all.py --verify
    python scripts/run_ingest_all.py --branches-file E:/aia_robot/aia_data/分公司页面.json
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


def verify_collections(prefix_hint: str = "", collection_name: str = "") -> None:
    """打印 collection point count。

    当 `collection_name` 提供时，仅展示该 collection 的点数（便于直接查看
      http://localhost:6333/collections/<name>）。
    """
    from qdrant_client import QdrantClient
    from app.config import settings

    client = QdrantClient(url=settings.qdrantclient_url or "http://localhost:6333")

    if collection_name:
        try:
            info = client.get_collection(collection_name)
        except Exception as exc:
            print(f"\n[verify] 获取 collection {collection_name} 失败: {exc}")
            return

        count = info.points_count or 0
        print(f"\n{'=' * 55}")
        print(f"Collection: {collection_name}")
        print(f"Point Count: {count:,}")
        print(f"{'=' * 55}\n")
        return

def ingest_service_categories(data_dir: Path) -> list[dict]:
    """入库 service_categories 目录中的 JSON 文件到统一集合。"""
    from app.knowledge_base.config import DEFAULT_COLLECTION
    from app.knowledge_base.ingestion.pipeline import ingest_file

    results: list[dict] = []
    for p in sorted(data_dir.glob("*.json")):
        try:
            r = ingest_file(str(p), collection_name=DEFAULT_COLLECTION)
            results.append(r)
            logger.info(f"[ingest] {p.name}: {r.get('doc_count', 0)} docs -> {DEFAULT_COLLECTION}")
        except Exception as exc:
            logger.error(f"[ingest] {p.name} FAILED: {exc}")
            results.append({"file": p.name, "schema": "error", "doc_count": 0, "error": str(exc)})
    return results


def ingest_json_file(file_path: Path) -> dict:
    """入库单个 JSON 文件到统一集合。"""
    from app.knowledge_base.config import DEFAULT_COLLECTION
    from app.knowledge_base.ingestion.pipeline import ingest_file

    try:
        result = ingest_file(str(file_path), collection_name=DEFAULT_COLLECTION)
        logger.info(f"[ingest] {file_path.name}: {result.get('doc_count', 0)} docs -> {DEFAULT_COLLECTION}")
        return result
    except Exception as exc:
        logger.error(f"[ingest] {file_path.name} FAILED: {exc}")
        return {"file": file_path.name, "schema": "error", "doc_count": 0, "error": str(exc)}


def ingest_text(file_path: Path, title: str = "") -> dict:
    """入库单个文本文件到统一集合。"""
    from app.knowledge_base.config import DEFAULT_COLLECTION
    from app.knowledge_base.ingestion.pipeline import ingest_text_file

    try:
        result = ingest_text_file(str(file_path), collection_name=DEFAULT_COLLECTION, title=title or file_path.stem)
        logger.info(f"[ingest] {file_path.name}: {result.get('doc_count', 0)} docs -> {DEFAULT_COLLECTION}")
        return result
    except Exception as exc:
        logger.error(f"[ingest] {file_path.name} FAILED: {exc}")
        return {"file": file_path.name, "schema": "error", "doc_count": 0, "error": str(exc)}


def resolve_optional_file(explicit_path: str, *default_candidates: str) -> Path | None:
    """优先返回显式路径，否则按候选路径顺序查找。"""
    if explicit_path:
        p = Path(explicit_path)
        return p if p.exists() and p.is_file() else None

    for rel in default_candidates:
        p = ROOT / rel
        if p.exists() and p.is_file():
            return p
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="AIA 知识库统一入库脚本")
    parser.add_argument(
        "--service-categories-dir",
        default="",
        help="service_categories 目录路径（默认: aia_data/service_categories）",
    )
    parser.add_argument(
        "--branches-file",
        default="",
        help="分公司页面 JSON 文件路径（默认: aia_data/分公司页面.json）",
    )
    parser.add_argument(
        "--products-page-file",
        default="",
        help="个险+团险产品 JSON 文件路径（默认: aia_data/个险+团险产品.json）",
    )
    parser.add_argument(
        "--personal-insurance-recommended-products-file",
        default="",
        help="个险推荐产品 JSON 文件路径（默认: aia_data/个险-推荐产品.json）",
    )
    parser.add_argument(
        "--group-insurance-recommended-products-file",
        default="",
        help="团险推荐产品 JSON 文件路径（默认: aia_data/团险-推荐产品.json）",
    )
    parser.add_argument(
        "--on-sale-products-file",
        default="",
        help="在售产品基本信息 JSON 文件路径（默认: aia_data/在售产品基本信息.json）",
    )
    parser.add_argument(
        "--branch-news-file",
        default="",
        help="分公司新闻 JSON 文件路径（默认: aia_data/分公司新闻.json）",
    )
    parser.add_argument(
        "--anti-fraud-file",
        default="",
        help="反保险欺诈提示文本路径（默认: aia_data/反保险欺诈提示及举报渠道.txt）",
    )
    parser.add_argument("--verify", action="store_true", help="入库完成后打印各 collection point count")
    parser.add_argument("--verify-only", action="store_true", help="仅打印 collection 状态，不执行入库")
    args = parser.parse_args()

    service_categories_dir = (
        Path(args.service_categories_dir)
        if args.service_categories_dir
        else (ROOT / "aia_data" / "service_categories")
    )
    branches_file = resolve_optional_file(
        args.branches_file,
        "aia_data/分公司页面.json",
    )
    products_page_file = resolve_optional_file(args.products_page_file, "aia_data/个险+团险产品.json")
    personal_insurance_recommended_products_file = resolve_optional_file(
        args.personal_insurance_recommended_products_file,
        "aia_data/个险-推荐产品.json",
    )
    group_insurance_recommended_products_file = resolve_optional_file(
        args.group_insurance_recommended_products_file,
        "aia_data/团险-推荐产品.json",
    )
    on_sale_products_file = resolve_optional_file(
        args.on_sale_products_file,
        "aia_data/在售产品基本信息.json",
    )
    branch_news_file = resolve_optional_file(args.branch_news_file, "aia_data/分公司新闻.json")
    anti_fraud_file = resolve_optional_file(
        args.anti_fraud_file,
        "aia_data/反保险欺诈提示及举报渠道.txt",
    )

    if args.verify_only:
        verify_collections(collection_name="aia_knowledge_base")
        return

    if not service_categories_dir.exists() or not service_categories_dir.is_dir():
        raise SystemExit(f"service_categories 目录不存在或不是文件夹: {service_categories_dir}")

    logger.info("=" * 55)
    logger.info(" AIA 知识库统一入库开始")
    logger.info("=" * 55)
    logger.info(f"service_categories 目录: {service_categories_dir}")
    logger.info(f"分公司页面文件: {branches_file}")
    logger.info(f"个险+团险产品文件: {products_page_file}")
    logger.info(f"个险推荐产品文件: {personal_insurance_recommended_products_file}")
    logger.info(f"团险推荐产品文件: {group_insurance_recommended_products_file}")
    logger.info(f"在售产品基本信息文件: {on_sale_products_file}")
    logger.info(f"分公司新闻文件: {branch_news_file}")
    logger.info(f"反保险欺诈文本: {anti_fraud_file}")

    t0 = time.time()
    results = ingest_service_categories(service_categories_dir)

    for optional_json in [
        branches_file,
        products_page_file,
        personal_insurance_recommended_products_file,
        group_insurance_recommended_products_file,
        on_sale_products_file,
        branch_news_file,
    ]:
        if optional_json:
            results.append(ingest_json_file(optional_json))

    if anti_fraud_file:
        results.append(ingest_text(anti_fraud_file, title="反保险欺诈提示及举报渠道"))

    elapsed = time.time() - t0

    print(f"\n{'=' * 72}")
    print(f"{'文件':<26} {'Schema':<20} {'Doc数':>8}")
    print(f"{'-' * 72}")
    for r in results:
        fname = (r.get("file", "") or "")[:24]
        schema = (r.get("schema", "") or "")[:18]
        count = r.get("doc_count", 0)
        err = r.get("error", "")
        flag = "  ✗" if err else ""
        print(f"{fname:<26} {schema:<20} {count:>8}{flag}")
        if r.get("collections"):
            print(f"  -> collections: {r['collections']}")
        if err:
            print(f"  错误: {err}")
    print(f"{'-' * 72}")

    total_docs = sum(r.get("doc_count", 0) for r in results)
    error_count = sum(1 for r in results if r.get("error"))
    print(f"总计: {len(results)} 文件  {total_docs} 条向量  {error_count} 个错误  耗时 {elapsed:.1f}s")
    print(f"{'=' * 72}\n")

    if args.verify or error_count == 0:
        verify_collections(collection_name="aia_knowledge_base")

    if error_count > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
