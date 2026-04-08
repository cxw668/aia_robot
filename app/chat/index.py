"""LLM 客户端 —— 封装了 SiliconFlow 的对话补全 API。

支持功能：
- 多轮对话消息 (chat_completion)
- 流式传输 SSE (chat_completion_stream) —— 实时输出文本增量
- 传统的单轮对话 (query_llm)
"""
from __future__ import annotations

import json
from typing import Generator

import requests
from app.config import settings

_API_URL = "https://api.siliconflow.cn/v1/chat/completions"


def _headers() -> dict:
    key = settings.llm_chat_api_key
    if not key or not key.strip():
        raise RuntimeError(
            "LLM API key is not set. Please set LLM_CHAT_API_KEY in environment or app/.env"
        )
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _model() -> str:
    return settings.llm_model or "tencent/Hunyuan-MT-7B"


def chat_completion(messages: list[dict], stream: bool = False) -> str:
    payload = {
        "model": _model(),
        "messages": messages,
        "stream": False,
    }
    resp = requests.post(
        settings.llm_api_url or _API_URL,
        data=json.dumps(payload),
        headers=_headers(),
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text}")
    return resp.json()["choices"][0]["message"]["content"]


def chat_completion_stream(
    messages: list[dict],
) -> Generator[str, None, None]:
    payload = {
        "model": _model(),
        "messages": messages,
        "stream": True,
    }
    with requests.post(
        settings.llm_api_url or _API_URL,
        data=json.dumps(payload),
        headers=_headers(),
        timeout=120,
        stream=True,
    ) as resp:
        if not resp.ok:
            raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text}")
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data:"):
                continue
            data_str = line[len("data:"):].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            text = delta.get("content", "")
            if text:
                yield text


# ── Legacy single-turn helper (backward-compat) ─────────────────────────────

def query_llm(prompt: str) -> str:
    return chat_completion([{"role": "user", "content": prompt}])
