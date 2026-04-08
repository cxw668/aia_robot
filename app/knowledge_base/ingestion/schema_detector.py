"""Schema 自动检测（从 ingest.py 迁移）。"""
from __future__ import annotations

from typing import Any


def detect_schema(data: Any) -> str:
    if isinstance(data, dict):
        keys = set(data.keys())
        if "service_categories" in keys:
            return "service_categories"
        if "items" in keys and isinstance(data.get("items"), list):
            sample = data["items"][:1]
            if sample and isinstance(sample[0], dict):
                if "full_url" in sample[0] or "filename" in sample[0]:
                    return "forms"
                if "title" in sample[0] and "url" in sample[0] and "full_url" not in sample[0]:
                    return "menu"
        if "forms" in keys or "form_categories" in keys:
            return "forms"
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
        if "regions" in keys:
            return "branches"
        if "branch" in keys:
            return "branches"
        if "menu" in keys or "menus" in keys:
            return "menu"
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and "productName" in data[0]:
            return "products_list"
        return "generic_list"
    return "generic"


# 保持向后兼容的别名
_detect_schema = detect_schema

__all__ = ["detect_schema"]
