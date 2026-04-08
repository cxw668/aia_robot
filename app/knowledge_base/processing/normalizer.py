"""类别规范化与文本清洗（从 category_utils 迁移）。"""
from __future__ import annotations

import re
import unicodedata


def _clean_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\-–—_]+", "-", s)
    s = re.sub(r"(\.json|\.txt)$", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"(页面|列表|基本信息|信息|菜单|栏目)$", "", s).strip()
    s = s.strip(" -_")
    return s


def normalize_category(cat: str | None) -> str:
    """规范化类别名称，进行文本清理。"""
    if not cat:
        return ""
    return _clean_text(cat)


def get_point_category(payload: dict) -> str:
    """从 payload 中提取并返回规范化后的类别名称。"""
    if not isinstance(payload, dict):
        return ""
    for key in ("category_canonical", "category", "service_name", "source_file"):
        val = payload.get(key)
        if val:
            n = normalize_category(val)
            if n:
                return n
    return ""


def category_matches(pred: str | None, expected: str | None) -> bool:
    if not pred or not expected:
        return False
    p = normalize_category(pred)
    e = normalize_category(expected)
    if not p or not e:
        return False
    if p == e:
        return True
    if e in p or p in e:
        return True
    p_chars = set(re.sub(r"[\W_0-9\s]+", "", p))
    e_chars = set(re.sub(r"[\W_0-9\s]+", "", e))
    if p_chars and e_chars and len(p_chars & e_chars) >= 2:
        return True
    return False


__all__ = ["normalize_category", "get_point_category", "category_matches"]
