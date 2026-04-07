"""Tests for relevance feedback feature."""

import json
import pytest
from memos.core import MemOS
from memos.models import FeedbackEntry, FeedbackStats


@pytest.fixture
def memos(tmp_path):
    """Create a MemOS instance with a temporary JSON store."""
    return MemOS(backend="memory", persist_path=str(tmp_path / "store.json"))


class TestFeedbackEntry:
    def test_create_entry(self):
        e = FeedbackEntry(item_id="abc123", feedback="relevant", query="test")
        assert e.item_id == "abc123"
        assert e.feedback == "relevant"
        assert e.query == "test"
        assert e.created_at > 0

    def test_to_dict(self):
        e = FeedbackEntry(item_id="abc", feedback="not-relevant", score_at_recall=0.85)
        d = e.to_dict()
        assert d["item_id"] == "abc"
        assert d["feedback"] == "not-relevant"
        assert d["score_at_recall"] == 0.85

    def test_from_dict(self):
        data = {"item_id": "abc", "feedback": "relevant", "query": "q", "agent_id": "agent1"}
        e = FeedbackEntry.from_dict(data)
        assert e.item_id == "abc"
        assert e.agent_id == "agent1"

    def test_from_dict_ignores_extra_keys(self):
        data = {"item_id": "abc", "feedback": "relevant", "extra": "ignored"}
        e = FeedbackEntry.from_dict(data)
        assert e.item_id == "abc"
        assert not hasattr(e, "extra")


class TestFeedbackStats:
    def test_empty_stats(self):
        s = FeedbackStats()
        assert s.total_feedback == 0
        assert s.to_dict()["avg_feedback_score"] == 0.0

    def test_stats_to_dict(self):
        s = FeedbackStats(total_feedback=10, relevant_count=7, not_relevant_count=3,
                         items_with_feedback=5, avg_feedback_score=0.4)
        d = s.to_dict()
        assert d["total_feedback"] == 10
        assert d["relevant_count"] == 7
        assert d["avg_feedback_score"] == 0.4


class TestRecordFeedback:
    def test_record_relevant(self, memos):
        item = memos.learn("test memory", tags=["test"])
        entry = memos.record_feedback(item.id, "relevant", query="test", score_at_recall=0.8)
        assert entry.feedback == "relevant"
        assert entry.item_id == item.id
        # Importance should increase
        updated = memos._store.get(item.id, namespace="")
        assert updated.importance == pytest.approx(0.6)

    def test_record_not_relevant(self, memos):
        item = memos.learn("test memory", tags=["test"])
        entry = memos.record_feedback(item.id, "not-relevant")
        assert entry.feedback == "not-relevant"
        updated = memos._store.get(item.id, namespace="")
        assert updated.importance == pytest.approx(0.4)

    def test_invalid_feedback_raises(self, memos):
        item = memos.learn("test", tags=["test"])
        with pytest.raises(ValueError, match="Invalid feedback"):
            memos.record_feedback(item.id, "maybe")

    def test_importance_clamped_at_1(self, memos):
        item = memos.learn("test", tags=["test"], importance=0.95)
        memos.record_feedback(item.id, "relevant")
        updated = memos._store.get(item.id, namespace="")
        assert updated.importance == pytest.approx(1.0)

    def test_importance_clamped_at_0(self, memos):
        item = memos.learn("test", tags=["test"], importance=0.05)
        memos.record_feedback(item.id, "not-relevant")
        updated = memos._store.get(item.id, namespace="")
        assert updated.importance == pytest.approx(0.0)

    def test_feedback_persists_in_metadata(self, memos):
        item = memos.learn("test", tags=["test"])
        memos.record_feedback(item.id, "relevant", query="q")
        updated = memos._store.get(item.id, namespace="")
        assert "_feedback" in updated.metadata
        assert len(updated.metadata["_feedback"]) == 1
        assert updated.metadata["_feedback"][0]["feedback"] == "relevant"

    def test_multiple_feedback_on_same_item(self, memos):
        item = memos.learn("test", tags=["test"])
        memos.record_feedback(item.id, "relevant", query="q1")
        memos.record_feedback(item.id, "not-relevant", query="q2")
        updated = memos._store.get(item.id, namespace="")
        assert len(updated.metadata["_feedback"]) == 2
        # 0.5 + 0.1 - 0.1 = 0.5
        assert updated.importance == pytest.approx(0.5)

    def test_nonexistent_item_no_error(self, memos):
        # Should not raise, just not store importance change
        entry = memos.record_feedback("nonexistent123", "relevant")
        assert entry.feedback == "relevant"


class TestGetFeedback:
    def test_get_all_feedback(self, memos):
        item1 = memos.learn("memory one", tags=["test"])
        item2 = memos.learn("memory two", tags=["test"])
        memos.record_feedback(item1.id, "relevant", query="q")
        memos.record_feedback(item2.id, "not-relevant", query="q")
        entries = memos.get_feedback()
        assert len(entries) == 2

    def test_get_feedback_by_item_id(self, memos):
        item1 = memos.learn("memory one", tags=["test"])
        item2 = memos.learn("memory two", tags=["test"])
        memos.record_feedback(item1.id, "relevant")
        memos.record_feedback(item2.id, "not-relevant")
        entries = memos.get_feedback(item_id=item1.id)
        assert len(entries) == 1
        assert entries[0].item_id == item1.id

    def test_get_feedback_limit(self, memos):
        item = memos.learn("test", tags=["test"])
        for i in range(10):
            memos.record_feedback(item.id, "relevant", query=f"q{i}")
        entries = memos.get_feedback(limit=5)
        assert len(entries) == 5

    def test_get_feedback_empty(self, memos):
        memos.learn("test", tags=["test"])
        entries = memos.get_feedback()
        assert entries == []


class TestFeedbackStats:
    def test_stats_empty(self, memos):
        stats = memos.feedback_stats()
        assert stats.total_feedback == 0

    def test_stats_mixed(self, memos):
        item1 = memos.learn("mem1", tags=["test"])
        item2 = memos.learn("mem2", tags=["test"])
        memos.record_feedback(item1.id, "relevant")
        memos.record_feedback(item1.id, "relevant")
        memos.record_feedback(item2.id, "not-relevant")
        stats = memos.feedback_stats()
        assert stats.total_feedback == 3
        assert stats.relevant_count == 2
        assert stats.not_relevant_count == 1
        assert stats.items_with_feedback == 2
        assert stats.avg_feedback_score == pytest.approx(1/3)

    def test_stats_to_dict(self, memos):
        item = memos.learn("test", tags=["test"])
        memos.record_feedback(item.id, "relevant")
        stats = memos.feedback_stats()
        d = stats.to_dict()
        assert "total_feedback" in d
        assert "relevant_count" in d


class TestFeedbackPersistence:
    def test_feedback_survives_restart(self, tmp_path):
        store_path = str(tmp_path / "store.json")
        m1 = MemOS(backend="memory", persist_path=store_path)
        item = m1.learn("persistent test", tags=["test"])
        m1.record_feedback(item.id, "relevant", query="test")
        
        # Simulate restart
        m2 = MemOS(backend="memory", persist_path=store_path)
        entries = m2.get_feedback(item_id=item.id)
        assert len(entries) == 1
        assert entries[0].feedback == "relevant"

    def test_importance_survives_restart(self, tmp_path):
        store_path = str(tmp_path / "store.json")
        m1 = MemOS(backend="memory", persist_path=store_path)
        item = m1.learn("test", tags=["test"], importance=0.5)
        m1.record_feedback(item.id, "relevant")
        
        m2 = MemOS(backend="memory", persist_path=store_path)
        updated = m2._store.get(item.id, namespace="")
        assert updated.importance == pytest.approx(0.6)
