"""文本切片策略（从 pdf_parser 迁移）。"""
from app.knowledge_base.processing._pdf_impl import (
    chunk_markdown,
    chunk_text,
)

__all__ = ["chunk_markdown", "chunk_text"]
