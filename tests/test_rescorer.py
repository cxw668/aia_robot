from __future__ import annotations

import unittest
from unittest.mock import patch

from app.knowledge_base.retrieval.rescorer import llm_rescore_candidates


def _candidates() -> list[dict]:
    return [
        {"id": "1", "title": "借款", "content": "保单借款办理说明", "score": 0.71},
        {"id": "2", "title": "退保", "content": "退保办理说明", "score": 0.63},
    ]


class RescorerTests(unittest.TestCase):
    @patch("app.chat.index.query_llm", side_effect=RuntimeError("boom"))
    def test_rescorer_falls_back_when_llm_call_fails(self, _: object) -> None:
        result = llm_rescore_candidates("保单借款怎么办", _candidates(), final_top_k=1)

        self.assertFalse(result.used_llm)
        self.assertEqual(result.fallback_reason, "llm_request_failed")
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0]["id"], "1")

    @patch("app.chat.index.query_llm", return_value="not-json")
    def test_rescorer_falls_back_when_llm_response_is_invalid(self, _: object) -> None:
        result = llm_rescore_candidates("保单借款怎么办", _candidates(), final_top_k=2)

        self.assertFalse(result.used_llm)
        self.assertEqual(result.fallback_reason, "llm_response_parse_failed")
        self.assertEqual(len(result.items), 2)

    @patch(
        "app.chat.index.query_llm",
        return_value='[{"id":"2","relevance_score":0.95,"verdict":"use"},{"id":"1","relevance_score":0.2,"verdict":"skip"}]',
    )
    def test_rescorer_returns_llm_ranked_items_when_parse_succeeds(self, _: object) -> None:
        result = llm_rescore_candidates("退保怎么办", _candidates(), final_top_k=2)

        self.assertTrue(result.used_llm)
        self.assertIsNone(result.fallback_reason)
        self.assertEqual(result.items[0]["id"], "2")

    @patch(
        "app.chat.index.query_llm",
        return_value='评分结果如下：```json\n[{id: 2, relevance_score: 0.95, verdict: "use"}, {id: 1, relevance_score: 0.2, verdict: "skip"}]\n```\n请按此排序。',
    )
    def test_rescorer_accepts_fenced_json_with_unquoted_keys(self, _: object) -> None:
        result = llm_rescore_candidates("退保怎么办", _candidates(), final_top_k=2)

        self.assertTrue(result.used_llm)
        self.assertIsNone(result.fallback_reason)
        self.assertEqual(result.items[0]["id"], "2")
