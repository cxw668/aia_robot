from __future__ import annotations
from typing import AsyncGenerator
import redis.asyncio as aioredis
from redis.asyncio import Redis
from app.config import settings

_pool: aioredis.ConnectionPool = aioredis.ConnectionPool.from_url(
    settings.redis_url,
    max_connections=settings.redis_max_connections,
    decode_responses=True,
)


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
