"""Centralised application configuration.

All settings are read from environment variables (with fallbacks).
Load order: system env > .env file > defaults below.
"""
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "AIA Robot API"
    app_version: str = "1.0.0"
    debug: bool = False

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]

    # ── MySQL ─────────────────────────────────────────────────────────────────
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "aia_bot"
    db_user: str = "root"
    db_password: str = "1234"
    db_echo: bool = False          # set True to log SQL statements
    db_pool_size: int = 10
    db_max_overflow: int = 20

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy DSN (aiomysql driver)."""
        return (
            f"mysql+aiomysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync SQLAlchemy DSN (pymysql driver) — for Alembic migrations."""
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 6
    redis_password: str | None = None
    redis_max_connections: int = 20

    @property
    def redis_url(self) -> str:
        """Redis connection URL."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_chat_api_key: str = ""
    llm_api_url: str = "https://api.siliconflow.cn/v1/chat/completions"
    llm_model: str = "tencent/Hunyuan-MT-7B"

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrantclient_url: str = ""
    qdrantclient_key: str = ""

    # ── Embedding ─────────────────────────────────────────────────────────────
    model_cache_path: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton Settings instance."""
    return Settings()


# Module-level shortcut — use `from app.config import settings`
settings = get_settings()
