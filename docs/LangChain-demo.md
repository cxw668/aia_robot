步骤（我将按此顺序说明）  
1. 阅读并理解脚本（已完成）。  
2. 给出总体设计与模块职责。  
3. 说明三种运行模式的数据流与关键实现细节。  
4. 列出潜在问题与改进建议，并提供运行示例。

**总体设计**  
- **目的**: 脚本 langchain_demo.py 分阶段演示把现有自研组件用适配器接入 LangChain（RAG）并通过 LangGraph 实现简单 Agent（planner + tool）。  
- **分层思路**: 适配层（封装 embedding/vector/retriever）→ RAG Chain（检索上下文 + prompt → LLM）→ Agent（planner 决策 → 调用工具检索 → 最终回答）。

**模块职责**  
- **适配层**: `EmbeddingsAdapter` / `VectorStoreAdapter` / `RetrieverAdapter`（来自 langchain_adapters.py）— 把本地 embedding/向量/检索包装成 LangChain-friendly 接口。  
- **LLM 封装**: `AIAChatModel`（来自 lc_components.py）— 抽象具体 chat/生成调用。  
- **演示入口**: `run_adapter_demo` / `run_rag_demo` / `run_agent_demo`：分别展示 adapter、RAG chain、Agent。  
- **Agent 状态机**: `build_agent_app` 用 `StateGraph` 定义 planner/tool/finalize 节点并编译为可调用 runnable。  
- **解析与健壮性**: `_extract_json_block`、`_parse_agent_decision` 对模型输出做 JSON 提取与容错解析。  
- **结构化输出模型**: `AgentDecision`（Pydantic）用于约束 planner 输出格式。

**三种运行模式的数据流（高层）**  
- **Adapter**: Query → `EmbeddingsAdapter.embed_query` → `VectorStoreAdapter.search` / `RetrieverAdapter.retrieve` → 打印 hits / 调用 legacy `retr.rag_query`。  
- **RAG Chain**: Query → `fast_search`（embeddings + vector_store.search）→ `_format_hit_records` → `ChatPromptTemplate` → `AIAChatModel` → `StrOutputParser()`（纯文本答案）。  
- **Agent**: 初始 state → `planner`（prompt + `AIAChatModel`）产出 JSON 决策 → 若为 `search_kb` 则调用 `search_kb` 工具（emb+vector search）并把结果 append 到 `scratchpad` → 重新 planner（可多轮，受 `max_steps` 限制）→ `finalize` 用 answer prompt 生成最终答案。

**关键实现细节 & 要点**  
- **LangChain Core 组合**: 使用 `RunnableLambda` 将同步函数（`fast_search` / `_format_hit_records`）接入 runnable pipeline；`RunnablePassthrough` 负责传递问题参数。  
- **Prompt 设计**: 用 `ChatPromptTemplate.from_messages` 明确 system/human role；在 planner prompt 中插入 `decision_parser.get_format_instructions()` 强化输出格式约束。  
- **输出解析容错**: `_extract_json_block` 实现逐字符匹配 JSON 花括号并支持 ```json ``` fenced block；`_parse_agent_decision` 在解析失败时有降级策略（plain text → final_answer 或重试检索）。  
- **Pydantic v2 风格**: 使用 `AgentDecision.model_validate(...)` 与 `decision.model_dump()`，代码假定 Pydantic v2；如环境使用 v1 需适配 `parse_obj`/`dict()`。  
- **LangGraph StateGraph**: 用 `add_conditional_edges` + `route_next` 决定下一节点（planner→tool→planner→finalize），`graph.compile()` 返回可 `invoke` 的 runnable。  
- **工具封装**: `@tool def search_kb(query: str)` 返回 `_format_hit_records` 的字符串，作为 planner 的可用工具。  
- **鲁棒性**: 脚本在很多点做了简要异常/降级处理（如 `run_adapter_demo` 捕获 legacy RAG 异常），但整体对 LLM 超时、外部服务失败的监控较少。  
- **同步/阻塞**: 当前实现全部同步（直接调用 `.invoke()`），在 Async FastAPI 环境需用线程池或 async 适配器避免阻塞事件循环。  
- **上下文长度控制**: RAG 直接把 `top_k` 的检索内容（未做摘要）放入 prompt，可能导致 token 爆炸，需要在生产中做裁剪/摘要。

**潜在问题与改进建议（优先级排序）**  
- **强制结构化与重试**: planner 输出解析失败时最好实现 N 次重试或让模型只输出 JSON（若仍失败，返回明确错误），并记录解析异常以便调试。  
- **超时与并发**: 给 LLM 和向量检索调用增加超时与并发限制；在 FastAPI 中把同步调用包进线程池。  
- **输出可信度与证据引用**: final answer 应附带明确证据引用（point id / source_file / score），并在 prompt 中强制要求引用来源。  
- **文档摘要**: 对检索到的长文本预先做摘要或抽取要点，减少 prompt token 开销并提高一致性。  
- **类型与接口契约**: 明确 `VectorStoreAdapter.search` 返回的对象类型（建议返回 LangChain `Document` 或统一 dict{page_content, metadata}`），并为 adapters 添加单元测试。  
- **监控与指标**: 增加调用链路的日志、耗时、命中数统计与 hallucination 率监控（用于灰度评估）。  
- **安全与合规**: planner/prompt 中应加入合规/敏感信息检测规则以避免模型泄露或生成违规建议。

**测试 & 验证建议**  
- 写单元测试覆盖：`_extract_json_block`、`_parse_agent_decision`、`build_rag_chain`（输入短例）和 agent 的 1-2 个简单流程。  
- 用现有评估脚本对比 legacy 实现与 LangChain RAG 的 Top-K 命中与生成质量（你已有 `scripts/evaluate_retrieval_quality.py`）。

**运行示例**  
```bash
python scripts/langchain_demo.py "我的保单如何退保？" --mode adapter
python scripts/langchain_demo.py "我的保单如何退保？" --mode rag --top-k 5
python scripts/langchain_demo.py "我的保单如何退保？" --mode agent --top-k 3
```

**相关文件**  
- langchain_demo.py — 演示脚本（当前分析对象）  
- langchain_adapters.py — 适配器实现（必须保证返回类型兼容）  
- lc_components.py — `AIAChatModel` 封装 LLM 调用

需要我现在：1) 为关键函数（`_parse_agent_decision` / `_extract_json_block` / agent 流程）写单元测试模板，还是 2) 把上述改进逐项列成可执行 TODO 并生成补丁？请选择其一。