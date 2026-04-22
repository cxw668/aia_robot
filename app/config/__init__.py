from __future__ import annotations
from functools import lru_cache
from app.env_loader import EnvLoader


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str | None, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _to_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _to_str_list(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    def __init__(self) -> None:
        EnvLoader.load()

        # ── App ───────────────────────────────────────────────────────────────
        self.app_name: str = EnvLoader.get("APP_NAME", "AIA Robot API") or "AIA Robot API"
        self.app_version: str = EnvLoader.get("APP_VERSION", "1.0.0") or "1.0.0"
        self.debug: bool = _to_bool(EnvLoader.get("DEBUG", "false"), False)

        # ── CORS ──────────────────────────────────────────────────────────────
        self.cors_origins: list[str] = [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
        ]

        # ── MySQL ─────────────────────────────────────────────────────────────
        self.db_host: str = EnvLoader.get("DB_HOST", "localhost") or "localhost"
        self.db_port: int = _to_int(EnvLoader.get("DB_PORT", "3306"), 3306)
        self.db_name: str = EnvLoader.get("DB_NAME", "aia_bot") or "aia_bot"
        self.db_user: str = EnvLoader.get("DB_USER", "root") or "root"
        self.db_password: str = EnvLoader.get("DB_PASSWORD", "1234") or "1234"
        self.db_echo: bool = _to_bool(EnvLoader.get("DB_ECHO", "false"), False)
        self.db_pool_size: int = _to_int(EnvLoader.get("DB_POOL_SIZE", "10"), 10)
        self.db_max_overflow: int = _to_int(EnvLoader.get("DB_MAX_OVERFLOW", "20"), 20)

        # ── Redis ─────────────────────────────────────────────────────────────
        self.redis_host: str = EnvLoader.get("REDIS_HOST", "localhost") or "localhost"
        self.redis_port: int = _to_int(EnvLoader.get("REDIS_PORT", "6379"), 6379)
        self.redis_db: int = _to_int(EnvLoader.get("REDIS_DB", "6"), 6)
        self.redis_password: str | None = _to_optional_str(EnvLoader.get("REDIS_PASSWORD", None))
        self.redis_max_connections: int = _to_int(EnvLoader.get("REDIS_MAX_CONNECTIONS", "20"), 20)
        self.chat_cache_enabled: bool = _to_bool(EnvLoader.get("CHAT_CACHE_ENABLED", "true"), True)
        self.chat_cache_ttl_seconds: int = _to_int(EnvLoader.get("CHAT_CACHE_TTL_SECONDS", "300"), 300)
        self.auth_rate_limit_count: int = _to_int(EnvLoader.get("AUTH_RATE_LIMIT_COUNT", "10"), 10)
        self.auth_rate_limit_window_seconds: int = _to_int(EnvLoader.get("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60"), 60)
        self.chat_rate_limit_count: int = _to_int(EnvLoader.get("CHAT_RATE_LIMIT_COUNT", "30"), 30)
        self.chat_rate_limit_window_seconds: int = _to_int(EnvLoader.get("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60"), 60)
        active_jwt_secret = _to_optional_str(EnvLoader.get("JWT_SECRET_KEY", "aia-robot-dev-secret"))
        previous_jwt_secrets = _to_str_list(EnvLoader.get("JWT_PREVIOUS_SECRET_KEYS", ""))
        self.jwt_secret_keys: list[str] = [active_jwt_secret or "aia-robot-dev-secret"]
        self.jwt_secret_keys.extend(
            secret for secret in previous_jwt_secrets
            if secret not in self.jwt_secret_keys
        )

        # ── LLM ───────────────────────────────────────────────────────────────
        self.llm_chat_api_key: str = EnvLoader.get("LLM_CHAT_API_KEY", "") or ""
        self.llm_api_url: str = (
            EnvLoader.get("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions")
            or "https://api.siliconflow.cn/v1/chat/completions"
        )
        self.llm_model: str = EnvLoader.get("LLM_MODEL", "tencent/Hunyuan-MT-7B") or "tencent/Hunyuan-MT-7B"

        # ── Qdrant ────────────────────────────────────────────────────────────
        self.qdrantclient_url: str = EnvLoader.get("QdrantClient_url", "http://localhost:6333") or "http://localhost:6333"
        self.qdrantclient_key: str = EnvLoader.get("QdrantClient_key", "") or ""

        # ── Embedding ─────────────────────────────────────────────────────────
        self.model_cache_path: str = EnvLoader.get("MODEL_CACHE_PATH", "E:\\aia_embedding_models") or "E:\\aia_embedding_models"

        # ── OCR ───────────────────────────────────────────────────────────────
        self.ocr_api_url: str = (
            EnvLoader.get("OCR_API_URL", "https://api.siliconflow.cn/v1/chat/completions")
            or "https://api.siliconflow.cn/v1/chat/completions"
        )
        self.ocr_api_key: str = EnvLoader.get("OCR_API_KEY", "") or ""
        self.ocr_model: str = EnvLoader.get("OCR_MODEL", "deepseek-ai/DeepSeek-OCR") or "deepseek-ai/DeepSeek-OCR"
        self.ocr_fallback_min_chars: int = _to_int(EnvLoader.get("OCR_FALLBACK_MIN_CHARS", "50"), 50)
        self.ocr_render_dpi: int = _to_int(EnvLoader.get("OCR_RENDER_DPI", "300"), 300)
        self.ocr_timeout: int = _to_int(EnvLoader.get("OCR_TIMEOUT", "120"), 120)
        self.ocr_max_tokens: int = _to_int(EnvLoader.get("OCR_MAX_TOKENS", "8192"), 8192)
        self.ocr_noise_min_repeat: int = _to_int(EnvLoader.get("OCR_NOISE_MIN_REPEAT", "2"), 2)
        self.ocr_noise_max_line_length: int = _to_int(EnvLoader.get("OCR_NOISE_MAX_LINE_LENGTH", "80"), 80)

        # ── MinIO ─────────────────────────────────────────────────────────────
        self.minio_endpoint: str = EnvLoader.get("MINIO_ENDPOINT", "localhost:9000") or "localhost:9000"
        self.minio_access_key: str = EnvLoader.get("MINIO_ACCESS_KEY", "minioadmin") or "minioadmin"
        self.minio_secret_key: str = EnvLoader.get("MINIO_SECRET_KEY", "minioadmin") or "minioadmin"
        self.minio_secure: bool = _to_bool(EnvLoader.get("MINIO_SECURE", "false"), False)
        self.minio_bucket_raw: str = EnvLoader.get("MINIO_BUCKET_RAW", "kb-raw") or "kb-raw"
        self.minio_bucket_parsed: str = EnvLoader.get("MINIO_BUCKET_PARSED", "kb-parsed") or "kb-parsed"

        # ── PDF ingestion ─────────────────────────────────────────────────────
        self.pdf_max_bytes: int = _to_int(EnvLoader.get("PDF_MAX_BYTES", "52428800"), 52_428_800)
        self.pdf_download_timeout: int = _to_int(EnvLoader.get("PDF_DOWNLOAD_TIMEOUT", "60"), 60)
        self.pdf_allowed_hosts: str = EnvLoader.get("PDF_ALLOWED_HOSTS", "www.aia.com.cn,aia.com.cn") or "www.aia.com.cn,aia.com.cn"
        self.pdf_chunk_size: int = _to_int(EnvLoader.get("PDF_CHUNK_SIZE", "600"), 600)
        self.pdf_chunk_overlap: int = _to_int(EnvLoader.get("PDF_CHUNK_OVERLAP", "80"), 80)

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def pdf_allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.pdf_allowed_hosts.split(",") if h.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
