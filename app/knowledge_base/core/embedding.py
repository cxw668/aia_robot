"""向量模型加载与编码封装。"""
from __future__ import annotations

import logging
import os

from sentence_transformers import SentenceTransformer

from app.config import settings
from app.env_loader import EnvLoader
from app.knowledge_base.config import MODEL_NAME

logger = logging.getLogger(__name__)

_model_instance: SentenceTransformer | None = None

_model_cache = settings.model_cache_path
if _model_cache:
    os.environ["HF_HOME"] = _model_cache
    os.environ["TRANSFORMERS_CACHE"] = _model_cache
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = _model_cache


def get_model() -> SentenceTransformer:
    global _model_instance
    if _model_instance is None:
        explicit_local = (EnvLoader.get("EMBEDDING_MODEL_PATH", "") or "").strip()
        local_candidates: list[str] = []

        if explicit_local:
            local_candidates.append(explicit_local)

        if _model_cache:
            direct = os.path.join(_model_cache, "models--BAAI--bge-small-zh-v1.5")
            if os.path.isdir(direct):
                local_candidates.append(direct)
                snapshots = os.path.join(direct, "snapshots")
                if os.path.isdir(snapshots):
                    for d in os.listdir(snapshots):
                        p = os.path.join(snapshots, d)
                        if os.path.isdir(p):
                            local_candidates.append(p)

        for cand in local_candidates:
            if os.path.exists(os.path.join(cand, "config.json")) or os.path.exists(
                os.path.join(cand, "modules.json")
            ):
                logger.info("[embedding] using local model path: %s", cand)
                _model_instance = SentenceTransformer(cand, local_files_only=True)
                break

        if _model_instance is None:
            _model_instance = SentenceTransformer(MODEL_NAME)
    return _model_instance


__all__ = ["get_model"]
