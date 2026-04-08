"""意图相关数据类定义。"""
from __future__ import annotations

from dataclasses import dataclass, field

OFFICIAL_BASE_URL = "https://www.aia.com.cn"


@dataclass(frozen=True)
class RetrievalIntent:
    key: str
    name: str
    schemas: tuple[str, ...]
    categories: tuple[str, ...] = ()
    only_on_sale: bool = False
    official_url: str = ""


@dataclass(frozen=True)
class IntentCandidate:
    key: str
    score: int
    confidence: float
    intent: RetrievalIntent


@dataclass(frozen=True)
class IntentRecognitionResult:
    intent: RetrievalIntent | None
    scores: dict[str, int]
    normalized_query: str
    confidence: float
    candidates: list[IntentCandidate]
    needs_confirmation: bool


__all__ = [
    "OFFICIAL_BASE_URL",
    "RetrievalIntent",
    "IntentCandidate",
    "IntentRecognitionResult",
]
