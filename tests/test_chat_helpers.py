from __future__ import annotations

import unittest

from app.routers.chat import ChatMode, _build_chat_cache_key


class ChatCacheKeyTests(unittest.TestCase):
    def test_cache_key_changes_with_history(self) -> None:
        base_history = [{"role": "system", "content": "system"}]
        follow_up_history = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "保单借款怎么办"},
        ]

        first = _build_chat_cache_key(
            query="怎么办",
            retrieval_query="保单借款 怎么办",
            mode=ChatMode.SUPPORT,
            category=None,
            top_k=5,
            history=base_history,
        )
        second = _build_chat_cache_key(
            query="怎么办",
            retrieval_query="保单借款 怎么办",
            mode=ChatMode.SUPPORT,
            category=None,
            top_k=5,
            history=follow_up_history,
        )

        self.assertNotEqual(first, second)

    def test_cache_key_changes_with_mode(self) -> None:
        history = [{"role": "system", "content": "system"}]

        support_key = _build_chat_cache_key(
            query="你好",
            retrieval_query="你好",
            mode=ChatMode.SUPPORT,
            category=None,
            top_k=5,
            history=history,
        )
        casual_key = _build_chat_cache_key(
            query="你好",
            retrieval_query="你好",
            mode=ChatMode.CASUAL,
            category=None,
            top_k=5,
            history=history,
        )

        self.assertNotEqual(support_key, casual_key)
