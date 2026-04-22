from __future__ import annotations

import unittest
from unittest.mock import patch

from app.knowledge_base.core import embedding as embedding_module


class _FakeResponse:
    def __init__(self, payload: dict, ok: bool = True, status_code: int = 200) -> None:
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class EmbeddingTests(unittest.TestCase):
    def tearDown(self) -> None:
        embedding_module._model_instance = None

    @patch("app.knowledge_base.core.embedding.requests.post")
    def test_siliconflow_embedding_normalizes_single_query(self, mock_post) -> None:
        mock_post.return_value = _FakeResponse(
            {"data": [{"index": 0, "embedding": [3.0, 4.0]}]}
        )
        embedding_module._model_instance = None

        with patch.object(embedding_module.settings, "embedding_api_key", "test-key"):
            model = embedding_module.get_model()
            vector = model.encode("保单借款", normalize_embeddings=True)

        self.assertEqual(len(vector), 2)
        self.assertAlmostEqual(vector[0], 0.6, places=6)
        self.assertAlmostEqual(vector[1], 0.8, places=6)
        mock_post.assert_called_once()

    @patch("app.knowledge_base.core.embedding.requests.post")
    def test_siliconflow_embedding_batches_multiple_inputs(self, mock_post) -> None:
        mock_post.return_value = _FakeResponse(
            {
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0]},
                    {"index": 1, "embedding": [0.0, 1.0]},
                ]
            }
        )
        embedding_module._model_instance = None

        with patch.object(embedding_module.settings, "embedding_api_key", "test-key"):
            model = embedding_module.get_model()
            vectors = model.encode(["理赔", "退保"], normalize_embeddings=True, batch_size=2)

        self.assertEqual(vectors.tolist(), [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(mock_post.call_args.kwargs["json"]["input"], ["理赔", "退保"])
