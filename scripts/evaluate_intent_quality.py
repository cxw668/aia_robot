#!/usr/bin/env python3
"""首层意图识别质量测试脚本。"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.env_loader import EnvLoader

EnvLoader.load()

from app.knowledge_base.intent_recognition import classify_query_intent_with_scores

OUTPUT_PATH = ROOT / "docs" / "意图识别测试结果.json"


@dataclass(frozen=True)
class IntentTestCase:
    query: str
    expected_intent: str
    notes: str = ""


TEST_CASES: list[IntentTestCase] = [
    IntentTestCase("怎么变更投保人？需要谁签字？", "service_guide"),
    IntentTestCase("我的联系方式变了，去哪里改联系电话和地址？", "service_guide"),
    IntentTestCase("退保时如果还有借款没还，会怎么处理？", "service_guide"),
    IntentTestCase("理赔申请要下载什么个险表单？", "form"),
    IntentTestCase("团险续保需要哪份申请书？", "form"),
    IntentTestCase("第三方代缴保费需要哪张授权委托书？", "form"),
    IntentTestCase("北京分公司客服电话是多少？", "branch"),
    IntentTestCase("安徽分公司信访接待日是什么时候？", "branch"),
    IntentTestCase("广东分公司地址在哪里？", "branch"),
    IntentTestCase("河北分公司升级改建的新闻是什么？", "branch_news"),
    IntentTestCase("友邦北京的乳腺健康公益讲座是什么活动？", "branch_news"),
    IntentTestCase("天津 7.8 全国保险公众宣传日有什么特别企划？", "branch_news"),
    IntentTestCase("个险里面的疾病保障主要是做什么的？", "product_category"),
    IntentTestCase("团险的员工企业福利是什么意思？", "product_category"),
    IntentTestCase("教育储备类保险大概是什么定位？", "product_category"),
    IntentTestCase("有没有适合儿童的意外伤害保险产品计划？", "recommended_product"),
    IntentTestCase("有没有高端医疗相关的个险推荐产品？", "recommended_product"),
    IntentTestCase("想找高端医疗尊享组合计划，团险有吗？", "recommended_product"),
    IntentTestCase("友邦星耀未来年金保险现在在售吗？", "on_sale_product"),
    IntentTestCase("有没有友邦传世颐年养老年金保险的产品说明书？", "on_sale_product"),
    IntentTestCase("友邦增盈宝C款终身寿险（万能型）属于哪个产品组？", "on_sale_product"),
    IntentTestCase("表单下载入口在哪里？", "menu"),
    IntentTestCase("理赔服务页面从哪里进入？", "menu"),
    IntentTestCase("官网入口怎么去客户服务？", "menu"),
    IntentTestCase("保险欺诈举报邮箱是多少？", "anti_fraud"),
    IntentTestCase("哪些行为属于保险欺诈？", "anti_fraud"),
    IntentTestCase("保险欺诈可能承担什么责任？", "anti_fraud"),
]


def evaluate_case(case: IntentTestCase) -> dict:
    started = time.perf_counter()
    result = classify_query_intent_with_scores(case.query)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    predicted = result.intent.key if result.intent else None
    top_candidates = [
        {
            "intent": candidate.key,
            "score": candidate.score,
            "confidence": candidate.confidence,
        }
        for candidate in result.candidates[:3]
    ]
    return {
        "query": case.query,
        "expected_intent": case.expected_intent,
        "predicted_intent": predicted,
        "passed": predicted == case.expected_intent,
        "elapsed_ms": elapsed_ms,
        "normalized_query": result.normalized_query,
        "confidence": result.confidence,
        "needs_confirmation": result.needs_confirmation,
        "top_candidates": top_candidates,
        "notes": case.notes,
    }


def build_summary(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(int(row["passed"]) for row in results)
    by_intent: dict[str, dict[str, int]] = {}
    failed_cases: list[dict] = []
    confirmation_required = sum(int(row["needs_confirmation"]) for row in results)
    avg_confidence = round(sum(float(row["confidence"]) for row in results) / total, 4) if total else 0.0

    for row in results:
        bucket = by_intent.setdefault(
            row["expected_intent"],
            {"total": 0, "passed": 0, "avg_confidence": 0.0, "confirmation_required": 0},
        )
        bucket["total"] += 1
        bucket["passed"] += int(row["passed"])
        bucket["avg_confidence"] += float(row["confidence"])
        bucket["confirmation_required"] += int(row["needs_confirmation"])
        if not row["passed"]:
            failed_cases.append({
                "query": row["query"],
                "expected_intent": row["expected_intent"],
                "predicted_intent": row["predicted_intent"],
                "confidence": row["confidence"],
                "top_candidates": row["top_candidates"],
            })

    for stats in by_intent.values():
        stats["avg_confidence"] = round(stats["avg_confidence"] / stats["total"], 4) if stats["total"] else 0.0

    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "pass_rate": round(passed / total * 100, 2) if total else 0.0,
        "avg_confidence": avg_confidence,
        "confirmation_required": confirmation_required,
        "by_intent": by_intent,
        "failed_case_details": failed_cases,
    }


def main() -> None:
    results = [evaluate_case(case) for case in TEST_CASES]
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": build_summary(results),
        "cases": results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report["summary"]
    print("=" * 72)
    print("意图识别测试完成")
    print("-" * 72)
    print(f"total      : {summary['total_cases']}")
    print(f"passed     : {summary['passed_cases']}")
    print(f"failed     : {summary['failed_cases']}")
    print(f"pass_rate  : {summary['pass_rate']}%")
    print(f"avg_conf   : {summary['avg_confidence']}")
    print(f"need_clarify: {summary['confirmation_required']}")
    print(f"output     : {OUTPUT_PATH}")
    print("-" * 72)
    for intent, stats in summary["by_intent"].items():
        print(
            f"{intent:<20} {stats['passed']}/{stats['total']} "
            f"avg_conf={stats['avg_confidence']} clarify={stats['confirmation_required']}"
        )
    print("=" * 72)


if __name__ == "__main__":
    main()
