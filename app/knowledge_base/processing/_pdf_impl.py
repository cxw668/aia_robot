"""Markdown-oriented PDF parsing with DeepSeek-OCR.

单页处理流程
-----------------
1. 将 PDF 页面渲染为 PNG 图片。
2. 调用 DeepSeek-OCR 进行 Markdown 内容重建。
3. 清理重复的页眉、页脚和页码。
4. 如果 OCR 识别失败或被拒绝，则回退使用 PDF 原生的文本提取方式。
5. 根据标题和表格进行语义化切片。
"""
from __future__ import annotations

import base64
import logging
import re
from collections import Counter
from typing import Optional

import fitz
import requests

from app.config import settings

logger = logging.getLogger(__name__)


def _page_to_png_b64(page: fitz.Page, dpi: Optional[int] = None) -> str:
    render_dpi = dpi or settings.ocr_render_dpi
    mat = fitz.Matrix(render_dpi / 72, render_dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
    return base64.b64encode(pix.tobytes("png")).decode("ascii")


def _extract_markdown_from_response(data: dict) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(p.strip() for p in parts if p and str(p).strip()).strip()
    return str(content).strip()


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return stripped


_OCR_PROMPT = (
    "请识别这一页文档，并直接输出 Markdown。"
    "要求：\n"
    "1. 按视觉阅读顺序重建内容；\n"
    "2. 标题用 #/##/###；\n"
    "3. 表格必须完整输出为 Markdown 表格；\n"
    "4. 不要补写不存在的内容；\n"
    "5. 不要输出任何解释或代码围栏。"
)


def _build_ocr_payload(img_b64: str, variant: str, max_tokens: int) -> dict:
    image_part = {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
    }
    text_part = {"type": "text", "text": _OCR_PROMPT}
    if variant == "simple":
        return {
            "model": settings.ocr_model,
            "messages": [{"role": "user", "content": [text_part, image_part]}],
            "max_tokens": max_tokens,
        }
    return {
        "model": settings.ocr_model,
        "messages": [
            {
                "role": "system",
                "content": "你是文档理解模型，请输出干净 Markdown，保留表格结构。",
            },
            {"role": "user", "content": [text_part, image_part]},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }


def _post_ocr_payload(payload: dict) -> tuple[bool, str]:
    api_key = settings.ocr_api_key or settings.llm_chat_api_key
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
    if resp.ok:
        return True, _strip_code_fence(_extract_markdown_from_response(resp.json()))
    logger.warning("[pdf_parser] OCR HTTP %s response: %s", resp.status_code, resp.text.strip()[:1000])
    return False, ""


def _extract_page_native_markdown(page: fitz.Page) -> str:
    text = page.get_text("text").strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines()]
    normalized: list[str] = []
    for line in lines:
        if not line:
            normalized.append("")
        elif re.match(r"^(第[一二三四五六七八九十百零\d]+[章节条部分项]|[一二三四五六七八九十]+、)", line):
            normalized.append(f"## {line}")
        else:
            normalized.append(line)
    return "\n".join(normalized).strip()


def _ocr_page_via_deepseek(page: fitz.Page) -> str:
    api_key = settings.ocr_api_key or settings.llm_chat_api_key
    if not api_key:
        logger.warning("[pdf_parser] OCR skipped — no OCR_API_KEY configured")
        return _extract_page_native_markdown(page)

    attempts = [
        (settings.ocr_render_dpi, "simple", min(settings.ocr_max_tokens, 4096)),
        (200, "simple", 2048),
        (150, "with_system", 2048),
    ]
    for dpi, variant, max_tokens in attempts:
        try:
            img_b64 = _page_to_png_b64(page, dpi=dpi)
            ok, markdown = _post_ocr_payload(_build_ocr_payload(img_b64, variant, max_tokens))
            if ok and markdown.strip():
                return markdown.strip()
        except Exception as exc:
            logger.warning(
                "[pdf_parser] OCR failed for page %s (dpi=%s, variant=%s): %s",
                page.number + 1,
                dpi,
                variant,
                exc,
            )
    fallback = _extract_page_native_markdown(page)
    if fallback:
        logger.info("[pdf_parser] page %s using native text fallback", page.number + 1)
    else:
        logger.warning("[pdf_parser] page %s OCR + native fallback both empty", page.number + 1)
    return fallback


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _is_noise_line(line: str) -> bool:
    text = _normalize_line(line)
    return (
        not text
        or re.fullmatch(r"第?\s*\d+\s*页", text) is not None
        or re.fullmatch(r"\d+\s*/\s*\d+", text) is not None
        or re.fullmatch(r"[-_—=·•\s]{3,}", text) is not None
    )


def _is_html_noise_line(line: str) -> bool:
    text = _normalize_line(line)
    return (
        bool(re.search(r"<[^>]+>", text))
        or text.count("</") >= 1
        or text.count("{{") >= 1
        or text.count("}}") >= 1
        or text.count("\\/") >= 2
        or bool(re.search(r"[{}\\]{4,}", text))
    )


def _looks_like_table_garbage(line: str) -> bool:
    text = _normalize_line(line)
    if not text:
        return False
    if text.startswith("|") and text.endswith("|"):
        cells = [cell.strip() for cell in text.strip("|").split("|")]
        dense_short_cells = sum(1 for cell in cells if 0 < len(cell) <= 4)
        repeated_cells = len(cells) >= 6 and len(set(cells)) <= max(2, len(cells) // 4)
        return dense_short_cells >= max(4, len(cells) // 2) or repeated_cells
    repeated_phrases = ["产品 数据供", "qqq", "components:array", "}}}}", "{{{{"]
    return any(token in text for token in repeated_phrases)


def _clean_markdown_line(line: str) -> str:
    text = line.strip()
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"\\/", "/", text)
    text = re.sub(r"[\t\r]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" |")


def _clean_markdown_pages(pages: list[str]) -> list[str]:
    normalized_pages: list[list[str]] = []
    edge_counter: Counter[str] = Counter()
    for page in pages:
        lines = [line.rstrip() for line in page.splitlines()]
        normalized_pages.append(lines)
        candidates = []
        if lines:
            candidates.extend(lines[:2])
            candidates.extend(lines[-2:])
        for candidate in candidates:
            text = _normalize_line(candidate)
            if 0 < len(text) <= settings.ocr_noise_max_line_length:
                edge_counter[text] += 1
    repeated_noise = {text for text, count in edge_counter.items() if count >= settings.ocr_noise_min_repeat}
    cleaned_pages: list[str] = []
    for lines in normalized_pages:
        kept: list[str] = []
        for idx, line in enumerate(lines):
            text = _normalize_line(line)
            if _is_noise_line(text):
                continue
            if text in repeated_noise and (idx < 2 or idx >= max(len(lines) - 2, 0)):
                continue
            if _is_html_noise_line(text) or _looks_like_table_garbage(text):
                continue
            cleaned = _clean_markdown_line(line)
            if not cleaned:
                continue
            kept.append(cleaned)
        cleaned = "\n".join(kept).strip()
        if cleaned:
            cleaned_pages.append(cleaned)
    return cleaned_pages


def _promote_plain_headings(lines: list[str]) -> list[str]:
    promoted: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            promoted.append("")
        elif stripped.startswith(("#", "- ", "* ", "|")):
            promoted.append(line)
        elif re.match(r"^(第[一二三四五六七八九十百零\d]+[章节条部分项]|[一二三四五六七八九十]+、)", stripped):
            promoted.append(f"## {stripped.lstrip('#').strip()}")
        else:
            promoted.append(line)
    return promoted


def extract_pdf_pages(pdf_bytes: bytes) -> list[str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[str] = []
    try:
        for page in doc:
            markdown = _ocr_page_via_deepseek(page)
            if markdown.strip():
                pages.append(markdown.strip())
    finally:
        doc.close()
    cleaned_pages = _clean_markdown_pages(pages)
    final_pages: list[str] = []
    for page in cleaned_pages:
        lines = _promote_plain_headings(page.splitlines())
        normalized = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        if normalized:
            final_pages.append(normalized)
    return final_pages


def extract_pdf_markdown(pdf_bytes: bytes) -> str:
    pages = extract_pdf_pages(pdf_bytes)
    return "\n\n---\n\n".join(pages) if pages else ""


def extract_pdf_text(pdf_bytes: bytes) -> str:
    return extract_pdf_markdown(pdf_bytes)


def chunk_markdown(text: str, chunk_size: Optional[int] = None, overlap: Optional[int] = None) -> list[str]:
    size = chunk_size or settings.pdf_chunk_size
    ovlp = overlap or settings.pdf_chunk_overlap
    if not text.strip():
        return []
    sections: list[str] = []
    current: list[str] = []
    in_table = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        is_heading = stripped.startswith("#")
        is_table = stripped.startswith("|") and stripped.endswith("|")
        if is_heading and current:
            sections.append("\n".join(current).strip())
            current = [line]
            in_table = False
            continue
        if is_table:
            current.append(line)
            in_table = True
            continue
        if in_table and stripped and not is_table:
            in_table = False
        if not stripped and current:
            current.append("")
            continue
        current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    chunks: list[str] = []
    buffer = ""
    for section in sections:
        candidate = section if not buffer else f"{buffer}\n\n{section}"
        if len(candidate) <= size:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer.strip())
            tail = buffer[-ovlp:] if ovlp > 0 else ""
            buffer = f"{tail}\n\n{section}" if tail.strip() else section
        else:
            start = 0
            while start < len(section):
                end = min(start + size, len(section))
                piece = section[start:end].strip()
                if piece:
                    chunks.append(piece)
                if end >= len(section):
                    break
                start = max(end - ovlp, start + 1)
            buffer = ""
        while len(buffer) > size:
            chunks.append(buffer[:size].strip())
            buffer = buffer[max(size - ovlp, 1):].strip()
    if buffer.strip():
        chunks.append(buffer.strip())
    return [chunk for chunk in chunks if chunk.strip()]


def chunk_text(text: str, chunk_size: Optional[int] = None, overlap: Optional[int] = None) -> list[str]:
    return chunk_markdown(text, chunk_size=chunk_size, overlap=overlap)
