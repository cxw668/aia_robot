"""知识库全局常量配置。"""
from __future__ import annotations

from app.config import settings

# Qdrant 集合
DEFAULT_COLLECTION = "aia_knowledge_base"
COLLECTION_NAME = DEFAULT_COLLECTION

# 向量模型
MODEL_NAME = settings.embedding_model or "BAAI/bge-large-zh-v1.5"
VECTOR_SIZE = settings.embedding_vector_size or 1024

# 检索参数
TOP_K = 5
SCORE_THRESHOLD = 0.45

# 向量检索分层阈值
VECTOR_HIGH_CONFIDENCE_THRESHOLD = 0.85
VECTOR_LLM_CANDIDATE_THRESHOLD = 0.5
VECTOR_LLM_CANDIDATE_LIMIT = 50

# LLM 复审阈值
LLM_RELEVANCE_THRESHOLD = 0.6

# 向量化批大小
_BATCH = 32
