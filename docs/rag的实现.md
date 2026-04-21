**概览**  
- **目标**: 把已通过测试的 RAG 管道工程化、可重复部署并易运维。  
- **核心思路**: 将整个流程拆成可独立部署的阶段（ingest → chunk → embed → index → retrieve → rerank → generate），每阶段定义清晰接口、批处理/流式两套路径、并加自动化测试与监控。

**关键组件**  
- **Ingest**: 文档接入、格式检测、元数据化。  
- **Chunker**: 语义分块、重组、保留原位置信息。  
- **Embedder**: 批量/异步计算向量并归一化。  
- **Vector Store**: ANN 索引 + 元数据过滤（支持 hybrid）。  
- **Retriever**: 候选召回（ANN/BM25 混合），去重与合并策略。  
- **Reranker**: Cross-encoder 或 light-weight scorer 精排。  
- **Context Builder**: 按 token budget 汇总片段并注入来源。  
- **Generator**: LLM 调用层（带流、速率限制、降重指令）。  
- **监控/评估**: 自动指标、回归测试、人工打分流。  

**实施细则（How to do）**

- **A. 数据接入与解析**  
  - **搭建入口**: 实现一个可复用的 `ingest` 接口（支持文件、URL、数据库、Webhook）。  
  - **格式识别**: 用工具链（Tika/pdfminer/Office parser/自定义 JSON 解析器）先做 content extraction，再做 schema detector。  
  - **标准化输出**: 统一为 Document JSON：{doc_id, src, title, lang, created_at, raw_text, source_uri, metadata}，并写入原始存储（S3/FS/DB）用于可追溯性。  
  - **实践要点**: 把解析失败记录到错误队列，保证可重试并保持幂等性（用 doc checksum 做幂等键）。

- **B. 文本分块（Chunking）**  
  - **怎么做**: 先做语言/句子分割，再按 token（或字符）窗口滑动切分，保留 overlap。  
  - **参数建议**: chunk 目标 200–500 tokens，overlap 50–150 tokens；对短句文档可减少 overlap。  
  - **元数据**: 每 chunk 保存 {doc_id, chunk_id, start_offset, end_offset, page_no, section}。  
  - **验证**: 写单元测试验证 chunk 数量、边界、拼接后等于原文（允许少量 trim）。

- **C. 嵌入计算（Embeddings）**  
  - **接口设计**: Embedding 服务暴露批量接口：embed(texts[]) → vectors[]，支持 sync/async（消息队列）两模式。  
  - **批次与并发**: batch_size 32–256（根据 GPU/CPU/带宽），并发 worker 数根据 QPS 调整。  
  - **归一化与去重**: 计算后做 L2 归一化（如向量库需要），并用快速哈希过滤重复文本。  
  - **重试与降级**: 失败时写 error queue 并自动重试，遇到 API 限流可降级到 cheaper model 并打标。

- **D. 向量存储与索引**  
  - **选型与部署**: POC 可用 FAISS（磁盘/内存），生产优先 Milvus/Weaviate/RedisVector/Pinecone。  
  - **索引构建**: 对大规模使用 HNSW/IVF+PQ，调参示例：HNSW M=16, efConstruction=200；查询 efSearch=100–512。  
  - **元数据过滤**: 为支持 filter（如分公司、产品线），把 metadata 保存在向量索引支持的字段或并行的文档 DB（elasticsearch）中。  
  - **Hybrid 支持**: 若需要精确 recall，把 BM25（Elastic）作为候选来源并与 ANN 合并。

- **E. 检索策略（召回层）**  
  - **两阶段召回**: Stage1 候选（ANN topK + BM25 topK）；Stage2 重排序（cross-encoder）。  
  - **合并与去重**: 合并候选并按 score normalize；按 doc_id 去重并保留最高得分 chunk。  
  - **参数示例**: stage1 candidate K=100，stage2 rerank topN=50，最终上下文选 topM=3–8（受 token 限制）。  
  - **降级策略**: 当 ANN 慢或不可用时，用 BM25 fallback；若两者均低置信度，返回“未找到”或触发扩展检索（FAQ、KB）。

- **F. 精排（Reranker）与可信度**  
  - **实现方式**: 使用 cross-encoder 或轻量的神经 reranker 对 (query, passage) 评分并重排。  
  - **训练/微调**: 若有标注数据，可微调 reranker；无标注时使用 off-the-shelf cross-encoder。  
  - **如何落地**: 批量构造 pairs→调用 reranker→合并score→按 score 降序取前 N。  
  - **可信度阈值**: 给出置信度阈值，当 top score 低于阈值，触发“无法回答”或人工转接。

- **G. 上下文构建与 Prompt 工程**  
  - **拼接规则**: 按 reranker 排序拼接 passage，同时插入来源标注（标题+段落号/页码）。  
  - **token 预算管理**: 计算模型上下文窗口，预留生成所需 tokens，采用先填充高相关片段再加入次相关的方式。  
  - **防止幻觉**: 在 prompt 中明确要求模型“只基于下列片段作答，并在引用处标注来源；若无法回答则说明无法从提供信息推断”。  
  - **模板化**: 把 prompt 模板化（system + instruction + contexts + user query），并把模板版本化便于回滚。

- **H. 生成模型调用（LLM 层）**  
  - **接口封装**: 封装 LLM 调用层，支持 streaming、token-level 控制、重试、限流、并发池。  
  - **速率控制**: 使用队列与 concurrency limiter，设置并发上限 + 每分钟请求限额。  
  - **输出后处理**: 强制模型返回带来源段落的答案并把来源 ID、confidence、score 一并返回给上层。  
  - **降责设计**: 对敏感/高风险问题加二次验证（再调用 reranker 或人工审核）。

- **I. 评估与回归测试**  
  - **自动化指标**: 实现 recall@K、MRR、NDCG、precision of cited source、latency（各阶段），并记录 per-query 结果。  
  - **离线测试集**: 建立带 gold passage 的测试集，写 CI 测试在每次变更时跑（阈值下降触发阻断）。  
  - **人工评估**: 定期抽样人工打分答复质量/准确性/来源正确率，保持打分流程与数据留存。  
  - **回归流程**: 在模型/索引更新前做 A/B 或 canary，对比核心指标并自动回滚策略。

- **J. 监控、日志与运维**  
  - **打点字段**: 每次查询记录：query_id, timings（ingest/embed/retrieve/rerank/generate）、candidate_ids、scores、final_sources、error_codes。  
  - **指标系统**: 导入 Prometheus + Grafana，设定 SLO（p95 latency, error rate）与告警（高延迟、低 recall、embedding errors）。  
  - **运行手册**: 编写 runbook：索引重建步骤、磁盘扩容、热点缓解、API key 轮换流程。  
  - **成本控制**: 监控 embedding API 与生成 API 消耗，分离 hot/cold 数据以降低热数据成本。

- **K. 索引更新策略（增量 & 全量）**  
  - **增量流程**: 记录 doc-level change set（create/update/delete），对变更文档只重新 chunk→embed→upsert 到向量库。  
  - **冷重建**: 定期做 full rebuild（例如 schema 变更、embedding 模型切换），使用原子切换（build 新 index → 切流量 → 删除旧 index）。  
  - **一致性保证**: 在写入向量库前先写入变更日志，确保可回放与幂等重做。

- **L. 安全、隐私与合规**  
  - **PII 检测**: 在 ingest 前做 PII 检测/脱敏策略，记录脱敏策略与审计日志。  
  - **权限控制**: 向量库与生成 API 做 RBAC，敏感源加字段级 ACL。  
  - **数据保留**: 定义索引数据保留策略与删除流程（支持 GDPR 删除链路）。

