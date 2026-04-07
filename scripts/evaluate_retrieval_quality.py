#!/usr/bin/env python3
"""检索质量验证脚本。"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.env_loader import EnvLoader

EnvLoader.load()

from app.knowledge_base.rag import DEFAULT_COLLECTION, retrieve
from app.knowledge_base.intent_recognition import classify_query_intent_with_scores
from app.knowledge_base.category_utils import category_matches, normalize_category, get_point_category

OUTPUT_PATH = ROOT / "docs" / "检索质量测试结果.json"
INTENT_OUTPUT_PATH = ROOT / "docs" / "意图识别测试结果.json"
TOP_K = 5
IGNORED_CATEGORIES = {"客户服务菜单"}


@dataclass
class TestCase:
    category: str
    question: str
    expected_categories: list[str]
    expected_keywords: list[str]
    notes: str = ""


TEST_CASES: list[TestCase] = [
    # TestCase("保单服务", "怎么变更投保人？需要谁签字？", ["保单服务"], ["变更投保人", "原投保人", "新投保人", "被保险人"]),
    # TestCase("保单服务", "想把身故保险金受益人改掉，要准备什么？", ["保单服务"], ["变更身故保险金受益人", "受益人"]),
    # TestCase("保单服务", "我的联系方式变了，去哪里改联系电话和地址？", ["保单服务"], ["变更联系资料", "联系电话", "通讯地址"]),
    TestCase("保险计划变更", "保单失效后还能复效吗？", ["保险计划变更"], ["保险合同效力恢复", "恢复合同效力"]),
    TestCase("保险计划变更", "我想把年缴改成月缴，怎么申请？", ["保险计划变更"], ["变更保险费支付方式", "年付", "月付"]),
    TestCase("保险计划变更", "附加险不想要了，能取消附加合同吗？", ["保险计划变更"], ["取消附加合同"]),
    # TestCase("合同", "纸质保单丢了，怎么补发保险合同？", ["合同"], ["补发保险合同", "纸质保险合同"]),
    # TestCase("合同", "电子保险合同怎么申请或者查看？", ["合同"], ["申请电子保险合同", "电子合同"]),
    # TestCase("合同", "我想申请付款凭证或者发票，怎么弄？", ["合同"], ["申请发票与付款凭证", "付款凭证", "发票"]),
    # TestCase("借款", "保单可以借款吗？单日金额有限制吗？", ["借款"], ["保单借款", "20万元", "5万元"]),
    # TestCase("借款", "已经借过款了，现在想还款怎么办？", ["借款"], ["保单还款", "还款"]),
    # TestCase("借款", "申请保单借款需要准备哪些材料？", ["借款"], ["借款申请书", "有效身份证明"]),
    # TestCase("年金", "年金怎么领取？谁可以申请？", ["年金"], ["年金/生存金的领取", "领款人"]),
    # TestCase("年金", "现金红利处理方式可以变更吗？", ["年金"], ["变更现金红利处理方式", "现金红利"]),
    # TestCase("年金", "生存现金可以提现吗，还是能转万能账户？", ["年金"], ["变更生存现金处理方式", "万能账户", "生存现金"]),
    # TestCase("退保", "犹豫期内可以撤销保险合同吗？", ["退保"], ["犹豫期内保险合同撤销", "犹豫期"]),
    # TestCase("退保", "过了犹豫期之后退保，多久能退现金价值？", ["退保"], ["解除保险合同/退保", "三十日", "现金价值"]),
    # TestCase("退保", "退保时如果还有借款没还，会怎么处理？", ["退保"], ["解除保险合同/退保", "未还款项", "先予扣除"]),
    # TestCase("万能险", "万能险可以追加保险费吗？", ["万能险"], ["支付追加保险费", "万能险"]),
    # TestCase("万能险", "投连险个人账户价值能转换到别的投资账户吗？", ["万能险"], ["个人账户价值转换", "投资账户"]),
    # TestCase("万能险", "期交保险费投资账户分配比例可以改吗？", ["万能险"], ["分配比例变更", "投资账户"]),
    # TestCase("续期及账户管理", "续期保费怎么交？可以在线支付吗？", ["续期及账户管理"], ["续期续保", "在线支付", "银行自动转账"]),
    # TestCase("续期及账户管理", "我想把续期扣款银行卡换掉，怎么办？", ["续期及账户管理"], ["保险费付款的自动转账授权", "银行账号"]),
    # TestCase("续期及账户管理", "领取保险金的账户能修改吗？", ["续期及账户管理"], ["保险款项给付的自动转账授权", "领款账号"]),
    # TestCase("分公司页面", "北京分公司客服电话是多少？", ["分公司"], ["北京分公司", "6528 6938", "北京"]),
    # TestCase("分公司页面", "广东分公司地址在哪里？", ["分公司"], ["广东分公司", "沿江西路", "广州"]),
    # TestCase("分公司页面", "安徽分公司信访接待日是什么时候？", ["分公司"], ["安徽分公司", "第四个星期四", "信访接待日"]),
    # TestCase("分公司新闻", "友邦北京的乳腺健康公益讲座是什么活动？", ["分公司动态"], ["乳腺健康公益讲座", "北京"]),
    # TestCase("分公司新闻", "河北分公司升级改建的新闻是什么？", ["分公司动态"], ["河北分公司", "改建升级"]),
    # TestCase("分公司新闻", "天津 7.8 全国保险公众宣传日有什么特别企划？", ["分公司动态"], ["7.8全国保险公众宣传日", "天津"]),
    # TestCase("产品分类", "个险里面的疾病保障主要是做什么的？", ["个险产品", "个险"], ["疾病保障", "重大疾病"]),
    # TestCase("产品分类", "团险的员工企业福利是什么意思？", ["团险产品", "团险"], ["员工企业福利", "员工福利"]),
    # TestCase("产品分类", "教育储备类保险大概是什么定位？", ["个险产品", "个险"], ["教育储备", "教育金"]),
    # TestCase("个险推荐产品", "有没有适合儿童的意外伤害保险产品计划？", ["个险推荐产品"], ["儿童", "意外伤害保险产品计划"]),
    # TestCase("个险推荐产品", "长保康惠长期医疗保险适合什么场景？", ["个险推荐产品"], ["长保康惠", "长期医疗"]),
    # TestCase("个险推荐产品", "有没有高端医疗相关的个险推荐产品？", ["个险推荐产品"], ["高端医疗", "友童无忧"]),
    # TestCase("团险推荐产品", "有没有适合企业员工福利的团险中端医疗方案？", ["团险推荐产品"], ["中端医疗", "员工企业福利"]),
    # TestCase("团险推荐产品", "团险补充医疗优享组合计划是什么？", ["团险推荐产品"], ["补充医疗优享组合计划"]),
    # TestCase("团险推荐产品", "想找高端医疗尊享组合计划，团险有吗？", ["团险推荐产品"], ["高端医疗尊享组合计划", "团险"]),
    # TestCase("在售产品", "友邦星耀未来年金保险现在在售吗？", ["在售产品"], ["友邦星耀未来年金保险", "在售"]),
    # TestCase("在售产品", "有没有友邦传世颐年养老年金保险的产品说明书？", ["在售产品"], ["友邦传世颐年养老年金保险", "产品说明书"]),
    # TestCase("在售产品", "友邦增盈宝C款终身寿险（万能型）属于哪个产品组？", ["在售产品"], ["友邦增盈宝C款终身寿险", "产品组", "P3"]),
    # TestCase("反保险欺诈", "哪些行为属于保险欺诈？", ["反欺诈"], ["保险欺诈", "虚构保险标的", "虚假理赔申请材料"]),
    # TestCase("反保险欺诈", "保险欺诈可能承担什么责任？", ["反欺诈"], ["刑事责任", "行政责任", "民事责任"]),
    # TestCase("反保险欺诈", "保险欺诈举报邮箱是多少？", ["反欺诈"], ["CN.BXQZJB@aia.com", "举报邮箱"]),
    # TestCase("表单下载", "变更投保人要下载哪份个险表单？", ["表单下载"], ["《保险合同内容变更申请书》", "保险合同内容变更申请书"]),
    # TestCase("表单下载", "理赔申请要下载什么个险表单？", ["表单下载"], ["《保险金给付申请书》", "保险金给付申请书"]),
    # TestCase("表单下载", "第三方代缴保费需要哪张授权委托书？", ["表单下载"], ["《第三方缴费授权委托书》", "第三方缴费授权委托书"]),
    # TestCase("表单下载", "团险理赔申请书在哪里下载？", ["表单下载"], ["《团险理赔申请书》", "团险理赔申请书"]),
    # TestCase("表单下载", "团险续保需要哪份申请书？", ["表单下载"], ["《团体保险续保申请书》", "团体保险续保申请书", "续保"]),
    # TestCase("表单下载", "团险合同变更申请书有上海专用版吗？", ["表单下载"], ["《合同变更申请书》", "合同变更申请书", "上海专用版"]),
]


CATEGORY_TO_SCHEMA_HINTS: dict[str, list[str]] = {
    "保单服务": ["service_categories"],
    "保险计划变更": ["service_categories"],
    "合同": ["service_categories"],
    "借款": ["service_categories"],
    "年金": ["service_categories"],
    "退保": ["service_categories"],
    "万能险": ["service_categories"],
    "续期及账户管理": ["service_categories"],
    "分公司页面": ["branches"],
    "分公司新闻": ["branches"],
    "产品分类": ["products_page"],
    "个险推荐产品": ["recommended_products"],
    "团险推荐产品": ["recommended_products"],
    "在售产品": ["products_list"],
    "反保险欺诈": ["text"],
    "表单下载": ["forms_markdown"],
}


def contains_any(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    return any(keyword in text for keyword in keywords)


def content_to_text(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


def hit_schema(hit: dict[str, Any]) -> str:
    return str(hit.get("schema") or hit.get("payload", {}).get("schema", ""))


def normalize_hit(hit: dict[str, Any]) -> dict[str, Any]:
    content = content_to_text(hit.get("content")).replace("\n", " ")
    return {
        "score": hit.get("score"),
        "title": hit.get("title", ""),
        "category": hit.get("category", ""),
        "service_name": hit.get("service_name", ""),
        "schema": hit_schema(hit),
        "content_preview": content[:180],
    }


def evaluate_case(case: TestCase) -> dict[str, Any]:
    started = time.perf_counter()
    only_on_sale = case.category == "在售产品"
    hits = retrieve(
        case.question,
        top_k=TOP_K,
        collection_name=DEFAULT_COLLECTION,
        only_on_sale=only_on_sale,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    schema_hints = CATEGORY_TO_SCHEMA_HINTS.get(case.category, [])
    top_hit = hits[0] if hits else {}

    top_text = "\n".join([
        str(top_hit.get("title", "")),
        content_to_text(top_hit.get("content", "")),
        str(top_hit.get("category", "")),
        str(top_hit.get("service_name", "")),
        hit_schema(top_hit),
    ])

    hit_texts = [
        "\n".join([
            str(hit.get("title", "")),
            content_to_text(hit.get("content", "")),
            str(hit.get("category", "")),
            str(hit.get("service_name", "")),
            hit_schema(hit),
        ])
        for hit in hits
    ]

    # Prefer normalized/alias-aware category matching; fall back to substring check
    if case.expected_categories:
        pred_cat = top_hit.get("category") or top_hit.get("service_name") or ""
        top_category_ok = any(
            category_matches(pred_cat, exp) or category_matches(top_hit.get("service_name", ""), exp)
            for exp in case.expected_categories
        )
        if not top_category_ok:
            top_category_ok = contains_any(top_text, case.expected_categories)
    else:
        top_category_ok = True
    top_keyword_ok = contains_any(top_text, case.expected_keywords)
    any_keyword_ok = any(contains_any(text, case.expected_keywords) for text in hit_texts)
    schema_ok = any(any(hint in text for hint in schema_hints) for text in hit_texts) if schema_hints else True

    passed = bool(hits) and (top_keyword_ok or (top_category_ok and any_keyword_ok)) and schema_ok

    return {
        "category": case.category,
        "question": case.question,
        "notes": case.notes,
        "expected_categories": case.expected_categories,
        "expected_keywords": case.expected_keywords,
        "elapsed_ms": elapsed_ms,
        "hit_count": len(hits),
        "passed": passed,
        "ignored": case.category in IGNORED_CATEGORIES,
        "checks": {
            "top_category_ok": top_category_ok,
            "top_keyword_ok": top_keyword_ok,
            "any_keyword_ok": any_keyword_ok,
            "schema_ok": schema_ok,
        },
        "top_hit": normalize_hit(top_hit) if top_hit else None,
        "hits": [normalize_hit(hit) for hit in hits],
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    effective_results = [row for row in results if not row.get("ignored")]
    by_category: dict[str, dict[str, int]] = {}
    for row in effective_results:
        bucket = by_category.setdefault(row["category"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += int(bool(row["passed"]))

    failed_cases = [
        {
            "category": row["category"],
            "question": row["question"],
            "top_hit": row["top_hit"],
            "checks": row["checks"],
        }
        for row in effective_results
        if not row["passed"]
    ]

    passed_cases = sum(int(bool(r["passed"])) for r in effective_results)
    ignored_cases = [row for row in results if row.get("ignored")]
    return {
        "collection": DEFAULT_COLLECTION,
        "top_k": TOP_K,
        "total_cases": len(effective_results),
        "passed_cases": passed_cases,
        "failed_cases": len(failed_cases),
        "ignored_cases": len(ignored_cases),
        "pass_rate": round(passed_cases / len(effective_results) * 100, 2) if effective_results else 0.0,
        "categories": by_category,
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
    print("检索质量测试完成")
    print("-" * 72)
    print(f"collection : {summary['collection']}")
    print(f"total      : {summary['total_cases']}")
    print(f"passed     : {summary['passed_cases']}")
    print(f"failed     : {summary['failed_cases']}")
    print(f"ignored    : {summary['ignored_cases']}")
    print(f"pass_rate  : {summary['pass_rate']}%")
    print(f"output     : {OUTPUT_PATH}")
    print("-" * 72)
    for category, stats in summary["categories"].items():
        print(f"{category:<12} {stats['passed']}/{stats['total']}")
    print("=" * 72)


if __name__ == "__main__":
    main()
