"""LLM client — wraps SiliconFlow chat completions API.
Supports both single-turn (legacy) and multi-turn messages.
"""
from __future__ import annotations

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

_API_KEY = os.getenv("LLM_CHAT_API_KEY", "")
_API_URL = "https://api.siliconflow.cn/v1/chat/completions"
_MODEL = "tencent/Hunyuan-MT-7B"
_HEADERS = {
    "Authorization": f"Bearer {_API_KEY}",
    "Content-Type": "application/json",
}


def chat_completion(messages: list[dict], stream: bool = False) -> str:
    """
    Call SiliconFlow chat API with a full messages list.

    Args:
        messages: OpenAI-format list [{"role": ..., "content": ...}, ...]
        stream:   Whether to use streaming (currently returns full text either way)

    Returns:
        Assistant reply text.
    """
    payload = {
        "model": _MODEL,
        "messages": messages,
        "stream": stream,
    }
    resp = requests.post(_API_URL, data=json.dumps(payload), headers=_HEADERS, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text}")
    return resp.json()["choices"][0]["message"]["content"]


# ── legacy single-turn helper (backward-compat) ───────────────────────────────
def query_llm(prompt: str) -> str:
    """Single-turn convenience wrapper — keeps existing callers working."""
    return chat_completion([{"role": "user", "content": prompt}])
