"""Tests for memory CRUD API routes — learn, batch, get, delete, search,
prune, classify, feedback, consolidate, sync, and parquet export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from memos.api import create_fastapi_app
from memos.core import MemOS

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def memos():
    return MemOS(backend="memory")


@pytest.fixture()
def app(memos):
    return create_fastapi_app(memos=memos)


@pytest.fixture()
def client(app):
    return TestClient(app)


def _learn(client: TestClient, content: str = "test memory", **kwargs: object) -> str:
    """POST /learn and return the new item's ID."""
    payload: dict = {"content": content}
    payload.update(kwargs)
    resp = client.post("/api/v1/learn", json=payload)
    assert resp.status_code == 200, f"learn failed: {resp.text}"
    return resp.json()["id"]


def _make_envelope(memories: list[dict] | None = None) -> dict:
    """Build a minimal MemoryEnvelope dict (empty checksum → validation skipped)."""
    return {
        "source_agent": "agent-a",
        "target_agent": "agent-b",
        "memories": memories or [],
        "scope": "items",
        "format_version": "1.0",
        "checksum": "",
    }


# ── 1. POST /api/v1/learn/extract ──────────────────────────────────────────


class TestLearnExtract:
    """Learn a memory and extract KG facts in one call."""

    def test_happy_path(self, client):
        resp = client.post(
            "/api/v1/learn/extract",
            json={"content": "Alice works at Acme Corp"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "memory" in data
        assert data["memory"]["content"] == "Alice works at Acme Corp"
        assert "facts" in data
        assert "fact_count" in data
        assert isinstance(data["facts"], list)

    def test_with_tags_and_importance(self, client):
        resp = client.post(
            "/api/v1/learn/extract",
            json={"content": "Important note", "tags": ["urgent"], "importance": 0.9},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["memory"]["tags"] == ["urgent"]
        assert data["memory"]["importance"] == 0.9

    def test_empty_content_rejected(self, client):
        resp = client.post("/api/v1/learn/extract", json={"content": ""})
        assert resp.status_code == 422

    def test_missing_content_rejected(self, client):
        resp = client.post("/api/v1/learn/extract", json={})
        assert resp.status_code == 422


# ── 2. POST /api/v1/learn/batch ────────────────────────────────────────────


class TestBatchLearn:
    """Bulk-learn multiple memories."""

    def test_happy_path(self, client):
        resp = client.post(
            "/api/v1/learn/batch",
            json={
                "items": [
                    {"content": "one", "tags": [], "metadata": {}},
                    {"content": "two", "tags": [], "metadata": {}},
                    {"content": "three", "tags": [], "metadata": {}},
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["learned"] == 3
        assert len(data["items"]) == 3

    def test_with_tags_and_importance(self, client):
        resp = client.post(
            "/api/v1/learn/batch",
            json={
                "items": [
                    {"content": "alpha", "tags": ["a"], "importance": 0.9, "metadata": {}},
                    {"content": "beta", "tags": ["b"], "importance": 0.1, "metadata": {}},
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["learned"] == 2

    def test_continue_on_error_default_true(self, client):
        resp = client.post(
            "/api/v1/learn/batch",
            json={
                "items": [{"content": "valid", "tags": [], "metadata": {}}],
                "continue_on_error": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["learned"] == 1

    def test_empty_items_rejected(self, client):
        resp = client.post("/api/v1/learn/batch", json={"items": []})
        assert resp.status_code == 422

    def test_missing_items_rejected(self, client):
        resp = client.post("/api/v1/learn/batch", json={})
        assert resp.status_code == 422


# ── 3. GET /api/v1/memory/{item_id} ───────────────────────────────────────


class TestGetMemory:
    """Retrieve a single memory by ID."""

    def test_found(self, client):
        item_id = _learn(client, "hello world", tags=["greet"])
        resp = client.get(f"/api/v1/memory/{item_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        item = data["item"]
        assert item["id"] == item_id
        assert item["content"] == "hello world"
        assert "tags" in item
        assert "importance" in item
        assert "created_at" in item
        assert "accessed_at" in item
        assert "access_count" in item
        assert "relevance_score" in item

    def test_not_found(self, client):
        resp = client.get("/api/v1/memory/nonexistent-id-12345")
        assert resp.status_code == 404
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == "NOT_FOUND"

    def test_item_shape_includes_optional_fields(self, client):
        item_id = _learn(client, "metadata test", metadata={"source": "test"})
        resp = client.get(f"/api/v1/memory/{item_id}")
        assert resp.status_code == 200
        item = resp.json()["item"]
        assert "metadata" in item
        assert item["metadata"]["source"] == "test"


# ── 4. DELETE /api/v1/memory/{item_id} ────────────────────────────────────


class TestDeleteMemory:
    """Delete a single memory by ID."""

    def test_delete_existing(self, client):
        item_id = _learn(client, "to be deleted")
        resp = client.delete(f"/api/v1/memory/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        # Verify gone
        resp2 = client.get(f"/api/v1/memory/{item_id}")
        assert resp2.status_code == 404

    def test_delete_nonexistent(self, client):
        resp = client.delete("/api/v1/memory/nonexistent-id-12345")
        assert resp.status_code == 404
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == "NOT_FOUND"


# ── 5. GET /api/v1/search ─────────────────────────────────────────────────


class TestSearch:
    """Keyword search across all memories."""

    def test_returns_matching_results(self, client):
        _learn(client, "python programming language")
        _learn(client, "rust programming language")
        _learn(client, "cooking recipes for dinner")
        resp = client.get("/api/v1/search", params={"q": "programming"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["results"]) >= 2
        for r in data["results"]:
            assert "id" in r
            assert "content" in r
            assert "tags" in r

    def test_no_match_returns_empty(self, client):
        _learn(client, "something unrelated")
        resp = client.get("/api/v1/search", params={"q": "xyznonexistent"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []

    def test_missing_q_param(self, client):
        resp = client.get("/api/v1/search")
        assert resp.status_code == 422

    def test_limit_param(self, client):
        for i in range(5):
            _learn(client, f"programming item {i}")
        resp = client.get("/api/v1/search", params={"q": "programming", "limit": 2})
        assert resp.status_code == 200
        assert len(resp.json()["results"]) <= 2


# ── 6. POST /api/v1/prune ─────────────────────────────────────────────────


class TestPrune:
    """Decay-based cleanup of low-importance memories."""

    @staticmethod
    def _seed_old_item(memos: MemOS, content: str, importance: float) -> str:
        """Create an item with created_at 2 days ago so prune considers it."""

        item = memos.learn(content, importance=importance)
        item.created_at -= 2 * 86400  # age it 2 days
        memos._store.upsert(item, namespace=memos._namespace)
        return item.id

    def test_dry_run_returns_candidates(self, client, memos):
        self._seed_old_item(memos, "low importance", 0.05)
        resp = client.post(
            "/api/v1/prune",
            json={
                "threshold": 0.1,
                "max_age_days": 0,
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["pruned_count"] >= 1
        assert isinstance(data["pruned_ids"], list)

    def test_dry_run_does_not_delete(self, client, memos):
        item_id = self._seed_old_item(memos, "low importance", 0.05)
        client.post(
            "/api/v1/prune",
            json={
                "threshold": 0.1,
                "max_age_days": 0,
                "dry_run": True,
            },
        )
        resp = client.get(f"/api/v1/memory/{item_id}")
        assert resp.status_code == 200

    def test_actual_prune_deletes(self, client, memos):
        self._seed_old_item(memos, "low importance", 0.05)
        resp = client.post(
            "/api/v1/prune",
            json={
                "threshold": 0.1,
                "max_age_days": 0,
                "dry_run": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["pruned_count"] >= 1

    def test_high_threshold_skips_high_importance(self, client, memos):
        self._seed_old_item(memos, "important", 0.9)
        resp = client.post(
            "/api/v1/prune",
            json={
                "threshold": 0.1,
                "max_age_days": 0,
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["pruned_count"] == 0


# ── 7. GET /api/v1/classify ───────────────────────────────────────────────


class TestClassify:
    """Auto-tagging / classification of text."""

    def test_returns_tags_and_matches(self, client):
        resp = client.get("/api/v1/classify", params={"text": "deploy the python application"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["tags"], list)
        assert isinstance(data["matches"], (dict, list))

    def test_missing_text_param(self, client):
        resp = client.get("/api/v1/classify")
        assert resp.status_code == 422


# ── 8 & 9. Feedback — record + list ────────────────────────────────────────


class TestRecordFeedback:
    """POST /api/v1/feedback — record relevance feedback."""

    def test_positive_feedback(self, client):
        item_id = _learn(client, "feedback target")
        resp = client.post(
            "/api/v1/feedback",
            json={"item_id": item_id, "feedback": "relevant"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["feedback"]["item_id"] == item_id
        assert data["feedback"]["feedback"] == "relevant"

    def test_negative_feedback(self, client):
        item_id = _learn(client, "feedback target")
        resp = client.post(
            "/api/v1/feedback",
            json={"item_id": item_id, "feedback": "not-relevant"},
        )
        assert resp.status_code == 200
        assert resp.json()["feedback"]["feedback"] == "not-relevant"

    def test_invalid_feedback_value(self, client):
        item_id = _learn(client, "feedback target")
        resp = client.post(
            "/api/v1/feedback",
            json={"item_id": item_id, "feedback": "maybe"},
        )
        assert resp.status_code == 400

    def test_missing_required_fields(self, client):
        resp = client.post("/api/v1/feedback", json={})
        assert resp.status_code == 422


class TestListFeedback:
    """GET /api/v1/feedback — list feedback entries."""

    def test_empty_list(self, client):
        resp = client.get("/api/v1/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert data["feedback"] == []
        assert data["total"] == 0

    def test_returns_recorded_feedback(self, client):
        item_id = _learn(client, "target")
        client.post("/api/v1/feedback", json={"item_id": item_id, "feedback": "relevant"})
        resp = client.get("/api/v1/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["feedback"][0]["feedback"] == "relevant"

    def test_filter_by_item_id(self, client):
        id1 = _learn(client, "target one")
        id2 = _learn(client, "target two")
        client.post("/api/v1/feedback", json={"item_id": id1, "feedback": "relevant"})
        client.post("/api/v1/feedback", json={"item_id": id2, "feedback": "not-relevant"})
        resp = client.get("/api/v1/feedback", params={"item_id": id1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["feedback"][0]["item_id"] == id1


# ── 10. GET /api/v1/feedback/stats ─────────────────────────────────────────


class TestFeedbackStats:
    """GET /api/v1/feedback/stats — aggregate feedback statistics."""

    def test_empty_stats(self, client):
        resp = client.get("/api/v1/feedback/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_feedback"] == 0
        assert data["relevant_count"] == 0
        assert data["not_relevant_count"] == 0
        assert data["items_with_feedback"] == 0
        assert data["avg_feedback_score"] == 0.0

    def test_with_feedback_data(self, client):
        item_id = _learn(client, "stats target")
        client.post("/api/v1/feedback", json={"item_id": item_id, "feedback": "relevant"})
        client.post("/api/v1/feedback", json={"item_id": item_id, "feedback": "not-relevant"})
        resp = client.get("/api/v1/feedback/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_feedback"] == 2
        assert data["relevant_count"] == 1
        assert data["not_relevant_count"] == 1
        assert data["items_with_feedback"] == 1


# ── 11. POST /api/v1/consolidate (sync) ────────────────────────────────────


class TestConsolidateSync:
    """Trigger synchronous consolidation."""

    def test_dry_run(self, client):
        _learn(client, "duplicate content alpha")
        _learn(client, "duplicate content alpha")
        resp = client.post(
            "/api/v1/consolidate",
            json={"similarity_threshold": 0.75, "dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert "groups_found" in data
        assert "memories_merged" in data
        assert "space_freed" in data

    def test_actual_consolidation(self, client):
        _learn(client, "consolidation test memory one")
        _learn(client, "consolidation test memory two")
        resp = client.post(
            "/api/v1/consolidate",
            json={"similarity_threshold": 0.75, "dry_run": False, "merge_content": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"


# ── 12. GET /api/v1/consolidate (list) ──────────────────────────────────────


class TestConsolidateList:
    """List async consolidation tasks."""

    def test_empty_list(self, client):
        resp = client.get("/api/v1/consolidate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks"] == []


# ── 13. GET /api/v1/consolidate/{task_id} ──────────────────────────────────


class TestConsolidateStatus:
    """Get status of an async consolidation task."""

    def test_not_found(self, client):
        resp = client.get("/api/v1/consolidate/nonexistent-task-id")
        assert resp.status_code == 404
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == "NOT_FOUND"

    def test_after_async_consolidation(self, client):
        """Start an async consolidation then query its status."""
        _learn(client, "async consolidation test")
        start = client.post(
            "/api/v1/consolidate",
            json={"async": True, "similarity_threshold": 0.75, "dry_run": True},
        )
        assert start.status_code == 200
        task_id = start.json()["task_id"]
        assert task_id

        resp = client.get(f"/api/v1/consolidate/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task_id


# ── 14. POST /api/v1/sync/check ────────────────────────────────────────────


class TestSyncCheck:
    """Detect conflicts between local store and a remote envelope."""

    def test_all_new_memories(self, client):
        envelope = _make_envelope(
            memories=[{"id": "r1", "content": "remote memory", "tags": [], "importance": 0.5}],
        )
        resp = client.post("/api/v1/sync/check", json={"envelope": envelope})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["total_remote"] == 1
        assert data["new_memories"] == 1
        assert data["conflict_count"] == 0

    def test_empty_envelope(self, client):
        envelope = _make_envelope()
        resp = client.post("/api/v1/sync/check", json={"envelope": envelope})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_remote"] == 0

    def test_invalid_envelope_format(self, client):
        resp = client.post("/api/v1/sync/check", json={"envelope": {}})
        assert resp.status_code == 400

    def test_conflict_detection(self, client):
        """Learn locally, then send an envelope with same ID but different content."""
        item_id = _learn(client, "local content", tags=["local"], importance=0.5)
        envelope = _make_envelope(
            memories=[
                {"id": item_id, "content": "remote content CHANGED", "tags": ["remote"], "importance": 0.5},
            ],
        )
        resp = client.post("/api/v1/sync/check", json={"envelope": envelope})
        assert resp.status_code == 200
        data = resp.json()
        assert data["conflict_count"] >= 1


# ── 15. POST /api/v1/sync/apply ────────────────────────────────────────────


class TestSyncApply:
    """Apply synced memories with conflict resolution."""

    def test_apply_new_memories(self, client):
        envelope = _make_envelope(
            memories=[{"id": "r1", "content": "remote memory", "tags": [], "importance": 0.5}],
        )
        resp = client.post(
            "/api/v1/sync/apply",
            json={"envelope": envelope, "strategy": "local_wins"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["applied"] >= 1

    def test_apply_dry_run(self, client):
        envelope = _make_envelope(
            memories=[{"id": "r2", "content": "dry run memory", "tags": [], "importance": 0.5}],
        )
        resp = client.post(
            "/api/v1/sync/apply",
            json={"envelope": envelope, "strategy": "merge", "dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is True

    def test_apply_invalid_strategy(self, client):
        envelope = _make_envelope()
        # SyncApplyRequest validates strategy in pydantic, so this should 422
        resp = client.post(
            "/api/v1/sync/apply",
            json={"envelope": envelope, "strategy": "invalid_strategy"},
        )
        assert resp.status_code == 422

    def test_apply_invalid_envelope(self, client):
        resp = client.post("/api/v1/sync/apply", json={"envelope": {}})
        assert resp.status_code == 400


# ── 16. GET /api/v1/export/parquet ─────────────────────────────────────────


class TestExportParquet:
    """Export all memories as a downloadable Parquet file."""

    def test_returns_file(self, client):
        _learn(client, "export test")
        resp = client.get("/api/v1/export/parquet")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"
        assert "X-Memos-Total" in resp.headers
        assert int(resp.headers["X-Memos-Total"]) >= 1
        assert "X-Memos-Size" in resp.headers
        assert len(resp.content) > 0

    def test_empty_store_still_returns_file(self, client):
        resp = client.get("/api/v1/export/parquet")
        assert resp.status_code == 200
        assert int(resp.headers["X-Memos-Total"]) == 0


# ── 17. GET /api/v1/memories ──────────────────────────────────────────────


class TestListMemories:
    """List memories with optional filters."""

    def test_list_all(self, client):
        _learn(client, "M1", tags=["a"])
        _learn(client, "M2", tags=["b"])
        resp = client.get("/api/v1/memories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["total"] >= 2

    def test_list_with_tag_filter(self, client):
        _learn(client, "Tagged A", tags=["filter-tag-x"])
        _learn(client, "Tagged B", tags=["filter-tag-y"])
        resp = client.get("/api/v1/memories", params={"tag": ["filter-tag-x"]})
        assert resp.status_code == 200
        for item in resp.json()["results"]:
            assert "filter-tag-x" in item["tags"]

    def test_list_with_limit(self, client):
        for i in range(5):
            _learn(client, f"Item {i}")
        resp = client.get("/api/v1/memories", params={"limit": 2})
        assert resp.status_code == 200
        assert resp.json()["total"] <= 2


# ── 18. POST /api/v1/recall ───────────────────────────────────────────────


class TestRecallAPI:
    """Semantic recall via POST."""

    def test_recall_returns_results(self, client):
        _learn(client, "Python async patterns for web servers")
        resp = client.post("/api/v1/recall", json={"query": "python"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["results"], list)

    def test_recall_with_tag_filter(self, client):
        _learn(client, "Tagged recall", tags=["recall-filter"])
        resp = client.post("/api/v1/recall", json={"query": "tagged", "filter_tags": ["recall-filter"]})
        assert resp.status_code == 200
        assert len(resp.json()["results"]) >= 1

    def test_recall_with_importance_filter(self, client):
        _learn(client, "High importance", importance=0.9)
        _learn(client, "Low importance", importance=0.1)
        resp = client.post("/api/v1/recall", json={"query": "importance", "importance": {"min": 0.5}})
        assert resp.status_code == 200


# ── 19. GET /api/v1/recall/enriched ───────────────────────────────────────


class TestRecallEnriched:
    """Recall enriched with KG facts."""

    def test_recall_enriched(self, client):
        _learn(client, "Alice works at Beta Inc")
        resp = client.get("/api/v1/recall/enriched", params={"q": "Alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


# ── 20. GET /api/v1/memory/{id} — covered by TestGetMemory above ──────────

# ── 21. DELETE /api/v1/memory/{id} — covered by TestDeleteMemory above ────


# ── 22. POST /api/v1/prune ────────────────────────────────────────────────


class TestPruneAPI:
    """Decay-based pruning."""

    def test_dry_run(self, client):
        _learn(client, "Low imp", importance=0.01)
        resp = client.post("/api/v1/prune", json={"threshold": 0.5, "dry_run": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_dry_run_does_not_delete(self, client):
        _learn(client, "Keep me", importance=0.8)
        resp = client.post("/api/v1/prune", json={"threshold": 0.5, "dry_run": True})
        assert resp.status_code == 200
        # Memory should still exist after dry run
        list_resp = client.get("/api/v1/memories")
        assert list_resp.json()["total"] >= 1


# ── 23. GET/POST /api/v1/tags ─────────────────────────────────────────────


class TestTagsEndpoints:
    """Tags list, rename, delete."""

    def test_list_tags(self, client):
        _learn(client, "Tagged", tags=["tag-list-test"])
        resp = client.get("/api/v1/tags")
        assert resp.status_code == 200
        names = [t["tag"] for t in resp.json()]
        assert "tag-list-test" in names

    def test_rename_tag(self, client):
        _learn(client, "Rename test", tags=["rename-old"])
        resp = client.post("/api/v1/tags/rename", json={"old": "rename-old", "new": "rename-new"})
        assert resp.status_code == 200
        assert resp.json()["renamed"] >= 1

    def test_delete_tag(self, client):
        _learn(client, "Delete tag test", tags=["delete-this-tag"])
        resp = client.post("/api/v1/tags/delete", json={"tag": "delete-this-tag"})
        assert resp.status_code == 200
        assert resp.json()["deleted"] >= 1


# ── 24. POST /api/v1/decay/run ────────────────────────────────────────────


class TestDecayRun:
    """Run decay cycle."""

    def test_decay_dry_run(self, client):
        _learn(client, "Decay target", importance=0.5)
        resp = client.post("/api/v1/decay/run", json={"dry_run": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["total"], int)

    def test_decay_apply_via_public_facade(self, client):
        _learn(client, "decay apply target", importance=0.5)
        resp = client.post("/api/v1/decay/run", json={"apply": True, "min_age_days": 9999, "floor": 0.0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["total"], int)


# ── 25. POST /api/v1/memories/{id}/reinforce ──────────────────────────────


class TestReinforce:
    """Boost a memory's importance."""

    def test_reinforce_found(self, client):
        item_id = _learn(client, "Boost me", importance=0.5)
        resp = client.post(f"/api/v1/memories/{item_id}/reinforce", json={"strength": 0.1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["importance_after"] >= data["importance_before"]

    def test_reinforce_not_found(self, client):
        resp = client.post("/api/v1/memories/no-id/reinforce")
        assert resp.status_code == 404


# ── 26. POST /api/v1/compress ─────────────────────────────────────────────


class TestCompressAPI:
    """Memory compression."""

    def test_compress_dry_run(self, client):
        resp = client.post("/api/v1/compress", json={"dry_run": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── 27. POST /api/v1/dedup/check + scan ───────────────────────────────────


class TestDedupAPI:
    """Duplicate detection."""

    def test_dedup_check(self, client):
        _learn(client, "Dedup check content")
        resp = client.post("/api/v1/dedup/check", json={"content": "Dedup check content"})
        assert resp.status_code == 200
        assert "is_duplicate" in resp.json()

    def test_dedup_scan(self, client):
        _learn(client, "Scan A")
        _learn(client, "Scan B")
        resp = client.post("/api/v1/dedup/scan", json={"fix": False})
        assert resp.status_code == 200
        assert "total_scanned" in resp.json()


# ── 28. Versioning endpoints ──────────────────────────────────────────────


class TestVersioningAPI:
    """History, version get, diff, rollback, snapshot, recall-at, stats, gc."""

    def test_history(self, client):
        item_id = _learn(client, "Version test")
        resp = client.get(f"/api/v1/memory/{item_id}/history")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_version(self, client):
        item_id = _learn(client, "V get")
        resp = client.get(f"/api/v1/memory/{item_id}/version/1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_get_version_not_found(self, client):
        resp = client.get("/api/v1/memory/no-id/version/999")
        assert resp.status_code == 404

    def test_diff_latest(self, client, memos):
        item_id = _learn(client, "Diff test")
        from memos.models import MemoryItem

        updated = MemoryItem(id=item_id, content="Diff test updated", tags=[], importance=0.5)
        memos._store.upsert(updated)
        memos.versioning.record_version(updated, source="upsert")
        resp = client.get(f"/api/v1/memory/{item_id}/diff", params={"v1": 1, "latest": True})
        assert resp.status_code == 200

    def test_snapshot(self, client):
        import time

        ts = time.time()
        _learn(client, "Snap")
        resp = client.get("/api/v1/snapshot", params={"at": ts + 100})
        assert resp.status_code == 200
        assert isinstance(resp.json()["memories"], list)

    def test_recall_at(self, client):
        import time

        ts = time.time()
        resp = client.get("/api/v1/recall/at", params={"q": "test", "at": ts})
        assert resp.status_code == 200
        assert isinstance(resp.json()["results"], list)

    def test_versioning_stats(self, client):
        resp = client.get("/api/v1/versioning/stats")
        assert resp.status_code == 200

    def test_versioning_gc(self, client):
        resp = client.post("/api/v1/versioning/gc", json={"max_age_days": 365})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_rollback_not_found(self, client):
        resp = client.post("/api/v1/memory/no-id/rollback", json={"version": 1})
        assert resp.status_code == 404


# ── 29. GET /api/v1/export/markdown ───────────────────────────────────────


class TestExportMarkdown:
    """Export memories as markdown ZIP."""

    def test_returns_zip(self, client):
        _learn(client, "Markdown export test")
        resp = client.get("/api/v1/export/markdown")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert len(resp.content) > 0
