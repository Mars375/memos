"""Tests for HTTP versioning API endpoints (v0.12.0)."""

import time

import pytest

from memos.api import create_fastapi_app
from memos.core import MemOS
from memos.models import MemoryItem


@pytest.fixture
def app():
    """Create a FastAPI test app."""
    memos = MemOS(backend="memory")
    return create_fastapi_app(memos=memos)


@pytest.fixture
def client(app):
    """Create a test client."""
    from starlette.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def client_with_versions(client):
    """Create a client with versioned memories using direct storage upsert."""
    # Access the underlying MemOS from the app
    # We need to learn first, then update via storage
    resp = client.post("/api/v1/learn", json={"content": "API v1 about AI", "tags": ["ai"], "importance": 0.5})
    item1_id = resp.json()["id"]
    # Get the memos instance from the app's closure
    # Instead, use the learn API to create, then we can check history
    # But learn always creates new items... so we test with what we have
    return client, item1_id


@pytest.fixture
def mem_app():
    """Create MemOS + FastAPI app with full version history."""
    memos = MemOS(backend="memory")
    # Create item and update it 3 times
    item = memos.learn("API v1 about AI", tags=["ai"], importance=0.5)
    time.sleep(0.01)

    v2 = MemoryItem(id=item.id, content="API v2 about AI and ML", tags=["ai", "ml"], importance=0.7)
    memos._store.upsert(v2)
    memos.versioning.record_version(v2, source="upsert")
    time.sleep(0.01)

    v3 = MemoryItem(id=item.id, content="API v3 about AI, ML, DL", tags=["ai", "ml", "dl"], importance=0.9)
    memos._store.upsert(v3)
    memos.versioning.record_version(v3, source="upsert")

    # Also create a second independent item
    item2 = memos.learn("Cooking is fun", tags=["food"], importance=0.3)

    app = create_fastapi_app(memos=memos)
    return app, item.id, item2.id


@pytest.fixture
def mem_client(mem_app):
    from starlette.testclient import TestClient

    app, item1_id, item2_id = mem_app
    client = TestClient(app)
    return client, item1_id, item2_id


class TestVersionHistoryEndpoint:
    """Tests for GET /api/v1/memory/{item_id}/history."""

    def test_history_basic(self, mem_client):
        client, item1_id, _ = mem_client
        resp = client.get(f"/api/v1/memory/{item1_id}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["item_id"] == item1_id
        assert data["total"] == 3
        assert len(data["versions"]) == 3

    def test_history_item_not_found(self, client):
        resp = client.get("/api/v1/memory/nonexistent123/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


class TestVersionGetEndpoint:
    """Tests for GET /api/v1/memory/{item_id}/version/{n}."""

    def test_get_version(self, mem_client):
        client, item1_id, _ = mem_client
        resp = client.get(f"/api/v1/memory/{item1_id}/version/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"]["version_number"] == 1
        assert "API v1" in data["version"]["content"]

    def test_get_version_not_found(self, mem_client):
        client, item1_id, _ = mem_client
        resp = client.get(f"/api/v1/memory/{item1_id}/version/999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_found"


class TestVersionDiffEndpoint:
    """Tests for GET /api/v1/memory/{item_id}/diff."""

    def test_diff_specific(self, mem_client):
        client, item1_id, _ = mem_client
        resp = client.get(f"/api/v1/memory/{item1_id}/diff?v1=1&v2=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        diff = data["diff"]
        assert diff["from_version"] == 1
        assert diff["to_version"] == 3
        assert "content" in diff["changes"]

    def test_diff_latest(self, mem_client):
        client, item1_id, _ = mem_client
        resp = client.get(f"/api/v1/memory/{item1_id}/diff?v1=2&v2=3&latest=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestRollbackEndpoint:
    """Tests for POST /api/v1/memory/{item_id}/rollback."""

    def test_rollback(self, mem_client):
        client, item1_id, _ = mem_client
        resp = client.post(f"/api/v1/memory/{item1_id}/rollback", json={"version": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["rolled_back_to"] == 1
        assert "API v1" in data["content"]

    def test_rollback_not_found(self, mem_client):
        client, item1_id, _ = mem_client
        resp = client.post(f"/api/v1/memory/{item1_id}/rollback", json={"version": 999})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_found"

    def test_rollback_missing_version(self, mem_client):
        client, item1_id, _ = mem_client
        resp = client.post(f"/api/v1/memory/{item1_id}/rollback", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"


class TestSnapshotEndpoint:
    """Tests for GET /api/v1/snapshot."""

    def test_snapshot_now(self, mem_client):
        client, _, _ = mem_client
        resp = client.get(f"/api/v1/snapshot?at={time.time()}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0

    def test_snapshot_epoch_zero(self, mem_client):
        client, _, _ = mem_client
        resp = client.get("/api/v1/snapshot?at=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


class TestRecallAtEndpoint:
    """Tests for GET /api/v1/recall/at."""

    def test_recall_at_now(self, mem_client):
        client, _, _ = mem_client
        resp = client.get(f"/api/v1/recall/at?q=AI&at={time.time()}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0

    def test_recall_at_past(self, mem_client):
        client, _, _ = mem_client
        resp = client.get("/api/v1/recall/at?q=AI&at=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


class TestRecallAtStreamEndpoint:
    """Tests for GET /api/v1/recall/at/stream (SSE)."""

    def test_stream_basic(self, mem_client):
        client, _, _ = mem_client
        resp = client.get(f"/api/v1/recall/at/stream?q=AI&at={time.time()}")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        text = resp.text
        assert "event: recall" in text or "event: done" in text

    def test_stream_empty(self, mem_client):
        client, _, _ = mem_client
        resp = client.get("/api/v1/recall/at/stream?q=AI&at=0")
        assert resp.status_code == 200
        text = resp.text
        assert "event: done" in text


class TestVersioningStatsEndpoint:
    """Tests for GET /api/v1/versioning/stats."""

    def test_stats(self, mem_client):
        client, _, _ = mem_client
        resp = client.get("/api/v1/versioning/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_versions"] > 0
        assert data["total_items"] > 0


class TestVersioningGCEndpoint:
    """Tests for POST /api/v1/versioning/gc."""

    def test_gc_defaults(self, mem_client):
        client, _, _ = mem_client
        resp = client.post("/api/v1/versioning/gc", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["removed"] == 0  # No versions older than 90 days

    def test_gc_keep_latest(self, mem_client):
        """GC with keep_latest=1 should reduce versions but keep at least 1 per item."""
        client, item1_id, _ = mem_client
        # First check current versions
        stats_before = client.get("/api/v1/versioning/stats").json()
        assert stats_before["total_versions"] >= 3

        # GC keeping only 1 latest per item (all are recent so max_age doesn't matter)
        # Since all versions are very recent, they won't be removed by max_age_days
        # We need a very aggressive GC that still respects keep_latest
        resp = client.post("/api/v1/versioning/gc", json={"max_age_days": 0.0, "keep_latest": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        # Should have removed some versions (item1 had 3, now keeps 1)
        assert data["removed"] >= 2


class TestAPIVersioningIntegration:
    """End-to-end integration test for versioning API workflow."""

    def test_full_workflow(self, mem_client):
        """history -> diff -> snapshot -> recall-at -> rollback -> stats -> gc."""
        client, item1_id, _ = mem_client

        # History
        hist = client.get(f"/api/v1/memory/{item1_id}/history").json()
        assert hist["total"] == 3

        # Diff
        diff = client.get(f"/api/v1/memory/{item1_id}/diff?v1=1&v2=3").json()
        assert diff["status"] == "ok"
        assert "content" in diff["diff"]["changes"]

        # Snapshot
        snap = client.get(f"/api/v1/snapshot?at={time.time()}").json()
        assert snap["total"] > 0

        # Recall-at
        recall = client.get(f"/api/v1/recall/at?q=AI&at={time.time()}").json()
        assert recall["total"] > 0

        # Rollback
        rb = client.post(f"/api/v1/memory/{item1_id}/rollback", json={"version": 1}).json()
        assert rb["status"] == "ok"
        assert "API v1" in rb["content"]

        # Stats
        stats = client.get("/api/v1/versioning/stats").json()
        assert stats["total_versions"] >= 4  # 3 + rollback

        # GC
        gc = client.post("/api/v1/versioning/gc", json={"max_age_days": 0.0, "keep_latest": 2}).json()
        assert gc["status"] == "ok"
        assert gc["removed"] > 0
