"""LangChain 引入演示脚本。

阶段化演示：
1. adapter: 运行已有自研适配器
2. rag: 使用 LangChain LCEL 构建最小 RAG Chain
3. agent: 使用 LangGraph StateGraph + LangChain Tool 构建工具型 Agent

示例：
    python scripts/langchain_demo.py "我的保单如何退保？"
    python scripts/langchain_demo.py "我的保单如何退保？" --mode rag
    python scripts/langchain_demo.py "我想知道退保流程和办理方式" --mode agent
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from pprint import pprint
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

sys.path.append(str(Path(__file__).parent.parent))

from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from app.knowledge_base.config import DEFAULT_COLLECTION
from app.knowledge_base.langchain_adapters import (
    EmbeddingsAdapter,
    RetrieverAdapter,
    VectorStoreAdapter,
)
from app.knowledge_base.lc_components import AIAChatModel


def _print_section(title: str) -> None:
    print(f"\n== {title} ==")

def _format_documents(docs: list) -> str:
    if not docs:
        return "未检索到相关文档。"

    chunks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        meta = doc.metadata or {}
        title = meta.get("title") or meta.get("service_name") or f"文档{index}"
        score = meta.get("score")
        service_url = meta.get("service_url") or ""
        content = (doc.page_content or "").strip()
        if len(content) > 400:
            content = f"{content[:400]}..."
        header = f"[{index}] {title}"
        if score is not None:
            header = f"{header} | score={score}"
        if service_url:
            header = f"{header} | url={service_url}"
        chunks.append(f"{header}\n{content}")
    return "\n\n".join(chunks)


def _format_hit_records(hits: list[dict]) -> str:
    if not hits:
        return "未检索到相关文档。"

    chunks: list[str] = []
    for index, hit in enumerate(hits, start=1):
        title = hit.get("title") or hit.get("service_name") or f"结果{index}"
        score = hit.get("score")
        service_url = hit.get("service_url") or ""
        content = (hit.get("content") or "").strip()
        if len(content) > 400:
            content = f"{content[:400]}..."
        header = f"[{index}] {title}"
        if score is not None:
            header = f"{header} | score={score}"
        if service_url:
            header = f"{header} | url={service_url}"
        chunks.append(f"{header}\n{content}")
    return "\n\n".join(chunks)


def _extract_json_block(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    fence_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

    raise ValueError("No JSON object found in model output")


def _parse_agent_decision(raw: str, *, question: str, has_observation: bool) -> AgentDecision:
    raw = raw.strip()
    if raw == "null":
        if has_observation:
            return AgentDecision(action="final_answer", final_answer="")
        return AgentDecision(action="search_kb", action_input=question, reasoning="model returned null")

    try:
        payload_text = _extract_json_block(raw)
    except ValueError:
        if has_observation:
            return AgentDecision(action="final_answer", final_answer=raw)
        return AgentDecision(action="search_kb", action_input=question, reasoning="planner returned plain text")

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        payload, _ = json.JSONDecoder().raw_decode(payload_text)

    if isinstance(payload, str):
        payload = json.loads(payload)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("Agent decision payload must be a JSON object")

    if "answer" in payload and "final_answer" not in payload:
        payload["final_answer"] = payload.pop("answer")
    if "input" in payload and "action_input" not in payload:
        payload["action_input"] = payload.pop("input")
    if "thought" in payload and "reasoning" not in payload:
        payload["reasoning"] = payload.pop("thought")

    action = payload.get("action")
    if action not in {"search_kb", "final_answer"}:
        payload["action"] = "final_answer" if payload.get("final_answer") else "search_kb"

    payload.setdefault("action_input", "")
    payload.setdefault("reasoning", "")
    payload.setdefault("final_answer", "")
    return AgentDecision.model_validate(payload)


def run_adapter_demo(query: str, top_k: int) -> None:
    _print_section("Adapter Demo")
    print("Query:", query)

    emb = EmbeddingsAdapter()
    vec = VectorStoreAdapter(DEFAULT_COLLECTION)
    retr = RetrieverAdapter(DEFAULT_COLLECTION)

    qvec = emb.embed_query(query)

    _print_section("Vector Search")
    hits = vec.search(qvec, top_k=top_k)
    pprint(hits[:top_k])

    _print_section("Retriever Wrapper")
    records = retr.retrieve(query, top_k=top_k)
    pprint(records[:top_k])

    _print_section("Legacy RAG")
    try:
        out = retr.rag_query(query, top_k=min(top_k, 3))
        print(out[:1000])
    except Exception as exc:
        print("Legacy RAG failed:", exc)


def build_rag_chain(collection_name: str, top_k: int):
    llm = AIAChatModel()
    embeddings = EmbeddingsAdapter()
    vector_store = VectorStoreAdapter(collection_name)

    def fast_search(query: str) -> list[dict]:
        query_vector = embeddings.embed_query(query)
        return vector_store.search(query_vector, top_k=top_k)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是友邦保险知识库助手。请严格依据检索上下文回答，不要编造。"
                "如果上下文不足，请明确说明。优先输出简洁、可执行的中文答案。",
            ),
            (
                "human",
                "用户问题：{question}\n\n检索上下文：\n{context}\n\n请给出最终答案：",
            ),
        ]
    )
    return (
        {
            "context": RunnableLambda(fast_search) | RunnableLambda(_format_hit_records),
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )


def run_rag_demo(query: str, top_k: int) -> None:
    _print_section("LangChain RAG Chain")
    chain = build_rag_chain(DEFAULT_COLLECTION, top_k)
    answer = chain.invoke(query)
    print(answer)


class AgentDecision(BaseModel):
    action: Literal["search_kb", "final_answer"] = Field(
        description="下一步动作：检索知识库，或直接产出最终答案"
    )
    action_input: str = Field(default="", description="当动作是 search_kb 时要执行的检索语句")
    reasoning: str = Field(default="", description="当前动作的简短理由")
    final_answer: str = Field(default="", description="当 action=final_answer 时填写")


class AgentState(TypedDict):
    question: str
    scratchpad: list[str]
    decision: dict
    steps: int
    final_answer: str


def build_agent_app(collection_name: str, top_k: int, max_steps: int = 2):
    llm = AIAChatModel()
    decision_parser = PydanticOutputParser(pydantic_object=AgentDecision)
    embeddings = EmbeddingsAdapter()
    vector_store = VectorStoreAdapter(collection_name)

    @tool
    def search_kb(query: str) -> str:
        """检索友邦保险知识库，返回与用户问题最相关的服务流程、条款或产品片段。"""
        query_vector = embeddings.embed_query(query)
        hits = vector_store.search(query_vector, top_k=top_k)
        return _format_hit_records(hits)

    tools = [search_kb]
    tools_text = "\n".join(f"- {tool_item.name}: {tool_item.description}" for tool_item in tools)

    planner_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是友邦保险知识库 Agent。"
                "你只能在两种动作中选择：search_kb 或 final_answer。"
                "如果当前证据不足，请先检索；如果已有足够证据，请直接作答。"
                "如果已有观察是‘暂无观察’，第一步必须选择 search_kb。"
                "必须输出严格 JSON，不能附加额外说明。\n\n"
                "可用工具：\n{tools_text}\n\n{format_instructions}",
            ),
            (
                "human",
                "用户问题：{question}\n\n已有观察：\n{scratchpad}",
            ),
        ]
    )

    answer_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是友邦保险知识库助手。请只依据已检索的内容回答，禁止编造。"
                "如果信息不足，明确说明缺口。",
            ),
            (
                "human",
                "用户问题：{question}\n\n检索记录：\n{scratchpad}\n\n请输出最终中文答案：",
            ),
        ]
    )

    planner_chain = planner_prompt | llm | StrOutputParser()
    answer_chain = answer_prompt | llm | StrOutputParser()

    def planner_node(state: AgentState) -> dict:
        scratchpad = "\n\n".join(state["scratchpad"]) if state["scratchpad"] else "暂无观察"
        raw = planner_chain.invoke(
            {
                "question": state["question"],
                "scratchpad": scratchpad,
                "tools_text": tools_text,
                "format_instructions": decision_parser.get_format_instructions(),
            }
        )
        decision = _parse_agent_decision(
            raw,
            question=state["question"],
            has_observation=bool(state["scratchpad"]),
        )
        return {"decision": decision.model_dump(), "steps": state["steps"] + 1}

    def tool_node(state: AgentState) -> dict:
        action_input = (state["decision"].get("action_input") or state["question"]).strip()
        tool_output = search_kb.invoke({"query": action_input})
        scratchpad = state["scratchpad"] + [f"检索问题：{action_input}\n检索结果：\n{tool_output}"]
        return {"scratchpad": scratchpad}

    def finalize_node(state: AgentState) -> dict:
        decision = state.get("decision") or {}
        direct_answer = (decision.get("final_answer") or "").strip()
        if direct_answer:
            return {"final_answer": direct_answer}

        scratchpad = "\n\n".join(state["scratchpad"]) if state["scratchpad"] else "暂无检索结果"
        final_answer = answer_chain.invoke(
            {"question": state["question"], "scratchpad": scratchpad}
        )
        return {"final_answer": final_answer}

    def route_next(state: AgentState) -> str:
        if not state["scratchpad"] and state["steps"] <= 1:
            return "tool"
        if state["steps"] >= max_steps:
            return "finalize"
        if state["decision"].get("action") == "search_kb":
            return "tool"
        return "finalize"

    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("tool", tool_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner",
        route_next,
        {
            "tool": "tool",
            "finalize": "finalize",
        },
    )
    graph.add_edge("tool", "planner")
    graph.add_edge("finalize", END)
    return graph.compile()


def run_agent_demo(query: str, top_k: int) -> None:
    _print_section("LangGraph Agent")
    agent_app = build_agent_app(DEFAULT_COLLECTION, top_k)
    result = agent_app.invoke(
        {
            "question": query,
            "scratchpad": [],
            "decision": {},
            "steps": 0,
            "final_answer": "",
        }
    )
    print(result["final_answer"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIA LangChain / LangGraph demo runner")
    parser.add_argument("query", help="用户问题")
    parser.add_argument(
        "--mode",
        choices=["adapter", "rag", "agent"],
        default="adapter",
        help="运行模式：adapter / rag / agent",
    )
    parser.add_argument("--top-k", type=int, default=5, help="检索返回条数")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "adapter":
        run_adapter_demo(args.query, args.top_k)
        return
    if args.mode == "rag":
        run_rag_demo(args.query, args.top_k)
        return
    run_agent_demo(args.query, args.top_k)


if __name__ == "__main__":
    main()
