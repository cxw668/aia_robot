"""LLM 重排序策略（从 rag.py 迁移）。"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.knowledge_base.retrieval.prompt_builder import build_scoring_prompt

logger = logging.getLogger(__name__)
_JSON_DECODER = json.JSONDecoder()


@dataclass(frozen=True)
class RescoreResult:
    items: list[dict]
    used_llm: bool
    fallback_reason: str | None = None


def _fallback(candidates: list[dict], final_top_k: int, reason: str) -> RescoreResult:
    # Preserve a concrete fallback reason so retrieval logs can tell whether we
    # failed on the LLM call, JSON parsing, or a schema mismatch.
    return RescoreResult(
        items=candidates[:final_top_k],
        used_llm=False,
        fallback_reason=reason,
    )


def _parse_llm_response_payload(resp: str) -> list[dict] | dict:
    for candidate in _iter_json_candidates(resp):
        parsed = _try_decode_json(candidate)
        if parsed is not None:
            return parsed
    raise json.JSONDecodeError("Could not parse JSON payload", resp, 0)


def _iter_json_candidates(resp: str):
    seen: set[str] = set()

    def _yield_once(text: str):
        normalized = text.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        yield normalized

    yield from _yield_once(resp)

    for match in re.finditer(r"```(?:json)?\s*(.*?)```", resp, re.IGNORECASE | re.DOTALL):
        yield from _yield_once(match.group(1))

    for index, char in enumerate(resp):
        if char not in "[{":
            continue
        yield from _yield_once(resp[index:])


def _try_decode_json(candidate: str) -> list[dict] | dict | None:
    for text in (candidate, _quote_unquoted_keys(candidate)):
        try:
            parsed, _ = _JSON_DECODER.raw_decode(text)
            return parsed
        except json.JSONDecodeError:
            continue
    return None


def _quote_unquoted_keys(text: str) -> str:
    return re.sub(
        r'(?P<prefix>[\{,]\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:',
        r'\g<prefix>"\g<key>":',
        text,
    )


def llm_rescore_candidates(
    query: str,
    candidates: list[dict],
    max_candidates: int = 10,
    min_llm_score: float = 0.6,
    final_top_k: int = 5,
) -> RescoreResult:
    """使用 LLM 对候选文档进行逐条评分，并返回基于 LLM 分数融合后的候选列表。"""
    from app.chat.index import query_llm

    if not candidates:
        return RescoreResult(items=[], used_llm=False, fallback_reason="no_candidates")

    slice_cands = candidates[: max(1, min(len(candidates), max_candidates))]
    prompt = build_scoring_prompt(query, slice_cands)
    try:
        resp = query_llm(prompt)
    except Exception as exc:
        logger.exception("[rag] llm_rescore failed: %s", exc)
        return _fallback(candidates, final_top_k, "llm_request_failed")

    try:
        parsed = _parse_llm_response_payload(resp)
    except json.JSONDecodeError:
        logger.warning("[rag] could not parse JSON payload from LLM response")
        return _fallback(candidates, final_top_k, "llm_response_parse_failed")

    if isinstance(parsed, dict):
        # Accept both array-only responses and wrapper objects from the model.
        parsed = parsed.get("items") or parsed.get("results") or []
    if not isinstance(parsed, list):
        return _fallback(candidates, final_top_k, "llm_response_schema_invalid")

    score_map: dict[str, dict] = {}
    for item in parsed or []:
        try:
            cid = str(item.get("id"))
            s = float(item.get("relevance_score") or 0.0)
            score_map[cid] = {
                "llm_score": max(0.0, min(1.0, s)),
                "verdict": item.get("verdict"),
                "explanation": item.get("explanation"),
            }
        except Exception:
            continue
    if not score_map:
        return _fallback(candidates, final_top_k, "llm_scores_missing")

    fused: list[dict] = []
    for c in slice_cands:
        cid = str(c.get("id") or c.get("payload", {}).get("id") or c.get("title") or "")
        orig = float(c.get("score") or 0.0)
        meta = score_map.get(cid) or {}
        llm_s = float(meta.get("llm_score") or 0.0)
        combined = round(0.6 * orig + 0.4 * llm_s, 4)
        new = dict(c)
        new["llm_score"] = llm_s
        new["llm_verdict"] = meta.get("verdict")
        new["llm_explanation"] = meta.get("explanation")
        new["_orig_score"] = orig
        new["score"] = combined
        fused.append(new)

    rest = candidates[len(slice_cands):]
    full = fused + rest
    full.sort(key=lambda x: x.get("score", 0), reverse=True)

    filtered = [
        item for item in fused
        if item.get("llm_verdict") == "use"
        or float(item.get("llm_score") or 0.0) >= min_llm_score
    ]
    if filtered:
        filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
        return RescoreResult(items=filtered[:final_top_k], used_llm=True)

    return RescoreResult(items=full[:final_top_k], used_llm=True)


__all__ = ["RescoreResult", "llm_rescore_candidates"]
