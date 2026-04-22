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
            self.assertIn('"type": "citations"', stream_response.text)
            self.assertIn('"type": "delta", "text": "第一段"', stream_response.text)
            self.assertIn('"type": "delta", "text": "第二段"', stream_response.text)
            self.assertIn('"type": "structured"', stream_response.text)
            self.assertIn('"confidence": "low"', stream_response.text)
            self.assertIn('"type": "done"', stream_response.text)
