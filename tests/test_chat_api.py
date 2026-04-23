from __future__ import annotations

import unittest

from tests.api_test_utils import (
    FakeAsyncSession,
    auth_headers,
    create_test_client,
    register_user,
)


class ChatApiTests(unittest.TestCase):
    def test_chat_history_and_delete_flow(self) -> None:
        docs = [
            {
                "title": "保单借款",
                "content": "可通过友邦官网提交借款申请。",
                "score": 0.98,
                "service_name": "借款",
                "service_url": "https://www.aia.com.cn/service/loan",
                "collection": "aia_knowledge_base",
            }
        ]
        db = FakeAsyncSession()

        with create_test_client(
            db,
            retrieve_docs=docs,
            chat_answer="您可以通过友邦官网提交保单借款申请。",
        ) as client:
            token = register_user(client)

            chat_response = client.post(
                "/chat",
                headers=auth_headers(token),
                json={"query": "保单借款怎么办？", "mode": "support"},
            )

            self.assertEqual(chat_response.status_code, 200)
            chat_payload = chat_response.json()
            self.assertEqual(chat_payload["answer"], "您可以通过友邦官网提交保单借款申请。")
            self.assertEqual(len(chat_payload["citations"]), 1)
            self.assertEqual(chat_payload["citations"][0]["title"], "保单借款")
            self.assertEqual(chat_payload["structured_answer"]["summary"], "您可以通过友邦官网提交保单借款申请。")
            self.assertEqual(chat_payload["structured_answer"]["confidence"], "high")
            self.assertEqual(
                chat_payload["structured_answer"]["next_actions"][0]["url"],
                "https://www.aia.com.cn/service/loan",
            )

            session_id = chat_payload["session_id"]
            history_response = client.get(
                f"/chat/{session_id}/history",
                headers=auth_headers(token),
            )
            self.assertEqual(history_response.status_code, 200)
            history_payload = history_response.json()
            self.assertEqual(history_payload["session_id"], session_id)
            self.assertEqual(len(history_payload["messages"]), 2)
            self.assertEqual(history_payload["messages"][0]["role"], "user")
            self.assertIn("【用户问题】\n保单借款怎么办？", history_payload["messages"][0]["content"])
            self.assertEqual(history_payload["messages"][1]["role"], "assistant")
            self.assertEqual(history_payload["messages"][1]["content"], "您可以通过友邦官网提交保单借款申请。")

            delete_response = client.delete(
                f"/chat/{session_id}",
                headers=auth_headers(token),
            )
            self.assertEqual(delete_response.status_code, 200)
            self.assertEqual(delete_response.json()["status"], "cleared")

            missing_history_response = client.get(
                f"/chat/{session_id}/history",
                headers=auth_headers(token),
            )
            self.assertEqual(missing_history_response.status_code, 404)
            self.assertEqual(missing_history_response.json()["error"]["code"], "not_found")

    def test_stream_chat_returns_sse_events(self) -> None:
        db = FakeAsyncSession()

        with create_test_client(
            db,
            retrieve_docs=[],
            stream_chunks=["第一段", "第二段"],
        ) as client:
            token = register_user(client, username="streamer")

            stream_response = client.post(
                "/chat/stream",
                headers=auth_headers(token),
                json={"query": "你好", "mode": "casual"},
            )

            self.assertEqual(stream_response.status_code, 200)
            self.assertEqual(stream_response.headers["content-type"], "text/event-stream; charset=utf-8")
            self.assertIn('"type": "progress"', stream_response.text)
            self.assertIn('"stage": "context_ready"', stream_response.text)
            self.assertIn('"type": "citations"', stream_response.text)
            self.assertIn('"type": "delta", "text": "第一段"', stream_response.text)
            self.assertIn('"type": "delta", "text": "第二段"', stream_response.text)
            self.assertIn('"type": "structured"', stream_response.text)
            self.assertIn('"confidence": "low"', stream_response.text)
            self.assertIn('"type": "done"', stream_response.text)

    def test_follow_up_query_reuses_context_for_retrieval(self) -> None:
        queries: list[str] = []
        docs = [
            {
                "title": "保单借款",
                "content": "可通过友邦官网提交借款申请。",
                "score": 0.96,
                "service_name": "借款",
                "service_url": "https://www.aia.com.cn/service/loan",
                "collection": "aia_knowledge_base",
            }
        ]
        db = FakeAsyncSession()

        def retrieve_docs(query: str, top_k: int = 5, category: str | None = None) -> list[dict]:
            del top_k, category
            queries.append(query)
            return docs if "保单借款" in query else []

        with create_test_client(
            db,
            retrieve_docs=retrieve_docs,
            chat_answer="请前往友邦官网借款入口办理。",
        ) as client:
            token = register_user(client, username="followup")

            first_response = client.post(
                "/chat",
                headers=auth_headers(token),
                json={"query": "保单借款怎么办？", "mode": "support"},
            )
            self.assertEqual(first_response.status_code, 200)

            second_response = client.post(
                "/chat",
                headers=auth_headers(token),
                json={
                    "query": "这个怎么办？",
                    "mode": "support",
                    "session_id": first_response.json()["session_id"],
                },
            )

            self.assertEqual(second_response.status_code, 200)
            self.assertGreaterEqual(len(queries), 2)
            self.assertIn("保单借款", queries[-1])
            self.assertEqual(second_response.json()["structured_answer"]["confidence"], "high")

    def test_chat_returns_clarification_for_low_confidence_support_query(self) -> None:
        db = FakeAsyncSession()

        with create_test_client(
            db,
            retrieve_docs=[],
            chat_answer="这段回答不应被返回。",
        ) as client:
            token = register_user(client, username="clarify")

            response = client.post(
                "/chat",
                headers=auth_headers(token),
                json={"query": "这个怎么办？", "mode": "support"},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("还不够具体", payload["answer"])
            self.assertEqual(payload["structured_answer"]["confidence"], "low")
            self.assertIn("补充", payload["structured_answer"]["next_actions"][0]["label"])

    def test_stream_chat_returns_fallback_sequence_for_low_confidence_support_query(self) -> None:
        db = FakeAsyncSession()

        with create_test_client(
            db,
            retrieve_docs=[],
            chat_answer="这段回答不应被返回。",
            stream_chunks=["模型流式输出"],
        ) as client:
            token = register_user(client, username="stream-fallback")

            stream_response = client.post(
                "/chat/stream",
                headers=auth_headers(token),
                json={"query": "这个怎么办？", "mode": "support"},
            )

            self.assertEqual(stream_response.status_code, 200)
            self.assertIn("还不够具体", stream_response.text)
            self.assertIn('"type": "structured"', stream_response.text)
            self.assertIn('"confidence": "low"', stream_response.text)
            self.assertIn('"type": "done"', stream_response.text)

    def test_chat_keeps_llm_reranked_recommendation_answer_when_evidence_is_rich(self) -> None:
        docs = [
            {
                "title": "大学生保险建议",
                "content": "临近毕业且运动频率较高的人群，可优先关注意外伤害、医疗保障和基础重疾保障。",
                "score": 0.41,
                "llm_score": 0.88,
                "llm_verdict": "use",
                "service_name": "个险推荐产品",
                "service_url": "https://www.aia.com.cn/products",
                "collection": "aia_knowledge_base",
            }
        ]
        db = FakeAsyncSession()

        with create_test_client(
            db,
            retrieve_docs=docs,
            chat_answer="根据知识库内容，您可以优先考虑意外险、医疗险和基础重疾保障。",
        ) as client:
            token = register_user(client, username="recommendation")

            response = client.post(
                "/chat",
                headers=auth_headers(token),
                json={
                    "query": "我是一个大四毕业生，即将毕业，热爱篮球运动，推荐几个我适合购买的保险产品。",
                    "mode": "support",
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["answer"], "根据知识库内容，您可以优先考虑意外险、医疗险和基础重疾保障。")
            self.assertNotIn("我暂时没有从当前知识库里找到足够直接的依据", payload["answer"])
            self.assertNotEqual(payload["structured_answer"]["confidence"], "low")

    def test_chat_keeps_single_reranked_recommendation_hit_without_fallback(self) -> None:
        docs = [
            {
                "title": "大学生保险建议",
                "content": "临近毕业且运动频率较高的人群，可优先关注意外伤害、医疗保障和基础重疾保障。",
                "score": 0.33,
                "llm_score": 0.34,
                "llm_verdict": "use",
                "service_name": "个险推荐产品",
                "service_url": "https://www.aia.com.cn/products",
                "collection": "aia_knowledge_base",
            }
        ]
        db = FakeAsyncSession()

        with create_test_client(
            db,
            retrieve_docs=docs,
            chat_answer="结合知识库内容，您可以优先考虑意外和医疗保障，再根据预算补充重疾保障。",
        ) as client:
            token = register_user(client, username="recommendation-single-hit")

            response = client.post(
                "/chat",
                headers=auth_headers(token),
                json={
                    "query": "我是一个大四毕业生，即将毕业，热爱篮球运动，推荐几个我适合购买的保险产品。",
                    "mode": "support",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["answer"],
                "结合知识库内容，您可以优先考虑意外和医疗保障，再根据预算补充重疾保障。",
            )
