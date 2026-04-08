# AIA Robot 智能体构建计划

> **文档版本**: v3.1  
> **更新日期**: 2026-04-01  
> **当前阶段**: `aia_data` 数据已对齐 → 统一集合入库完成（待检索质量优化）

---

## 一、项目概览

AIA Robot 是面向友邦保险（AIA）用户的 RAG（检索增强生成）智能客服智能体。用户输入保险相关问题后，系统通过向量检索从本地知识库召回最相关内容，并结合 LLM 生成中文回答。

### 核心目标


| 目标       | 说明                                    |
| -------- | ------------------------------------- |
| **低延迟**  | 使用本地 Docker Qdrant，降低网络 RTT，提升检索速度    |
| **高精度**  | 基于 `BAAI/bge-small-zh-v1.5` 做中文语义向量检索 |
| **数据完整** | 覆盖 `aia_data/` 当前全部核心数据文件             |
| **可扩展**  | 支持后续接入 PDF 文档、更多模型与多轮对话优化             |


---

## 二、当前项目结构（按实际目录更新）

```text
aia_robot/
├── aia_data/
│   ├── service_categories/          # 8 个保单服务分类 JSON
│   │   ├── 保单服务.json
│   │   ├── 保险计划变更.json
│   │   ├── 合同.json
│   │   ├── 借款.json
│   │   ├── 年金.json
│   │   ├── 退保.json
│   │   ├── 万能险.json
│   │   └── 续期及账户管理.json
│   ├── 表单下载-个险.json
│   ├── 表单下载-团险.json
│   ├── 客户服务菜单.json
│   ├── 在售产品基本信息.json
│   ├── 个险+团险产品.json
│   ├── 个险-推荐产品.json
│   ├── 团险-推荐产品.json
│   ├── 分公司页面.json
│   ├── 分公司新闻.json
│   └── 反保险欺诈提示及举报渠道.txt
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── cache.py
│   ├── session.py
│   ├── chat/index.py
│   ├── cluster/index.py
│   ├── knowledge_base/
│   │   ├── rag.py
│   │   ├── build.py
│   │   ├── ingest.py
│   │   ├── pdf_parser.py
│   │   └── storage.py
│   └── routers/
│       ├── auth.py
│       ├── chat.py
│       └── knowledge.py
├── scripts/
│   ├── preprocess_service_categories.py
│   └── run_ingest_all.py            # 统一入库脚本
├── docs/
│   ├── index.md
│   └── 数据导入报告.txt
├── requirements.txt
└── start.ps1
```

---

## 三、技术架构

```text
用户输入
   |
   v
[FastAPI 后端]  POST /chat
   |
   |---> [Redis 缓存层] 命中则直接返回
   |
   v
[RAG 检索引擎 - app/knowledge_base/rag.py]
   |
   |---> [SentenceTransformer] BAAI/bge-small-zh-v1.5
   |       encode(query) -> 512 维向量
   |
   |---> [本地 Qdrant - Docker :6333]
   |       在 `aia_knowledge_base` 中检索 Top-K
   |
   v
[LLM - SiliconFlow API]
   |
   v
[流式响应] -> 前端 React 展示
```

### 基础设施组件


| 组件           | 技术选型                        | 用途                  |
| ------------ | --------------------------- | ------------------- |
| 向量数据库        | Qdrant（Docker 本地）           | 存储 embedding，执行语义检索 |
| Embedding 模型 | `BAAI/bge-small-zh-v1.5`    | 中文语义向量化（512 维）      |
| LLM          | SiliconFlow / Hunyuan-MT-7B | 自然语言生成              |
| 关系数据库        | MySQL                       | 用户、会话、历史记录          |
| 缓存           | Redis                       | 高频问答缓存              |
| 对象存储         | MinIO                       | PDF 原文件与解析结果        |
| 后端框架         | FastAPI + Uvicorn           | 异步 API 服务           |
| 前端框架         | React + Vite + TypeScript   | 用户交互界面              |


---

## 四、`aia_data` 数据现状（按当前文件）

### 4.1 文件与结构摘要


| 数据文件                            | 关键字段/结构                                        | 规模概览                 |
| ------------------------------- | ---------------------------------------------- | -------------------- |
| `service_categories/*.json`（8个） | `service_categories[].items[]`                 | 8 个服务子域              |
| `表单下载-个险.json`                  | `items[]`（含 `filename/full_url`）               | `total_items = 13`   |
| `表单下载-团险.json`                  | `items[]`（含 `filename/full_url`）               | `total_items = 23`   |
| `客户服务菜单.json`                   | `items[]`（`title/url/text`）                    | `total_items = 26`   |
| `分公司页面.json`                    | `regions[]`                                    | `total_regions = 13` |
| `分公司新闻.json`                    | `regions[].news_items[]`                       | `6` 区域，新闻约 `22` 条    |
| `个险+团险产品.json`                  | `personal_insurance_menu/group_insurance_menu` | 个险 9 类 + 团险 2 类      |
| `个险-推荐产品.json`                  | `personal_insurance_recommended_products`      | 多类别推荐产品              |
| `团险-推荐产品.json`                  | `group_insurance_recommended_products`         | 团险推荐产品               |
| `在售产品基本信息.json`                 | `on_sale_products_list[]`                      | 在售产品清单               |
| `反保险欺诈提示及举报渠道.txt`              | 反欺诈说明文本                                        | 纯文本分块入库              |


### 4.2 当前入库结果（参考 `docs/数据导入报告.txt`）

- 当前主集合：`aia_knowledge_base`
- 全量入库（`run_ingest_all.py`）结果：**15 文件、358 条向量、0 错误**
- Collection 校验：`aia_knowledge_base = 358 points`

分项统计（全量阶段）：
- `service_categories`：43
- `branches`（分公司页面 + 分公司新闻）：35（13 + 22）
- `products_page`：11
- `个险-推荐产品`：60
- `团险-推荐产品`：9
- `products_list`（在售产品）：195
- `text`（反欺诈）：5

表单重处理阶段（`reprocess_form_downloads.py`）：
- `表单下载-个险.json`：`forms_markdown` 86 chunks，失败 3
- `表单下载-团险.json`：`forms_markdown` 164 chunks，失败 1
- 说明：表单数据采用“清理旧数据 + 重建”策略，最终以最近一次重处理结果为准。

---

## 五、Qdrant 设计

> 现阶段不是“多 collection 拆分”，而是**统一写入单集合**。

### 5.1 集合策略

- 集合名：`aia_knowledge_base`
- 写入脚本：`scripts/run_ingest_all.py`
- 核心方式：不同来源通过 payload 字段（如 `schema`、`source_file`、`service_name`）区分，检索时再做过滤/排序。

### 5.2 Embedding 参数


| 参数     | 值                        | 说明             |
| ------ | ------------------------ | -------------- |
| 模型     | `BAAI/bge-small-zh-v1.5` | 中文检索主模型        |
| 向量维度   | 512                      | 固定输出维度         |
| 相似度类型  | Cosine                   | 归一化后余弦相似度      |
| 文本分块大小 | 600 字符                   | 长文本（txt/PDF）分块 |
| 分块重叠   | 80 字符                    | 保持上下文连续性       |


---

## 六、业务数据库

> 目标：避免与向量库重复存储知识正文，业务库仅存“元数据 + 业务状态 + 可追踪信息”。

### 6.1 设计原则

- 向量库（Qdrant）负责：知识正文 chunk、向量、语义检索。
- 业务库（MySQL）负责：知识入库记录、用户与会话、日志与追踪。
- 不在 MySQL 重复存储 `aia_data` 的完整正文内容。

### 6.2 业务数据库三类数据

#### 1）知识库（元数据）

建议存储：

- 数据源清单：`source_file`、`schema`、`content_hash`、`enabled`
- 入库任务：开始/结束时间、成功数、失败数、错误摘要
- 向量引用：`collection_name`、`point_count`、版本号（可选）

建议表（示例）：

- `kb_dataset`
- `kb_ingest_job`
- `kb_ingest_job_item`

#### 2）用户

建议存储：

- 用户主数据：账号、角色、状态、最后登录时间
- 会话主数据：`session_id`、用户 ID、创建时间、会话状态
- 对话消息：用户问题、模型回答、时间戳、消息类型
- 反馈：点赞/点踩、问题标注、人工修正建议

建议表（示例）：

- `user`
- `chat_session`
- `chat_message`
- `chat_feedback`

#### 3）日志

建议存储：

- 检索日志：query、命中条数、TopK、耗时、最高分
- 生成日志：模型名、token 使用、首 token 时延、总耗时
- 链路追踪：一次问答关联的 `session_id/request_id`、命中文档引用（point id）
- 异常日志：错误码、错误堆栈摘要、发生模块

建议表（示例）：

- `retrieval_log`
- `generation_log`
- `chat_trace`
- `error_log`

### 6.3 与向量库的边界

- MySQL 存“可管理、可统计、可审计”的业务数据。
- Qdrant 存“可检索”的知识向量数据。
- 两者通过 `source_file/content_hash/point_id` 建立引用，不重复保存正文。

---

## 七、构建阶段路线图（结合当前状态）

### Phase 0：本地 Qdrant 环境

- 状态：✅ 已完成
- 结果：本地 Qdrant 可用，已支撑统一集合入库。

### Phase 1：全量数据入库

- 状态：✅ 已完成（最新批次）
- 执行脚本：`python scripts/run_ingest_all.py`
- 验收结果：`15 文件 / 358 向量 / 0 错误`
- Collection 结果：`aia_knowledge_base = 358 points`
- 说明：`团险-推荐产品` 已补齐入库（9 条）。

### Phase 2：检索质量优化（当前重点）


| 步骤  | 操作                                                           | 预期收益           |
| --- | ------------------------------------------------------------ | -------------- |
| 2-1 | 调整 `TOP_K`（3→5）并评估延迟                                         | 提升召回覆盖率        |
| 2-2 | 增加低分过滤（如 `<0.5` 不注入）                                         | 降低噪声           |
| 2-3 | 基于 `schema/source_file` 增加检索过滤策略                             | 提升命中准确率        |
| 2-4 | 对“在售产品”查询增加 `productStatus=在售` 约束                        | 避免推荐非在售产品      |
| 2-5 | 表单知识（`forms_markdown`）接入在线检索与兜底策略                     | 提升保全/理赔场景覆盖    |
| 2-6 | 将 `rag.py` 拆分为检索数据源模块、意图规则模块、首层意图识别模块          | 降低耦合，便于迭代测试   |
| 2-7 | 建立 `scripts/evaluate_intent_quality.py`，覆盖 9 类意图共 27 条用例 | 建立首层意图识别基线    |
| 2-8 | 首层意图识别增加 `confidence / candidates / needs_confirmation` | 为低置信双路召回做准备 |
| 2-9 | 下一阶段采用方案 A：高置信单路检索，低置信 Top2 双路检索               | 提升边界 query 稳定性 |


验收标准：20 条典型问题 Top-1 准确率 ≥ 85%。

#### Phase 2 当前补充进展（2026-04-06）

已完成：
- `app/knowledge_base/retrieval_data_source.py`：统一管理 Qdrant client、embedding model、filter 与底层 query。
- `app/knowledge_base/intent_rules.py`：统一管理 `RetrievalIntent`、意图词典、bonus 规则与 query 归一化。
- `app/knowledge_base/intent_recognition.py`：实现首层意图识别，并支持候选意图、置信度、澄清标记输出。
- `app/knowledge_base/rag.py`：已完成第一轮模块化接线，保留检索主流程与上下文构建流程。
- `scripts/evaluate_intent_quality.py`：已建立首层意图识别评测脚本，并输出 `docs/意图识别测试结果.json`。

当前结果：
- 首层意图识别测试集：9 类意图、27 条样例。
- 本地评测结果：通过率 `100%`。
- 当前评测已可输出：预测意图、Top 候选、置信度、是否需要澄清。

下一步（方案 A）：
- 在 `retrieve()` 中接入首层意图识别结果。
- 高置信 query：按第一候选意图做单路过滤检索。
- 低置信 query：按前两名候选意图做 Top2 双路检索并合并去重。
- 极低置信或双路无结果：回退全库检索，必要时为后续追问机制预留接口。

#### Phase 2 当前补充进展（2026-04-07）

已完成：
- `app/knowledge_base/retrieval_data_source.py`：统一管理 Qdrant client、embedding model、filter 与底层 query。
- `app/knowledge_base/intent_rules.py`：统一管理 `RetrievalIntent`、意图词典、bonus 规则与 query 归一化。
- `app/knowledge_base/intent_recognition.py`：实现首层意图识别，并支持候选意图、置信度、澄清标记输出。
- `app/knowledge_base/rag.py`：已完成第一轮模块化接线，保留检索主流程与上下文构建流程。
- `scripts/evaluate_intent_quality.py`：已建立首层意图识别评测脚本，并输出 `docs/意图识别测试结果.json`。
- `app/knowledge_base/rag.py`：已实现意图驱动的检索路由，包括高置信度单路过滤、中置信度双路检索合并去重、低置信度回退全库检索。

当前结果：
- 首层意图识别测试集：9 类意图、27 条样例。
- 本地评测结果：通过率 `100%`。
- 检索路由策略：高置信度（≥0.7）按意图过滤检索，中置信度（0.5-0.7）双路检索合并，低置信度（<0.5）回退全库检索。
- 当前评测已可输出：预测意图、Top 候选、置信度、是否需要澄清。

已完成方案 A 实现：
- 在 [retrieve()](file://e:\aia_robot\app\knowledge_base\rag.py#L26-L97) 中接入首层意图识别结果。
- 高置信 query：按第一候选意图做单路过滤检索。
- 中置信 query：按前两名候选意图做 Top2 双路检索（filtered + unfiltered）并合并去重。
- 低置信或双路无结果：回退全库检索。

测试：
1. 意图识别准确性测试
运行 scripts/evaluate_intent_quality.py 验证意图分类准确性
验证27个测试用例，确保意图识别准确率达到95%以上
检查置信度阈值（高≥0.7、中0.5-0.7、低<0.5）的正确应用

```powershell
========================================================================
意图识别测试完成
------------------------------------------------------------------------
total      : 27
passed     : 27
failed     : 0
pass_rate  : 100.0%
avg_conf   : 0.9098
need_clarify: 1
output     : E:\aia_robot\docs\意图识别测试结果.json
------------------------------------------------------------------------
service_guide        3/3 avg_conf=0.9231 clarify=0
form                 3/3 avg_conf=0.8968 clarify=0
branch               3/3 avg_conf=1.0 clarify=0
branch_news          3/3 avg_conf=0.7024 clarify=1
product_category     3/3 avg_conf=1.0 clarify=0
recommended_product  3/3 avg_conf=0.9213 clarify=0
on_sale_product      3/3 avg_conf=0.8783 clarify=0
menu                 3/3 avg_conf=0.8667 clarify=0
anti_fraud           3/3 avg_conf=1.0 clarify=0
========================================================================
```

2. 检索质量测试
运行 scripts/evaluate_retrieval_quality.py 验证检索结果相关性
验证48个业务场景测试用例，确保Top-1准确率达到85%以上
验证不同业务领域（保单服务、产品、表单等）的检索准确性

```powershell

```
3. 意图路由逻辑测试
验证高置信度查询的单路过滤检索
验证中置信度查询的双路检索合并去重
验证低置信度查询的全库检索回退机制
验证无结果时的回退机制是否正常工作
4. 核心功能验证
验证 retrieve() 函数的完整工作流程
验证 _merge_and_deduplicate() 结果合并去重功能
验证 build_rag_context() 上下文构建功能
验证 rag_query() 端到端查询功能
5. 单元测试执行
运行 tests/test_rag_intent_routing.py 验证各模块单元功能
确保所有单元测试通过，验证各组件功能正常
6. 执行顺序
运行单元测试验证基础功能
执行意图质量评估
执行检索质量评估
检查生成的JSON结果文件确认各项指标达标

### Phase 3：多轮对话能力

- 状态：⏳ 待开始
- 目标：上下文指代正确率 ≥ 90%。

增强查询重写功能：在_rewrite_query_with_history函数中加入更复杂的上下文理解
实现分层记忆：将短期对话历史与长期知识分离
优化Token使用：实现滑动窗口和摘要机制，控制上下文长度
上下文检索增强：利用历史对话优化向量检索质量

必须有 Context Manager：实现专门的上下文管理模块
Tool 输出必须压缩：对工具调用结果进行过滤和摘要
Memory 必须检索：实现精准的记忆检索机制
定期总结：定期对对话历史进行摘要
Context Ranking：对上下文信息进行重要性排序

### Phase 4：性能基准

- 状态：⏳ 待开始
- 目标：Qdrant 检索 P99 < 150ms；端到端无缓存 P50 < 4s。

### Phase 5：前端联调与端到端验收

- 状态：⏳ 待开始
- 目标：覆盖核心数据域问题，10 条冒烟问题全部可返回有效答案。

---

## 八、当前进度总览


| 阶段                | 状态  | 完成度  |
| ----------------- | --- | ---- |
| 数据清洗              | 完成  | 100% |
| 后端框架搭建            | 完成  | 100% |
| 前端框架搭建            | 完成  | 100% |
| RAG 基础检索          | 完成  | 100% |
| Phase 0：本地 Qdrant | 完成  | 100% |
| Phase 1：全量数据入库    | 完成  | 100% |
| Phase 2：检索质量优化    | 进行中 | 20%  |
| Phase 3：多轮对话能力    | 待开始 | 0%   |
| Phase 4：性能基准测试    | 待开始 | 0%   |
| Phase 5：前端端到端验收   | 待开始 | 0%   |


---

## 九、知识库业务闭环实施方案

目标：从“单次检索问答”升级为“检索 → 推荐 → 需求识别 → 线索转化 → 持续运营”的闭环能力，并保证全流程合理合法、可审计。

### 9.1 分层能力架构

1. 检索层（已具备）
- 入口：`app/knowledge_base/rag.py`
- 数据：`aia_knowledge_base`
- 能力：语义召回 + source/schema 过滤 + 证据片段返回

2. 推荐层（下一步）
- 在检索结果上做“场景推荐”：保全、理赔、续期、产品、网点、反欺诈
- 输出结构：`推荐项 + 原因 + 依据文档 + 下一步动作`
- 示例动作：下载表单、准备资料、联系分公司、在线办理入口

3. 需求识别层（关键）
- 意图识别：咨询/办理/投诉/风险提示/购买意向
- 槽位抽取：险种、地区、保单状态、时间、预算、家庭结构
- 状态机：未识别 → 部分识别 → 信息充分 → 可执行推荐

4. 运营转化层（闭环）
- 当用户意向达到阈值时触发“线索创建”
- 将线索写入 CRM 或内部跟进系统（用户授权后）
- 跟进结果回流到知识库评估体系（不回写敏感正文）

### 9.2 端到端业务闭环流程

- Step 1：用户问题进入会话，先做意图分类与风险分级。
- Step 2：按意图选择检索策略（schema/source_file/filter）。
- Step 3：生成“答案 + 推荐动作 + 证据引用 + 风险提示”。
- Step 4：若识别为高价值意向，弹出授权确认（联系方式/回访许可）。
- Step 5：授权后写入线索系统并分配顾问，形成服务工单。
- Step 6：跟进结果（是否转化、失败原因）回流分析，持续优化检索和推荐策略。

### 9.3 可落地功能清单（按优先级）

P0（2~3 周）
- 检索结果结构化返回：答案、引用片段、来源文件、置信度
- 会话意图识别与槽位抽取（规则 + 轻模型）
- 推荐卡片组件：办理入口、所需材料、附近网点、风险提醒
- 人工兜底：低置信度自动转人工 （设计暂时的人工客服接口，后续再集成）

P1（3~6 周）
- 线索评分模型（行为分 + 语义分 + 时效分）
- 客群分层推荐（个人险/团险/续保/理赔）
- A/B 测试框架（推荐策略、TopK、阈值）
- 召回质量看板（准确率、覆盖率、拒答率、转人工率）

P2（持续）
- 多智能体协同：客服 Agent、产品推荐 Agent、合规审查 Agent
- 自动运营编排：定时触达、续期提醒、材料补齐提醒
- 全链路优化：从“问答满意度”升级到“业务转化率 + 合规通过率”

### 9.4 合规与风控基线（必须）

1. 个人信息保护
- 默认最小化采集，仅在必要场景收集联系方式
- 明示用途、保存期限、撤回机制
- 敏感字段脱敏存储与传输加密

2. 金融营销合规
- 推荐内容必须附带“非承诺收益/以条款为准”提示
- 禁止夸大宣传、误导销售、替代人工核保结论
- 高风险问题（理赔争议、反洗钱、投诉）优先转人工

3. 可审计与可追溯
- 保留检索证据链：query、命中文档、版本、时间戳
- 保留推荐决策链：触发规则、阈值、输出内容
- 保留用户授权记录：授权时间、范围、操作人/系统

### 9.5 核心指标（建议纳入周报）

- 检索质量：Top1/Top3 命中率、低分拒答率
- 服务质量：首响时延、会话完成率、转人工率
- 业务价值：推荐点击率、线索转化率、续保转化率
- 合规质量：违规触发率、授权完整率、审计可追溯率

---

## 十、备注

- 本文档已按当前 `aia_data/` 实际文件与入库报告同步修订。
- 如后续新增数据文件（如 PDF 批量资料、FAQ 扩展集），请同步更新本页“第四章数据现状”与“第七章路线图”。

