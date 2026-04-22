from __future__ import annotations

import unittest
from unittest.mock import patch

from app.knowledge_base.ingestion import _pipeline_impl as pipeline


class IngestionChunkingTests(unittest.TestCase):
    def test_split_docs_for_embedding_limit_splits_long_content(self) -> None:
        doc = {
            "text": "「保单服务」\n" + ("理" * 500),
            "payload": {
                "title": "保单服务",
                "content": "理" * 500,
                "category": "保单服务",
            },
        }

        with patch.object(pipeline.settings, "embedding_max_input_chars", 200):
            chunks = pipeline._split_docs_for_embedding_limit([doc])

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(item["text"]) <= 210 for item in chunks))
        self.assertTrue(all(item["payload"]["embedding_chunked"] for item in chunks))
        self.assertEqual(chunks[0]["payload"]["chunk_index"], 0)
        self.assertEqual(chunks[0]["payload"]["chunk_total"], len(chunks))

    def test_split_docs_for_embedding_limit_keeps_short_content(self) -> None:
        doc = {
            "text": "「借款」\n可通过官网办理借款。",
            "payload": {
                "title": "借款",
                "content": "可通过官网办理借款。",
                "category": "借款",
            },
        }

        with patch.object(pipeline.settings, "embedding_max_input_chars", 200):
            chunks = pipeline._split_docs_for_embedding_limit([doc])

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], doc["text"])
        self.assertNotIn("embedding_chunked", chunks[0]["payload"])
