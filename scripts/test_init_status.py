from __future__ import annotations

import asyncio
import os
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Awaitable, Callable
from urllib.parse import urlparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
BLUE = "\033[34m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"


def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | int | None, default: int) -> int:
    if isinstance(value, int):
        return value
    if value in (None, ""):
        return default
    return int(str(value).strip())


def _load_env_file(env_path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not env_path.exists():
        return data

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def load_settings() -> tuple[object, str]:
    try:
        from app.config import settings as app_settings

        return app_settings, "app.config"
    except Exception:
        env_data = _load_env_file(ROOT_DIR / ".env")

        def env(key: str, default: str = "") -> str:
            return os.getenv(key, env_data.get(key, default))

        redis_password = env("REDIS_PASSWORD", "") or None
        redis_host = env("REDIS_HOST", "localhost")
        redis_port = _parse_int(env("REDIS_PORT", "6379"), 6379)
        redis_db = _parse_int(env("REDIS_DB", "6"), 6)
        redis_auth = f":{redis_password}@" if redis_password else ""

        settings_obj = SimpleNamespace(
            app_name=env("APP_NAME", "AIA Robot API"),
            app_version=env("APP_VERSION", "1.0.0"),
            debug=_parse_bool(env("DEBUG", "false"), False),
            cors_origins=[
                "http://localhost:5173",
                "http://localhost:5174",
                "http://localhost:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
            ],
            db_host=env("DB_HOST", "localhost"),
            db_port=_parse_int(env("DB_PORT", "3306"), 3306),
            db_name=env("DB_NAME", "aia_bot"),
            db_user=env("DB_USER", "root"),
            db_password=env("DB_PASSWORD", "1234"),
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            redis_password=redis_password,
            redis_url=f"redis://{redis_auth}{redis_host}:{redis_port}/{redis_db}",
            llm_chat_api_key=env("LLM_CHAT_API_KEY", ""),
            llm_api_url=env("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions"),
            llm_model=env("LLM_MODEL", "tencent/Hunyuan-MT-7B"),
            qdrantclient_url=env("QdrantClient_url", ""),
            qdrantclient_key=env("QdrantClient_key", ""),
            model_cache_path=env("MODEL_CACHE_PATH", ""),
            ocr_api_url=env("OCR_API_URL", "https://api.siliconflow.cn/v1/chat/completions"),
            ocr_api_key=env("OCR_API_KEY", ""),
            ocr_model=env("OCR_MODEL", "deepseek-ai/DeepSeek-OCR"),
            ocr_timeout=_parse_int(env("OCR_TIMEOUT", "60"), 60),
            minio_endpoint=env("MINIO_ENDPOINT", "localhost:9000"),
            minio_access_key=env("MINIO_ACCESS_KEY", "minioadmin"),
            minio_secret_key=env("MINIO_SECRET_KEY", "minioadmin"),
            minio_secure=_parse_bool(env("MINIO_SECURE", "false"), False),
            minio_bucket_raw=env("MINIO_BUCKET_RAW", "kb-raw"),
            minio_bucket_parsed=env("MINIO_BUCKET_PARSED", "kb-parsed"),
        )
        return settings_obj, ".env fallback"


settings, SETTINGS_SOURCE = load_settings()


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    elapsed_ms: float


def supports_color() -> bool:
    return sys.stdout.isatty()


USE_COLOR = supports_color()


def colorize(text: str, color: str) -> str:
    if not USE_COLOR or not color:
        return text
    return f"{color}{text}{RESET}"


def badge(status: str) -> str:
    labels = {
        "ok": colorize("[ OK ]", GREEN),
        "warn": colorize("[WARN]", YELLOW),
        "fail": colorize("[FAIL]", RED),
    }
    return labels[status]


def mask_secret(value: str, keep_start: int = 4, keep_end: int = 4) -> str:
    if not value:
        return "<empty>"
    if len(value) <= keep_start + keep_end:
        return "*" * len(value)
    return f"{value[:keep_start]}{'*' * (len(value) - keep_start - keep_end)}{value[-keep_end:]}"


async def run_check(name: str, checker: Callable[[], Awaitable[tuple[str, str]]]) -> CheckResult:
    print(f"  {colorize('→', CYAN)} {name} ...", flush=True)
    started = time.perf_counter()
    try:
        status, detail = await checker()
    except Exception as exc:
        status = "fail"
        detail = f"{type(exc).__name__}: {exc}"
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"  {badge(status)} {name:<18} {detail} {colorize(f'({elapsed_ms:.0f} ms)', DIM)}", flush=True)
    return CheckResult(name=name, status=status, detail=detail, elapsed_ms=elapsed_ms)


async def check_app_config() -> tuple[str, str]:
    detail = (
        f"{settings.app_name} v{settings.app_version} | "
        f"DEBUG={settings.debug} | CORS={len(settings.cors_origins)} origins | source={SETTINGS_SOURCE}"
    )
    return "ok", detail


async def check_model_cache() -> tuple[str, str]:
    path = Path(settings.model_cache_path) if settings.model_cache_path else None
    if not path:
        return "warn", "MODEL_CACHE_PATH 未配置"
    if path.exists() and path.is_dir():
        return "ok", f"目录存在: {path}"
    return "warn", f"目录不存在: {path}"


async def check_mysql() -> tuple[str, str]:
    try:
        import aiomysql
    except ImportError as exc:
        return "fail", f"缺少依赖 aiomysql: {exc}"

    conn = await aiomysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        db=settings.db_name,
        connect_timeout=5,
        autocommit=True,
    )
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT 1")
            row = await cursor.fetchone()
        return "ok", f"{settings.db_host}:{settings.db_port}/{settings.db_name} -> SELECT {row[0]}"
    finally:
        conn.close()


async def check_redis() -> tuple[str, str]:
    try:
        import redis.asyncio as redis
    except ImportError as exc:
        return "fail", f"缺少依赖 redis: {exc}"

    client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=5)
    try:
        pong = await client.ping()
        return "ok", f"{settings.redis_host}:{settings.redis_port}/{settings.redis_db} -> PING={pong}"
    finally:
        await client.aclose()


async def check_qdrant() -> tuple[str, str]:
    url = settings.qdrantclient_url.strip()
    if not url:
        return "warn", "QdrantClient_url 未配置"

    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    def _connect() -> None:
        with socket.create_connection((host, port), timeout=5):
            return None

    await asyncio.to_thread(_connect)
    key_state = "已配置密钥" if settings.qdrantclient_key else "未配置密钥"
    return "ok", f"{url} 可连接 | {key_state}"


async def check_minio() -> tuple[str, str]:
    endpoint = settings.minio_endpoint.strip()
    if not endpoint:
        return "warn", "MINIO_ENDPOINT 未配置"

    secure = settings.minio_secure
    host, port = endpoint, 443 if secure else 80
    if ":" in endpoint:
        host, raw_port = endpoint.rsplit(":", 1)
        port = int(raw_port)

    def _connect() -> None:
        with socket.create_connection((host, port), timeout=5):
            return None

    await asyncio.to_thread(_connect)
    return "ok", f"{endpoint} 可连接 | buckets=[{settings.minio_bucket_raw}, {settings.minio_bucket_parsed}]"


async def check_llm() -> tuple[str, str]:
    api_key = settings.llm_chat_api_key.strip()
    if not api_key:
        return "warn", "LLM_CHAT_API_KEY 未配置"
    return "ok", f"{settings.llm_model} | {settings.llm_api_url} | key={mask_secret(api_key)}"


async def check_ocr() -> tuple[str, str]:
    api_key = settings.ocr_api_key.strip()
    if not api_key:
        return "warn", "OCR_API_KEY 未配置"
    return "ok", f"{settings.ocr_model} | timeout={settings.ocr_timeout}s | key={mask_secret(api_key)}"


def print_header() -> None:
    title = f"{settings.app_name} 初始化状态自检"
    print()
    print(colorize("=" * 72, BLUE))
    print(colorize(title, f"{BOLD}{BLUE}" if USE_COLOR else ""))
    print(colorize("=" * 72, BLUE))
    print(f"项目目录: {ROOT_DIR}")
    print(f"配置来源: {SETTINGS_SOURCE}")
    print(f"数据库 DSN: mysql+aiomysql://{settings.db_user}:***@{settings.db_host}:{settings.db_port}/{settings.db_name}")
    print(f"Redis URL: redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}")
    print()


def print_summary(results: list[CheckResult]) -> None:
    ok_count = sum(1 for item in results if item.status == "ok")
    warn_count = sum(1 for item in results if item.status == "warn")
    fail_count = sum(1 for item in results if item.status == "fail")
    total_ms = sum(item.elapsed_ms for item in results)

    print()
    print(colorize("-" * 72, BLUE))
    print(colorize("检查汇总", f"{BOLD}{BLUE}" if USE_COLOR else ""))
    print(colorize("-" * 72, BLUE))
    print(f"{badge('ok')} 成功: {ok_count}")
    print(f"{badge('warn')} 警告: {warn_count}")
    print(f"{badge('fail')} 失败: {fail_count}")
    print(f"总耗时: {total_ms:.0f} ms")

    if fail_count:
        print(colorize("\n初始化状态: 存在失败项，请先修复再启动服务。", RED))
    elif warn_count:
        print(colorize("\n初始化状态: 基本可用，但存在需要关注的警告项。", YELLOW))
    else:
        print(colorize("\n初始化状态: 全部通过，可以继续启动服务。", GREEN))


async def main() -> int:
    print_header()

    checks: list[tuple[str, Callable[[], Awaitable[tuple[str, str]]]]] = [
        ("应用配置", check_app_config),
        ("模型缓存目录", check_model_cache),
        ("MySQL 连接", check_mysql),
        ("Redis 连接", check_redis),
        ("Qdrant 连通性", check_qdrant),
        ("MinIO 连通性", check_minio),
        ("LLM 配置", check_llm),
        ("OCR 配置", check_ocr),
    ]

    results: list[CheckResult] = []
    for name, checker in checks:
        results.append(await run_check(name, checker))

    print_summary(results)
    return 1 if any(item.status == "fail" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
