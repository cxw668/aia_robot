"""Redis connection pool using the synchronous redis-py client.

We use redis.asyncio for async FastAPI handlers.
"""
from __future__ import annotations

from typing import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.config import settings

# ── Connection pool (created once at module import) ───────────────────────────
_pool: aioredis.ConnectionPool = aioredis.ConnectionPool.from_url(
    settings.redis_url,
    max_connections=settings.redis_max_connections,
    decode_responses=True,      # keys/values returned as str, not bytes
)


def get_redis_client() -> Redis:
    """Return a Redis client backed by the shared connection pool."""
    return aioredis.Redis(connection_pool=_pool)


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency — yields a Redis client and closes it after the request."""
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


async def ping_redis() -> bool:
    """Health-check helper — returns True if Redis responds to PING."""
    try:
        client = get_redis_client()
        ok = await client.ping()
        await client.aclose()
        return bool(ok)
    except Exception:
        return False
