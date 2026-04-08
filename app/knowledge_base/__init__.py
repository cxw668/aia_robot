"""High-level knowledge_base API shim.
暴露统一的高层 API（如 search, ingest）。
"""
from app.knowledge_base.retrieval import retrieve, rag_query
from app.knowledge_base.ingestion.pipeline import (
    ingest_file,
    ingest_all_aia_data,
    ingest_text_file,
    ingest_directory,
    ingest_forms_pdf,
    clear_form_knowledge,
)
from app.knowledge_base.intent import classify_query_intent, classify_query_intent_with_scores
from app.knowledge_base.processing.normalizer import normalize_category, get_point_category

__all__ = [
    "retrieve",
    "rag_query",
    "ingest_file",
    "ingest_all_aia_data",
    "ingest_text_file",
    "ingest_directory",
    "ingest_forms_pdf",
    "clear_form_knowledge",
    "classify_query_intent",
    "classify_query_intent_with_scores",
    "normalize_category",
    "get_point_category",
]
