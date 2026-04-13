"""Tests for the Knowledge Graph ↔ Memory bridge."""

from __future__ import annotations

from dataclasses import dataclass

from memos.kg_bridge import KGBridge
from memos.knowledge_graph import KnowledgeGraph
from memos.models import MemoryItem, RecallResult


@dataclass
class FakeMemOS:
    recall_results: list[RecallResult] | None = None

    def learn(self, content, tags=None, importance=0.5, metadata=None):
        return MemoryItem(
            id="mem12345",
            content=content,
            tags=list(tags or []),
            importance=importance,
            metadata=metadata or {},
        )

    def recall(self, query, top=10, filter_tags=None, min_score=0.0, filter_after=None, filter_before=None):
        return list(self.recall_results or [])[:top]


def test_learn_and_extract_creates_fact():
    memos = FakeMemOS()
    kg = KnowledgeGraph(db_path=":memory:")
    bridge = KGBridge(memos, kg)
    try:
        payload = bridge.learn_and_extract("Alice works at Acme Corp", tags=["people"])
        assert payload["fact_count"] == 1
        assert payload["memory"]["id"] == "mem12345"
        fact = payload["facts"][0]
        assert fact["subject"] == "Alice"
        assert fact["predicate"] == "works_at"
        assert fact["object"] == "Acme Corp"
        stored = kg.query("Alice")
        assert stored[0]["source"] == "memos:mem12345"
    finally:
        bridge.close()


def test_recall_enriched_merges_memory_and_kg_facts():
    kg = KnowledgeGraph(db_path=":memory:")
    kg.add_fact("Alice", "works_at", "Acme Corp")
    kg.add_fact("Bob", "knows", "Carol")
    memos = FakeMemOS(
        recall_results=[
            RecallResult(
                item=MemoryItem(id="m1", content="Alice met Bob", tags=["people"]),
                score=0.95,
                match_reason="semantic",
            )
        ]
    )
    bridge = KGBridge(memos, kg)
    try:
        payload = bridge.recall_enriched("Alice", top=5)
        assert payload["memory_count"] == 1
        assert payload["fact_count"] >= 1
        assert payload["memories"][0]["content"] == "Alice met Bob"
        assert any(f["subject"] == "Alice" for f in payload["facts"])
    finally:
        bridge.close()


def test_link_fact_to_memory_creates_bridge_fact():
    memos = FakeMemOS()
    kg = KnowledgeGraph(db_path=":memory:")
    bridge = KGBridge(memos, kg)
    try:
        link_id = bridge.link_fact_to_memory("fact-1", "mem-2")
        assert len(link_id) == 8
        facts = kg.query("memory:mem-2")
        assert any(f["predicate"] == "linked_to_memory" for f in facts)
    finally:
        bridge.close()


def test_api_recall_enriched_endpoint(tmp_path):
    from fastapi.testclient import TestClient

    from memos.api import create_fastapi_app

    kg_path = tmp_path / "kg.db"
    with KnowledgeGraph(db_path=str(kg_path)) as kg:
        kg.add_fact("Alice", "works_at", "Acme Corp")

    memos = FakeMemOS(
        recall_results=[
            RecallResult(
                item=MemoryItem(id="m2", content="Alice on the ops team", tags=["people"]),
                score=0.88,
                match_reason="semantic",
            )
        ]
    )
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))
    client = TestClient(app)

    resp = client.get("/api/v1/recall/enriched", params={"q": "Alice"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["memory_count"] == 1
    assert data["fact_count"] >= 1
