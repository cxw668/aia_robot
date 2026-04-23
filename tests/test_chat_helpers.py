from __future__ import annotations

import unittest

from app.chat.context import build_chat_context, build_support_fallback_decision, rewrite_query_with_context
from app.database import ChatMessage, MessageRole
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


class ChatContextTests(unittest.TestCase):
    def test_build_chat_context_extracts_topic_and_summary(self) -> None:
        messages = [
            ChatMessage(
                session_id="session-1",
                role=MessageRole.USER,
                content="【用户问题】\n保单借款怎么办？",
            ),
            ChatMessage(
                session_id="session-1",
                role=MessageRole.ASSISTANT,
                content="可前往官网借款入口办理。",
                citations=[
                    {
                        "title": "保单借款",
                        "service_name": "借款服务",
                        "service_url": "https://www.aia.com.cn/service/loan",
                        "collection": "aia_knowledge_base",
                    }
                ],
            ),
        ]

        context = build_chat_context(messages, max_turns=5)

        self.assertEqual(context.topic, "保单借款")
        self.assertEqual(context.service_name, "借款服务")
        self.assertIn("保单借款", context.summary)

    def test_rewrite_query_with_context_prefixes_ambiguous_follow_up(self) -> None:
        context = build_chat_context(
            [
                ChatMessage(
                    session_id="session-1",
                    role=MessageRole.USER,
                    content="【用户问题】\n保单借款怎么办？",
                ),
                ChatMessage(
                    session_id="session-1",
                    role=MessageRole.ASSISTANT,
                    content="可前往官网借款入口办理。",
                    citations=[{"title": "保单借款", "service_name": "借款服务"}],
                ),
            ],
            max_turns=5,
        )

        rewritten = rewrite_query_with_context("这个怎么办？", context)

        self.assertIn("保单借款", rewritten)
        self.assertIn("这个怎么办？", rewritten)

    def test_low_confidence_fallback_prefers_clarification_for_follow_up(self) -> None:
        context = build_chat_context(
            [
                ChatMessage(
                    session_id="session-1",
                    role=MessageRole.USER,
                    content="【用户问题】\n保单借款怎么办？",
                ),
                ChatMessage(
                    session_id="session-1",
                    role=MessageRole.ASSISTANT,
                    content="可前往官网借款入口办理。",
                    citations=[{"title": "保单借款"}],
                ),
            ],
            max_turns=5,
        )

        decision = build_support_fallback_decision(
            "这个怎么办？",
            [],
            context,
            low_confidence_threshold=0.65,
        )

        assert decision is not None
        self.assertEqual(decision.kind, "clarify")
        self.assertIn("保单借款", decision.answer)

    def test_low_confidence_fallback_uses_handoff_for_specific_question(self) -> None:
        decision = build_support_fallback_decision(
            "某产品等待期是多少？",
            [],
            build_chat_context([], max_turns=5),
            low_confidence_threshold=0.65,
        )

        assert decision is not None
        self.assertEqual(decision.kind, "handoff")
        self.assertIn("95519", decision.answer)
