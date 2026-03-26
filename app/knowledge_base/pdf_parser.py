"""PDF text extraction with DeepSeek-OCR fallback.

Pipeline per page
-----------------
1. PyMuPDF  — fast, zero-cost native text extraction.
2. DeepSeek-OCR (SiliconFlow vision API) — invoked only when native text
   is shorter than ``settings.ocr_fallback_min_chars`` (default 50 chars),
   which signals a scanned / image-only page.

Public API
----------
extract_pdf_text(pdf_bytes)  -> str   (full document text)
extract_pdf_pages(pdf_bytes) -> list[str]  (one string per page)
"""
from __future__ import annotations

import base64
import io
import json
import logging
from typing import Optional

import fitz  # PyMuPDF
import requests

from app.config import settings

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _page_to_png_b64(page: fitz.Page, dpi: int = 150) -> str:
    """Render a PDF page to a base64-encoded PNG string for vision API."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    png_bytes = pix.tobytes("png")
    return base64.b64encode(png_bytes).decode("ascii")


def _ocr_page_via_deepseek(page: fitz.Page) -> str:
    """Call SiliconFlow DeepSeek-OCR to extract text from one rendered page.

    Returns extracted text, or empty string on any failure.
    """
    api_key = settings.ocr_api_key or settings.llm_chat_api_key
    if not api_key:
        logger.warning("[pdf_parser] OCR skipped — no OCR_API_KEY configured")
        return ""

    try:
        img_b64 = _page_to_png_b64(page)
        payload = {
            "model": settings.ocr_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_b64}"
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "请识别图片中的全部文字内容，按原始排版顺序输出，"
                                "不要添加任何额外说明。"
                            ),
                        },
                    ],
                }
            ],
            "max_tokens": 4096,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            settings.ocr_api_url,
            json=payload,
            headers=headers,
            timeout=settings.ocr_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning(f"[pdf_parser] OCR failed for page: {exc}")
        return ""


def _extract_page_text(page: fitz.Page) -> str:
    """Extract text from one page; fall back to OCR when native text is thin."""
    native = page.get_text("text").strip()
    if len(native) >= settings.ocr_fallback_min_chars:
        return native
    logger.info(
        f"[pdf_parser] page {page.number + 1}: native text too short "
        f"({len(native)} chars), invoking OCR"
    )
    ocr_text = _ocr_page_via_deepseek(page)
    return ocr_text if ocr_text else native


# ── Public API ────────────────────────────────────────────────────────────────

def extract_pdf_pages(pdf_bytes: bytes) -> list[str]:
    """Return a list of text strings, one per page."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[str] = []
    for page in doc:
        pages.append(_extract_page_text(page))
    doc.close()
    return pages


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Return the full document text (all pages joined by double newline)."""
    return "\n\n".join(p for p in extract_pdf_pages(pdf_bytes) if p)


# ── Chunker ───────────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: Optional[int] = None,
    overlap: Optional[int] = None,
) -> list[str]:
    """Split *text* into overlapping chunks suitable for embedding.

    Uses character-level sliding window. Paragraph boundaries are preferred
    when they fall within the window.
    """
    size = chunk_size or settings.pdf_chunk_size
    ovlp = overlap or settings.pdf_chunk_overlap
    if ovlp >= size:
        ovlp = size // 5

    if len(text) <= size:
        return [text] if text.strip() else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end]
        # Try to break at a paragraph / sentence boundary
        for sep in ("\n\n", "\n", "。", ".", " "):
            idx = chunk.rfind(sep)
            if idx > size // 2:
                chunk = chunk[: idx + len(sep)]
                break
        chunk = chunk.strip()
        if chunk:
            chunks.append(chunk)
        start += len(chunk) - ovlp if len(chunk) > ovlp else len(chunk)
        if start >= len(text):
            break
    return chunks
