#!/usr/bin/env python3
"""
Preprocess 保单服务.json:
  1. Convert pinyin service_name to Chinese
  2. Split into per-category JSON files under aia_data/service_categories/
  3. Each output file is ready for ingest_file() with collection_name = Chinese service name

Usage:
    python scripts/preprocess_service_categories.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# ── Pinyin → Chinese mapping (exhaustive for this dataset) ────────────────────
PINYIN_TO_CN: dict[str, str] = {
    "baodanfuwu": "保单服务",
    "xuqijizhanghuguanli": "续期及账户管理",
    "nianjin": "年金",
    "baoxianjihuabiangeng": "保险计划变更",
    "tuibao": "退保",
    "wannengxian": "万能险",
    "hetong": "合同",
    "jiekuan": "借款",
}

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "aia_data" / "保单服务.json"
OUT_DIR = ROOT / "aia_data" / "service_categories"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)

    categories = data.get("service_categories", [])
    unknown: list[str] = []

    for cat in categories:
        pinyin_name: str = cat.get("service_name", "")
        cn_name = PINYIN_TO_CN.get(pinyin_name)
        if cn_name is None:
            cn_name = pinyin_name  # keep as-is and warn
            unknown.append(pinyin_name)

        # Build a self-contained single-category JSON that ingest.py already understands
        output = {
            "service_categories": [
                {
                    "service_name": cn_name,
                    "url": cat.get("url", ""),
                    "total_items": cat.get("total_items", len(cat.get("items", []))),
                    "items": cat.get("items", []),
                }
            ]
        }

        out_path = OUT_DIR / f"{cn_name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"[preprocess] {pinyin_name!r:30s} -> {cn_name}  ({len(cat.get('items', []))} items)  => {out_path.relative_to(ROOT)}")

    if unknown:
        print(f"\n[warn] Unknown pinyin names (kept as-is): {unknown}")
    else:
        print(f"\n[done] {len(categories)} categories written to {OUT_DIR.relative_to(ROOT)}/")

    # Also write an updated 保单服务_cn.json with all categories using Chinese names
    all_cn = {
        "service_categories": [
            {
                **cat,
                "service_name": PINYIN_TO_CN.get(cat.get("service_name", ""), cat.get("service_name", "")),
            }
            for cat in categories
        ]
    }
    cn_path = ROOT / "aia_data" / "保单服务_cn.json"
    with open(cn_path, "w", encoding="utf-8") as f:
        json.dump(all_cn, f, ensure_ascii=False, indent=2)
    print(f"[done] Full Chinese-name file -> {cn_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
