from __future__ import annotations

import unittest
from collections import Counter

import scripts.evaluate_intent_quality as intent_quality
import scripts.evaluate_retrieval_quality as retrieval_quality


class RegressionDatasetTests(unittest.TestCase):
    def test_retrieval_dataset_covers_high_frequency_business_categories(self) -> None:
        counts = Counter(case.category for case in retrieval_quality.TEST_CASES)

        self.assertGreaterEqual(counts["表单下载"], 4)
        self.assertGreaterEqual(counts["分公司"], 3)
        self.assertGreaterEqual(counts["在售产品"], 3)
        self.assertGreaterEqual(
            counts["保单服务"] + counts["保险计划变更"] + counts["合同"],
            5,
        )

    def test_retrieval_dataset_has_schema_hints_for_high_frequency_categories(self) -> None:
        self.assertEqual(retrieval_quality.CATEGORY_TO_SCHEMA_HINTS["表单下载"], ["forms_markdown"])
        self.assertEqual(retrieval_quality.CATEGORY_TO_SCHEMA_HINTS["分公司"], ["branches"])
        self.assertEqual(retrieval_quality.CATEGORY_TO_SCHEMA_HINTS["在售产品"], ["products_list"])
        self.assertEqual(retrieval_quality.CATEGORY_TO_SCHEMA_HINTS["合同"], ["service_categories"])

    def test_intent_dataset_covers_high_frequency_user_questions(self) -> None:
        counts = Counter(case.expected_intent for case in intent_quality.TEST_CASES)

        self.assertGreaterEqual(counts["service_guide"], 5)
        self.assertGreaterEqual(counts["form"], 4)
        self.assertGreaterEqual(counts["branch"], 4)
        self.assertGreaterEqual(counts["on_sale_product"], 4)
