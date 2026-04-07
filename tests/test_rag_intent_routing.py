import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.knowledge_base import rag
from app.knowledge_base.intent_rules import RetrievalIntent


def make_intent() -> RetrievalIntent:
    return RetrievalIntent(
        key="service_guide",
        name="服务指南",
        schemas=("service_categories",),
        categories=(),
        only_on_sale=False,
        official_url="",
    )


def test_high_confidence_single_route(monkeypatch):
    intent = make_intent()
    intent_result = type("R", (), {"intent": intent, "confidence": 0.8})()
    monkeypatch.setattr(rag, "classify_query_intent_with_scores", lambda q: intent_result)

    def qc(client, collection, vector, top_k, query_filter=None):
        if query_filter is not None:
            return [{"score": 0.9, "title": "T1", "content": "c1", "collection": "col"}]
        return [{"score": 0.5, "title": "T2", "content": "c2", "collection": "col"}]

    monkeypatch.setattr(rag, "query_collection", qc)
    hits = rag.retrieve("测试 高置信")
    assert isinstance(hits, list)
    assert hits[0]["title"] == "T1"


def test_mid_confidence_merge(monkeypatch):
    intent = make_intent()
    intent_result = type("R", (), {"intent": intent, "confidence": 0.6})()
    monkeypatch.setattr(rag, "classify_query_intent_with_scores", lambda q: intent_result)

    def qc(client, collection, vector, top_k, query_filter=None):
        if query_filter is not None:
            return [{"score": 0.6, "title": "A", "content": "common", "collection": "c1"}]
        else:
            return [
                {"score": 0.65, "title": "A", "content": "common", "collection": "c1"},
                {"score": 0.5, "title": "B", "content": "other", "collection": "c1"},
            ]

    monkeypatch.setattr(rag, "query_collection", qc)
    hits = rag.retrieve("测试 中置信")
    assert len(hits) == 2
    assert hits[0]["title"] == "A" and hits[0]["score"] == 0.65
    assert hits[1]["title"] == "B"


def test_low_confidence_unfiltered(monkeypatch):
    intent_result = type("R", (), {"intent": None, "confidence": 0.3})()
    monkeypatch.setattr(rag, "classify_query_intent_with_scores", lambda q: intent_result)

    def qc(client, collection, vector, top_k, query_filter=None):
        assert query_filter is None
        return [{"score": 0.4, "title": "U1", "content": "u1", "collection": "c"}]

    monkeypatch.setattr(rag, "query_collection", qc)
    hits = rag.retrieve("测试 低置信")
    assert hits[0]["title"] == "U1"


def test_high_confidence_fallback(monkeypatch):
    intent = make_intent()
    intent_result = type("R", (), {"intent": intent, "confidence": 0.9})()
    monkeypatch.setattr(rag, "classify_query_intent_with_scores", lambda q: intent_result)

    calls = []

    def qc(client, collection, vector, top_k, query_filter=None):
        calls.append(query_filter is not None)
        if query_filter is not None:
            return []
        return [{"score": 0.33, "title": "FB", "content": "fb", "collection": "c"}]

    monkeypatch.setattr(rag, "query_collection", qc)
    hits = rag.retrieve("测试 回退")
    assert hits[0]["title"] == "FB"
    assert True in calls and False in calls
