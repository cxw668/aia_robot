from __future__ import annotations

import unittest

from app.rate_limit import FixedWindowRateLimiter


class RateLimitTests(unittest.TestCase):
    def test_limiter_blocks_requests_over_limit_within_window(self) -> None:
        limiter = FixedWindowRateLimiter()
        self.assertTrue(limiter.allow(scope="auth", key="127.0.0.1", limit=2, window_seconds=60, now=100.0))
        self.assertTrue(limiter.allow(scope="auth", key="127.0.0.1", limit=2, window_seconds=60, now=101.0))
        self.assertFalse(limiter.allow(scope="auth", key="127.0.0.1", limit=2, window_seconds=60, now=102.0))

    def test_limiter_allows_requests_after_window_expires(self) -> None:
        limiter = FixedWindowRateLimiter()
        self.assertTrue(limiter.allow(scope="chat", key="127.0.0.1", limit=1, window_seconds=10, now=100.0))
        self.assertFalse(limiter.allow(scope="chat", key="127.0.0.1", limit=1, window_seconds=10, now=105.0))
        self.assertTrue(limiter.allow(scope="chat", key="127.0.0.1", limit=1, window_seconds=10, now=111.0))
