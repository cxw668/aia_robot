from __future__ import annotations

import math
import threading
import time
from collections import deque


class FailedLoginTracker:
    def __init__(
        self,
        *,
        max_failures: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lockouts: dict[str, float] = {}
        self._lock = threading.Lock()

    def get_retry_after(self, username: str, *, now: float | None = None) -> int:
        current = now if now is not None else time.time()
        with self._lock:
            self._prune(username, current)
            locked_until = self._lockouts.get(username)
            if locked_until is None:
                return 0
            return max(1, math.ceil(locked_until - current))

    def record_failure(self, username: str, *, now: float | None = None) -> int:
        current = now if now is not None else time.time()
        if self.max_failures <= 0 or self.window_seconds <= 0 or self.lockout_seconds <= 0:
            return 0

        with self._lock:
            self._prune(username, current)
            bucket = self._failures.setdefault(username, deque())
            bucket.append(current)
            if len(bucket) < self.max_failures:
                return 0

            locked_until = current + self.lockout_seconds
            self._lockouts[username] = locked_until
            self._failures.pop(username, None)
            return max(1, math.ceil(locked_until - current))

    def reset(self, username: str) -> None:
        with self._lock:
            self._failures.pop(username, None)
            self._lockouts.pop(username, None)

    def _prune(self, username: str, current: float) -> None:
        locked_until = self._lockouts.get(username)
        if locked_until is not None and locked_until <= current:
            self._lockouts.pop(username, None)

        bucket = self._failures.get(username)
        if bucket is None:
            return

        cutoff = current - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if not bucket:
            self._failures.pop(username, None)
