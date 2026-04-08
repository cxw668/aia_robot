"""入库管道 shim 模块，重新导出原始的 ingest 实现。
该模块在实现位于 `_pipeline_impl.py` 的同时保持公共 API 的稳定性。
"""
from app.knowledge_base.ingestion._pipeline_impl import (
    ingest_file,
    ingest_all_aia_data,
    ingest_text_file,
    ingest_directory,
    ingest_forms_pdf,
    clear_form_knowledge,
    flatten_json,
)

__all__ = [
    "ingest_file",
    "ingest_all_aia_data",
    "ingest_text_file",
    "ingest_directory",
    "ingest_forms_pdf",
    "clear_form_knowledge",
    "flatten_json",
]
