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

- 本次入库统计：**14 文件、154 条向量、0 错误**。
- 当前采用 **统一集合**：`aia_knowledge_base`。
- 其中已统计到：
  - `service_categories` 8 文件共 `43` 条
  - `分公司页面.json` `13` 条
  - `个险+团险产品.json` `11` 条
  - `个险-推荐产品.json` `60` 条
  - `分公司新闻.json` `22` 条
  - `反保险欺诈提示及举报渠道.txt` `5` 条
- `团险-推荐产品.json` 在报告中显示 `0` 条，需在后续优化中继续校验 schema 适配逻辑。

---

## 五、Qdrant 设计（已按当前实现修正）

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

- 状态：✅ 已完成（当前批次）
- 执行脚本：`python scripts/run_ingest_all.py`
- 验收结果：`14 文件 / 154 向量 / 0 错误`
- 待跟进项：`团险-推荐产品.json` 当前 doc 数为 `0`，需进一步确认 flatten 规则。

### Phase 2：检索质量优化（当前重点）


| 步骤  | 操作                                | 预期收益      |
| --- | --------------------------------- | --------- |
| 2-1 | 调整 `TOP_K`（3→5）并评估延迟              | 提升召回覆盖率   |
| 2-2 | 增加低分过滤（如 `<0.5` 不注入）              | 降低噪声      |
| 2-3 | 基于 `schema/source_file` 增加检索过滤策略  | 提升命中准确率   |
| 2-4 | 对“在售产品”查询增加 `productStatus=在售` 约束 | 避免推荐非在售产品 |
| 2-5 | 补齐 `团险-推荐产品` 的入库映射                | 提升团险问答覆盖  |


验收标准：20 条典型问题 Top-1 准确率 ≥ 85%。

### Phase 3：多轮对话能力

- 状态：⏳ 待开始
- 目标：上下文指代正确率 ≥ 90%。

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

## 九、备注

- 本文档已按当前 `aia_data/` 实际文件与入库报告同步修订。
- 如后续新增数据文件（如 PDF 批量资料、FAQ 扩展集），请同步更新本页“第四章数据现状”与“第七章路线图”。

