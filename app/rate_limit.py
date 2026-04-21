from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(
        self,
        *,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> bool:
        current = now if now is not None else time.time()
        bucket_key = f"{scope}:{key}"
        cutoff = current - window_seconds

        with self._lock:
            bucket = self._events.setdefault(bucket_key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(current)
            return True


rate_limiter = FixedWindowRateLimiter()


def _client_key(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded_for:
        return forwarded_for
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def build_rate_limit_dependency(
    *,
    scope: str,
    limit: int,
    window_seconds: int,
    message: str,
) -> Callable[[Request], None]:
    async def dependency(request: Request) -> None:
        if limit <= 0 or window_seconds <= 0:
            return
        if rate_limiter.allow(
            scope=scope,
            key=_client_key(request),
            limit=limit,
            window_seconds=window_seconds,
        ):
            return
        raise HTTPException(status_code=429, detail=message)

    return dependency
