from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings

_pool: aioredis.ConnectionPool = aioredis.ConnectionPool.from_url(
    settings.redis_url,
    max_connections=settings.redis_max_connections,
    decode_responses=True,
)
logger = logging.getLogger(__name__)


def get_redis_client() -> Redis:
    return aioredis.Redis(connection_pool=_pool)


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI 依赖：在请求中 yield Redis 客户端并在结束时关闭它。"""
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


async def ping_redis() -> bool:
    try:
        client = get_redis_client()
        ok = await client.ping()
        await client.aclose()
        return bool(ok)
    except Exception:
        return False


async def get_json(key: str) -> dict | list | None:
    client = get_redis_client()
    try:
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except RedisError as exc:
        logger.warning("[cache] redis read failed | key=%s | error=%s", key, exc)
        return None
    except json.JSONDecodeError as exc:
        logger.warning("[cache] invalid json payload | key=%s | error=%s", key, exc)
        return None
    finally:
        await client.aclose()


async def set_json(key: str, value: dict | list, ttl_seconds: int) -> bool:
    client = get_redis_client()
    try:
        await client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)
        return True
    except RedisError as exc:
        logger.warning("[cache] redis write failed | key=%s | error=%s", key, exc)
        return False
    finally:
        await client.aclose()
