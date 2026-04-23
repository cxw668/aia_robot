from __future__ import annotations

import unittest

from app.chat.structured import build_structured_answer


class StructuredAnswerTests(unittest.TestCase):
    def test_build_structured_answer_uses_citations_for_support_mode(self) -> None:
        answer = "您可以通过友邦官网提交保单借款申请。"
        citations = [
            {
                "title": "保单借款",
                "content": "可通过友邦官网提交借款申请，并按页面提示完成身份验证。",
                "score": 0.91,
                "service_name": "借款服务",
                "service_url": "https://www.aia.com.cn/service/loan",
            }
        ]

        structured = build_structured_answer(answer, citations, support_mode=True)

        self.assertEqual(structured.summary, answer)
        self.assertEqual(structured.confidence, "high")
        self.assertEqual(structured.evidence[0].title, "保单借款")
        self.assertEqual(
            structured.next_actions[0].url,
            "https://www.aia.com.cn/service/loan",
        )
        self.assertIn("正式合同", structured.risk_tips[0])

    def test_build_structured_answer_falls_back_without_evidence(self) -> None:
        structured = build_structured_answer("你好", [], support_mode=False)

        self.assertEqual(structured.confidence, "low")
        self.assertEqual(len(structured.evidence), 0)
        self.assertEqual(len(structured.next_actions), 1)
        self.assertIn("缺少直接知识库证据", structured.risk_tips[-1])

    def test_build_structured_answer_uses_clarification_actions_for_fallback(self) -> None:
        structured = build_structured_answer(
            "我理解您可能在继续咨询“保单借款”。",
            [],
            support_mode=True,
            fallback_kind="clarify",
            clarification_options=("办理条件", "下载入口"),
            context_topic="保单借款",
        )

        self.assertEqual(structured.confidence, "low")
        self.assertIn("确认是否继续咨询“保单借款”", structured.next_actions[0].label)
        self.assertIn("补充办理条件", structured.next_actions[1].label)
        self.assertIn("上下文省略", structured.risk_tips[1])
