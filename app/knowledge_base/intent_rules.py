from __future__ import annotations

import re
from dataclasses import dataclass

OFFICIAL_BASE_URL = "https://www.aia.com.cn"


@dataclass(frozen=True)
class RetrievalIntent:
    key: str
    name: str
    schemas: tuple[str, ...]
    categories: tuple[str, ...] = ()
    only_on_sale: bool = False
    official_url: str = ""


INTENT_RULES: tuple[RetrievalIntent, ...] = (
    RetrievalIntent(key="service_guide", name="服务指南", schemas=("service_categories",), official_url=f"{OFFICIAL_BASE_URL}/zh-cn/fuwu/fuwuzhinan"),
    RetrievalIntent(key="form", name="表单", schemas=("forms_markdown",), categories=("表单下载",), official_url=f"{OFFICIAL_BASE_URL}/zh-cn/fuwu/biaodanxiazai"),
    RetrievalIntent(key="branch_news", name="新闻", schemas=("branches",), categories=("分公司动态",)),
    RetrievalIntent(key="branch", name="分公司", schemas=("branches",), categories=("分公司",), official_url=f"{OFFICIAL_BASE_URL}/zh-cn/fuwu/shanghai"),
    RetrievalIntent(key="product_category", name="产品分类", schemas=("products_page",), categories=("个险产品", "团险产品")),
    RetrievalIntent(key="recommended_product", name="推荐产品", schemas=("recommended_products",), categories=("个险推荐产品", "团险推荐产品")),
    RetrievalIntent(key="on_sale_product", name="在售产品", schemas=("products_list",), categories=("在售产品",), only_on_sale=True),
    RetrievalIntent(key="menu", name="菜单导航", schemas=("menu",), categories=("客户服务导航",), official_url=f"{OFFICIAL_BASE_URL}/zh-cn/fuwu"),
    RetrievalIntent(key="anti_fraud", name="反欺诈", schemas=("text",), categories=("反欺诈",), official_url=f"{OFFICIAL_BASE_URL}/zh-cn/fuwu/fanbaoxianqizha"),
)

INTENT_MAP: dict[str, RetrievalIntent] = {intent.key: intent for intent in INTENT_RULES}

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "service_guide": ("服务指南", "怎么办", "如何办理", "怎么申请", "申请材料", "办理方式", "客户服务中心", "友邦友享", "投保人", "受益人", "变更", "退保", "借款", "年金", "联系方式", "联系电话", "通讯地址", "年缴", "月缴", "缴费方式"),
    "form": ("表单", "申请书", "授权委托书", "下载", "附件", "理赔申请书", "给付申请书", "pdf"),
    "branch_news": ("新闻", "活动", "发布", "讲座", "庆典", "训练营", "宣传日", "公益", "升级改建", "落幕", "启幕"),
    "branch": ("分公司", "客服电话", "电话", "地址", "营业时间", "服务时间", "信访", "接待日", "网点", "北京", "上海", "广东", "安徽", "天津", "河北", "四川", "湖北", "浙江"),
    "product_category": ("产品分类", "个险", "团险", "疾病保障", "意外/医疗", "寿险保障", "享老保障", "财富管理", "护理保障", "教育储备", "员工企业福利", "员工自选加保"),
    "recommended_product": ("推荐产品", "适合", "有没有", "组合计划", "智享组合计划", "优享组合计划", "尊享组合计划", "长保康惠", "友童", "儿童", "高端医疗", "中端医疗"),
    "on_sale_product": ("在售", "产品说明书", "费率表", "现金价值表", "产品组", "停售", "productgroup", "条款", "followupservice"),
    "menu": ("入口", "菜单", "导航", "从哪里进入", "去哪", "官网入口", "常见问题入口", "理赔服务页面", "表单下载入口"),
    "anti_fraud": ("反欺诈", "保险欺诈", "举报", "举报邮箱", "举报渠道", "欺诈", "虚构", "骗保", "刑事责任", "民事责任", "行政责任"),
}

INTENT_BONUS_RULES: tuple[tuple[str, tuple[str, ...], int], ...] = (
    ("branch_news", ("新闻", "活动", "讲座", "庆典", "公益", "训练营"), 3),
    ("menu", ("入口", "从哪里进入", "导航", "官网入口"), 5),
    ("form", ("下载", "申请书", "授权委托书", "表单"), 4),
    ("service_guide", ("联系方式", "联系电话", "通讯地址", "缴费方式", "年缴", "月缴"), 6),
    ("on_sale_product", ("在售", "产品说明书", "费率表", "现金价值表", "产品组"), 5),
    ("anti_fraud", ("举报", "欺诈", "骗保", "反保险"), 6),
)


def normalize_query_text(query: str) -> str:
    return re.sub(r"\s+", "", query).lower()
