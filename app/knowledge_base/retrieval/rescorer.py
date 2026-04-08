"""LLM 重排序策略（从 rag.py 迁移）。"""
from __future__ import annotations

import json
import logging

from app.knowledge_base.retrieval.prompt_builder import build_scoring_prompt

logger = logging.getLogger(__name__)


def llm_rescore_candidates(query: str, candidates: list[dict], max_candidates: int = 10) -> list[dict]:
    """使用 LLM 对候选文档进行逐条评分，并返回基于 LLM 分数融合后的候选列表。"""
    from app.chat.index import query_llm

    if not candidates:
        return candidates

    slice_cands = candidates[: max(1, min(len(candidates), max_candidates))]
    prompt = build_scoring_prompt(query, slice_cands)
    try:
        resp = query_llm(prompt)
    except Exception as exc:
        logger.exception("[rag] llm_rescore failed: %s", exc)
        return candidates

    try:
        parsed = json.loads(resp)
    except Exception:
        try:
            start_idx = resp.find("[")
            end_idx = resp.rfind("]") + 1
            if start_idx != -1 and end_idx != 0:
                parsed = json.loads(resp[start_idx:end_idx])
            else:
                start_idx = resp.find("{")
                end_idx = resp.rfind("}") + 1
                if start_idx != -1 and end_idx != 0:
                    parsed = json.loads(resp[start_idx:end_idx])
                else:
                    logger.warning("[rag] could not locate JSON in LLM response")
                    return candidates
        except json.JSONDecodeError as exc:
            try:
                import re
                fixed_resp = re.sub(r"(\s*{\s*|\s*,\s*)(\w+)\s*:", r'\1"\2":', resp)
                json_match = re.search(r"(\[.*\]|{.*})", fixed_resp, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                else:
                    logger.exception("[rag] failed to parse llm response: %s", exc)
                    return candidates
            except Exception as exc2:
                logger.exception("[rag] failed to parse llm response after fix attempts: %s", exc2)
                return candidates
        except Exception as exc:
            logger.exception("[rag] failed to parse llm response: %s", exc)
            return candidates

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
    return full


__all__ = ["llm_rescore_candidates"]
