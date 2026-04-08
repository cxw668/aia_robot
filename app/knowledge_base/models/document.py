"""文档切片与 Payload 的标准字段定义。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentChunk:
    """代表一个向量化文档切片。"""
    text: str
    payload: dict[str, Any]


__all__ = ["DocumentChunk"]
