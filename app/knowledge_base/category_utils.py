"""Category normalization and matching utilities.

Keep this module lightweight — no heavy ML or I/O dependencies — so it
can be imported by small utility scripts without pulling the full ingest
stack.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict

# Minimal alias mapping derived from observed failures; configurable/expandable.
CATEGORY_ALIASES: Dict[str, str] = {
    "年金": "保险计划变更",
    "表单下载-个险": "表单下载",
    "表单下载-团险": "表单下载",
    "个险表单": "表单下载",
    "团险表单": "表单下载",
    "在售产品基本信息": "在售产品",
    "客户服务菜单": "客户服务导航",
    "分公司页面": "分公司",
    "分公司新闻": "分公司动态",
}


def _clean_text(s: str) -> str:
    if not s:
        return ""
    # Normalize fullwidth/compat forms and collapse whitespace
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # Normalize various dashes/underscores to a single '-' for easier matching
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\-–—_]+", "-", s)
    # Remove common file suffixes and JSON/TXT extensions
    s = re.sub(r"(\.json|\.txt)$", "", s, flags=re.IGNORECASE).strip()
    # Remove trailing structural words (页面/列表/基本信息/信息/菜单/栏目)
    s = re.sub(r"(页面|列表|基本信息|信息|菜单|栏目)$", "", s).strip()
    # Trim leftover punctuation
    s = s.strip(" -_")
    return s


def normalize_category(cat: str | None) -> str:
    """Return a compact, canonical category string for comparison and counting.

    Behavior:
    - NFKC normalisation, whitespace collapse
    - strip common suffixes like "页面"/"列表"/"基本信息"
    - apply simple alias mapping (exact or substring match)
    """
    if not cat:
        return ""
    s = _clean_text(cat)

    # Exact alias first
    if s in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[s]

    # Substring alias (e.g. '表单下载-个险.json' -> matches '表单下载-个险')
    for k, v in CATEGORY_ALIASES.items():
        if k in s or s in k:
            return v

    return s


def get_point_category(payload: dict) -> str:
    """Extract a best-effort category from a Qdrant point payload.

    Preference order:
      1. category_canonical
      2. category
      3. service_name
      4. source_file
    """
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
    """Loose matching for category labels.

    Returns True if predicted category and expected category are considered
    the same or close enough. Rules (in order):
      - canonical strings equal
      - one is substring of the other
      - alias mapping links them
      - character-overlap (>=2 common CJK chars)
    """
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
    # alias indirect match (aliases are resolved in normalize_category already)
    # character overlap fallback for short/compound labels
    p_chars = set(re.sub(r"[\W_0-9\s]+", "", p))
    e_chars = set(re.sub(r"[\W_0-9\s]+", "", e))
    if p_chars and e_chars and len(p_chars & e_chars) >= 2:
        return True
    return False


__all__ = ["normalize_category", "get_point_category", "category_matches"]
