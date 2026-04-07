"""Tests for recall CLI filters: --tags, --after, --before."""

import os
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta

from memos.core import MemOS


class TestRecallDateFilters(unittest.TestCase):
    """Test recall with filter_after and filter_before in core."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mem = MemOS(backend="memory")
        # Disable retrieval engine so we get deterministic fallback behavior
        self.mem._retrieval._store = self.mem._store

    def test_recall_filter_after(self):
        """filter_after excludes memories created before the timestamp."""
        now = time.time()
        # Learn a memory, then manually set created_at to 1 day ago
        old_item = self.mem.learn("old memory from yesterday")
        old_item.created_at = now - 86400
        self.mem._store.upsert(old_item)

        # Learn a new memory
        self.mem.learn("new memory from today")

        # Recall with filter_after = 1 hour ago should only return today's memory
        results = self.mem.recall("memory", filter_after=now - 3600)
        contents = [r.item.content for r in results]
        assert all("today" in c or "new" in c for c in contents), f"Got old results: {contents}"
        assert not any("yesterday" in c for c in contents), f"Old memory leaked through: {contents}"

    def test_recall_filter_before(self):
        """filter_before excludes memories created after the timestamp."""
        now = time.time()
        old_item = self.mem.learn("old memory from yesterday")
        old_item.created_at = now - 86400
        self.mem._store.upsert(old_item)

        self.mem.learn("new memory from today")

        # Recall with filter_before = 1 hour ago should only return yesterday's memory
        results = self.mem.recall("memory", filter_before=now - 3600)
        contents = [r.item.content for r in results]
        assert all("yesterday" in c or "old" in c for c in contents), f"Got new results: {contents}"
        assert not any("today" in c for c in contents), f"New memory leaked through: {contents}"

    def test_recall_filter_after_and_before(self):
        """Combining both filters creates a date range."""
        now = time.time()

        # Three memories at different times
        old = self.mem.learn("memory from 3 days ago")
        old.created_at = now - 3 * 86400
        self.mem._store.upsert(old)

        mid = self.mem.learn("memory from 1 day ago")
        mid.created_at = now - 86400
        self.mem._store.upsert(mid)

        self.mem.learn("memory from today")

        # Filter to only the middle one (between 2 days ago and 12 hours ago)
        results = self.mem.recall(
            "memory",
            filter_after=now - 2 * 86400,
            filter_before=now - 43200,
        )
        contents = [r.item.content for r in results]
        assert any("1 day" in c for c in contents), f"Missing middle memory: {contents}"
        assert not any("3 days" in c for c in contents), f"Old memory leaked: {contents}"
        assert not any("today" in c for c in contents), f"New memory leaked: {contents}"

    def test_recall_no_date_filter_returns_all(self):
        """Without date filters, all memories are returned."""
        now = time.time()
        self.mem.learn("memory alpha")
        old = self.mem.learn("memory beta")
        old.created_at = now - 86400 * 100
        self.mem._store.upsert(old)

        results = self.mem.recall("memory")
        assert len(results) >= 2


class TestRecallTagFilter(unittest.TestCase):
    """Test recall with filter_tags in core (already exists, verify + new combos)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mem = MemOS(backend="memory")
        self.mem._retrieval._store = self.mem._store

    def test_recall_filter_tags_existing(self):
        """Existing filter_tags still works."""
        self.mem.learn("Docker setup", tags=["infra"])
        self.mem.learn("Pizza preferences", tags=["food"])
        results = self.mem.recall("setup", filter_tags=["infra"])
        assert all("infra" in r.item.tags for r in results)

    def test_recall_filter_tags_with_date(self):
        """Tags + date filters work together."""
        now = time.time()
        old = self.mem.learn("old infra note", tags=["infra"])
        old.created_at = now - 86400 * 10
        self.mem._store.upsert(old)

        self.mem.learn("new infra note", tags=["infra"])
        self.mem.learn("new food note", tags=["food"])

        results = self.mem.recall(
            "note",
            filter_tags=["infra"],
            filter_after=now - 3600,
        )
        contents = [r.item.content for r in results]
        assert any("new infra" in c for c in contents), f"Missing new infra: {contents}"
        assert not any("old infra" in c for c in contents), f"Old infra leaked: {contents}"
        assert not any("food" in c for c in contents), f"Food leaked: {contents}"


if __name__ == "__main__":
    unittest.main()
