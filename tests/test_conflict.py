"""Tests for memos.conflict — Memory Conflict Resolution (P12)."""



from memos.conflict import (
    Conflict,
    ConflictDetector,
    ConflictType,
    ResolutionStrategy,
    SyncReport,
)
from memos.core import MemOS
from memos.models import MemoryItem
from memos.sharing.models import MemoryEnvelope

# ── Helpers ──────────────────────────────────────────────

def _item(content="test", id=None, tags=None, importance=0.5, metadata=None):
    """Create a test MemoryItem."""
    from memos.models import generate_id
    return MemoryItem(
        id=id or generate_id(content),
        content=content,
        tags=tags or [],
        importance=importance,
        metadata=metadata or {},
    )


def _envelope(memories, source="agent-a", target="agent-b"):
    """Create a test MemoryEnvelope."""
    env = MemoryEnvelope(
        source_agent=source,
        target_agent=target,
        memories=memories,
    )
    env.checksum = env.compute_checksum()
    return env


# ── ConflictDetector — detect_from_dicts ────────────────

class TestDetectFromDicts:
    """Test conflict detection without a live MemOS instance."""

    def test_no_conflicts_identical(self):
        """Identical local and remote memories → no conflicts."""
        item = _item("hello world", id="abc123")
        detector = ConflictDetector()
        report = detector.detect_from_dicts(
            [item],
            [{"id": "abc123", "content": "hello world", "tags": [], "importance": 0.5}],
        )
        assert report.total_remote == 1
        assert report.unchanged == 1
        assert len(report.conflicts) == 0
        assert report.new_memories == 0

    def test_new_memory_no_conflict(self):
        """Remote memory with new ID → new memory, no conflict."""
        local = [_item("local memory", id="local1")]
        remote = [{"id": "remote1", "content": "remote memory"}]
        detector = ConflictDetector()
        report = detector.detect_from_dicts(local, remote)
        assert report.new_memories == 1
        assert len(report.conflicts) == 0

    def test_content_changed_conflict(self):
        """Same ID, different content → CONTENT_CHANGED conflict."""
        local = [_item("original content", id="mem1")]
        remote = [{"id": "mem1", "content": "modified content entirely different", "tags": [], "importance": 0.5}]
        detector = ConflictDetector()
        report = detector.detect_from_dicts(local, remote)
        assert len(report.conflicts) == 1
        assert ConflictType.CONTENT_CHANGED in report.conflicts[0].conflict_types

    def test_tags_changed_conflict(self):
        """Same ID, different tags → TAGS_CHANGED conflict."""
        local = [_item("content", id="mem1", tags=["old"])]
        remote = [{"id": "mem1", "content": "content", "tags": ["new"], "importance": 0.5}]
        detector = ConflictDetector()
        report = detector.detect_from_dicts(local, remote)
        assert len(report.conflicts) == 1
        assert ConflictType.TAGS_CHANGED in report.conflicts[0].conflict_types

    def test_importance_changed_conflict(self):
        """Same ID, different importance → IMPORTANCE_CHANGED conflict."""
        local = [_item("content", id="mem1", importance=0.3)]
        remote = [{"id": "mem1", "content": "content", "tags": [], "importance": 0.9}]
        detector = ConflictDetector()
        report = detector.detect_from_dicts(local, remote)
        assert len(report.conflicts) == 1
        assert ConflictType.IMPORTANCE_CHANGED in report.conflicts[0].conflict_types

    def test_metadata_changed_conflict(self):
        """Same ID, different metadata → METADATA_CHANGED conflict."""
        local = [_item("content", id="mem1", metadata={"key": "old"})]
        remote = [{"id": "mem1", "content": "content", "tags": [], "importance": 0.5, "metadata": {"key": "new"}}]
        detector = ConflictDetector()
        report = detector.detect_from_dicts(local, remote)
        assert len(report.conflicts) == 1
        assert ConflictType.METADATA_CHANGED in report.conflicts[0].conflict_types

    def test_multiple_conflict_types(self):
        """Same ID, content + tags + importance differ → multiple conflict types."""
        local = [_item("content A", id="mem1", tags=["a"], importance=0.3)]
        remote = [{"id": "mem1", "content": "content B is quite different now", "tags": ["b"], "importance": 0.8}]
        detector = ConflictDetector()
        report = detector.detect_from_dicts(local, remote)
        assert len(report.conflicts) == 1
        c = report.conflicts[0]
        assert ConflictType.CONTENT_CHANGED in c.conflict_types
        assert ConflictType.TAGS_CHANGED in c.conflict_types
        assert ConflictType.IMPORTANCE_CHANGED in c.conflict_types

    def test_mixed_new_and_conflicts(self):
        """Mix of new memories and conflicts."""
        local = [
            _item("same content", id="mem1"),
            _item("will conflict", id="mem2", tags=["old"]),
        ]
        remote = [
            {"id": "mem1", "content": "same content", "tags": [], "importance": 0.5},
            {"id": "mem2", "content": "will conflict but different", "tags": ["new"], "importance": 0.5},
            {"id": "mem3", "content": "brand new memory"},
        ]
        detector = ConflictDetector()
        report = detector.detect_from_dicts(local, remote)
        assert report.total_remote == 3
        assert report.unchanged == 1  # mem1
        assert len(report.conflicts) == 1  # mem2
        assert report.new_memories == 1  # mem3

    def test_missing_remote_id(self):
        """Remote memory without ID → error."""
        detector = ConflictDetector()
        report = detector.detect_from_dicts([], [{"content": "no id"}])
        assert len(report.errors) == 1
        assert report.total_remote == 1


# ── Content Similarity ──────────────────────────────────

class TestContentSimilarity:
    """Test the content similarity heuristic."""

    def test_identical_strings(self):
        detector = ConflictDetector()
        assert detector._content_similar("hello world", "hello world") is True

    def test_empty_strings(self):
        detector = ConflictDetector()
        assert detector._content_similar("", "") is True
        assert detector._content_similar("hello", "") is False
        assert detector._content_similar("", "hello") is False

    def test_similar_enough(self):
        """Small changes don't trigger conflict."""
        detector = ConflictDetector(content_similarity_threshold=0.9)
        # Only 1 char difference in 20 chars = 95% similarity
        assert detector._content_similar("hello world 12345", "hello world 12346") is True

    def test_too_different(self):
        """Large changes trigger conflict."""
        detector = ConflictDetector(content_similarity_threshold=0.9)
        assert detector._content_similar("short", "completely different text") is False


# ── Resolution Strategies ───────────────────────────────

class TestResolution:
    """Test conflict resolution strategies."""

    def _make_conflict(self):
        """Create a test conflict."""
        return Conflict(
            memory_id="mem1",
            conflict_types=[ConflictType.CONTENT_CHANGED, ConflictType.TAGS_CHANGED],
            local_version={
                "id": "mem1",
                "content": "local version",
                "tags": ["a"],
                "importance": 0.3,
                "created_at": 1000.0,
                "accessed_at": 2000.0,
                "access_count": 5,
                "relevance_score": 0.5,
                "metadata": {"source": "local"},
                "ttl": None,
            },
            remote_version={
                "id": "mem1",
                "content": "remote version updated",
                "tags": ["b"],
                "importance": 0.8,
                "created_at": 1000.0,
                "accessed_at": 3000.0,
                "access_count": 10,
                "relevance_score": 0.7,
                "metadata": {"source": "remote"},
                "ttl": None,
            },
            local_content="local version",
            remote_content="remote version updated",
            local_tags=["a"],
            remote_tags=["b"],
            local_importance=0.3,
            remote_importance=0.8,
            local_metadata={"source": "local"},
            remote_metadata={"source": "remote"},
        )

    def test_local_wins(self):
        """LOCAL_WINS keeps local version."""
        detector = ConflictDetector()
        conflict = self._make_conflict()
        resolved = detector.resolve([conflict], ResolutionStrategy.LOCAL_WINS)
        assert resolved[0].resolution == ResolutionStrategy.LOCAL_WINS
        assert resolved[0].resolved_version["content"] == "local version"
        assert resolved[0].resolved_version["tags"] == ["a"]

    def test_remote_wins(self):
        """REMOTE_WINS keeps remote version."""
        detector = ConflictDetector()
        conflict = self._make_conflict()
        resolved = detector.resolve([conflict], ResolutionStrategy.REMOTE_WINS)
        assert resolved[0].resolution == ResolutionStrategy.REMOTE_WINS
        assert resolved[0].resolved_version["content"] == "remote version updated"
        assert resolved[0].resolved_version["tags"] == ["b"]

    def test_merge_tags_union(self):
        """MERGE unions tags."""
        detector = ConflictDetector()
        conflict = self._make_conflict()
        resolved = detector.resolve([conflict], ResolutionStrategy.MERGE)
        assert resolved[0].resolution == ResolutionStrategy.MERGE
        tags = resolved[0].resolved_version["tags"]
        assert "a" in tags
        assert "b" in tags

    def test_merge_max_importance(self):
        """MERGE takes max importance."""
        detector = ConflictDetector()
        conflict = self._make_conflict()
        resolved = detector.resolve([conflict], ResolutionStrategy.MERGE)
        assert resolved[0].resolved_version["importance"] == 0.8

    def test_merge_most_recent_content(self):
        """MERGE takes content from the most recently accessed version."""
        detector = ConflictDetector()
        conflict = self._make_conflict()
        # remote has accessed_at=3000 vs local 2000 → remote wins
        resolved = detector.resolve([conflict], ResolutionStrategy.MERGE)
        assert resolved[0].resolved_version["content"] == "remote version updated"

    def test_merge_metadata_union(self):
        """MERGE merges metadata (remote overrides)."""
        detector = ConflictDetector()
        conflict = self._make_conflict()
        resolved = detector.resolve([conflict], ResolutionStrategy.MERGE)
        meta = resolved[0].resolved_version["metadata"]
        assert meta["source"] == "remote"  # Remote overrides local

    def test_manual_no_resolution(self):
        """MANUAL leaves resolved_version as None."""
        detector = ConflictDetector()
        conflict = self._make_conflict()
        resolved = detector.resolve([conflict], ResolutionStrategy.MANUAL)
        assert resolved[0].resolution == ResolutionStrategy.MANUAL
        assert resolved[0].resolved_version is None


# ── Integration with MemOS ──────────────────────────────

class TestDetectWithMemOS:
    """Test conflict detection with a live MemOS instance."""

    def test_detect_with_live_store(self):
        """Detect conflicts against a live MemOS store."""
        memos = MemOS(backend="memory")

        # Learn a memory locally
        item = memos.learn("original content", tags=["old"], importance=0.3)
        memory_id = item.id

        # Create a remote envelope with a conflicting version
        remote = _envelope([{
            "id": memory_id,
            "content": "remote content is different",
            "tags": ["new"],
            "importance": 0.8,
        }])

        detector = ConflictDetector()
        report = detector.detect(memos, remote)
        assert len(report.conflicts) == 1
        assert ConflictType.CONTENT_CHANGED in report.conflicts[0].conflict_types
        assert ConflictType.TAGS_CHANGED in report.conflicts[0].conflict_types
        assert ConflictType.IMPORTANCE_CHANGED in report.conflicts[0].conflict_types

    def test_detect_new_memory(self):
        """Detect that a remote memory is new (no local match)."""
        memos = MemOS(backend="memory")
        memos.learn("local stuff")

        remote = _envelope([{"id": "new1", "content": "new memory"}])
        detector = ConflictDetector()
        report = detector.detect(memos, remote)
        assert report.new_memories == 1
        assert len(report.conflicts) == 0


class TestApplyWithMemOS:
    """Test applying sync with a live MemOS instance."""

    def test_apply_merge(self):
        """Apply merge strategy — local + remote merged."""
        memos = MemOS(backend="memory")
        item = memos.learn("original", tags=["local"], importance=0.3)
        memory_id = item.id

        remote = _envelope([{
            "id": memory_id,
            "content": "updated content from remote",
            "tags": ["remote"],
            "importance": 0.8,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at + 1000,
        }])

        detector = ConflictDetector()
        report = detector.detect(memos, remote)
        report = detector.apply(memos, report, ResolutionStrategy.MERGE)

        assert report.applied == 1
        # Check the merged state
        merged = memos._store.get(memory_id)
        assert merged is not None
        assert "local" in merged.tags
        assert "remote" in merged.tags
        assert merged.importance == 0.8

    def test_apply_new_memories(self):
        """Apply adds new remote memories."""
        memos = MemOS(backend="memory")

        remote = _envelope([{
            "id": "brand_new",
            "content": "new memory from remote",
            "tags": ["remote"],
            "importance": 0.5,
        }])

        detector = ConflictDetector()
        report = detector.detect(memos, remote)
        report = detector.apply(memos, report, ResolutionStrategy.MERGE)

        assert report.applied == 1
        item = memos._store.get("brand_new")
        assert item is not None
        assert item.content == "new memory from remote"

    def test_apply_local_wins_keeps_local(self):
        """LOCAL_WINS strategy preserves local content."""
        memos = MemOS(backend="memory")
        item = memos.learn("local content", tags=["local"], importance=0.5)
        memory_id = item.id

        remote = _envelope([{
            "id": memory_id,
            "content": "remote content different",
            "tags": ["remote"],
            "importance": 0.9,
        }])

        detector = ConflictDetector()
        report = detector.detect(memos, remote)
        report = detector.apply(memos, report, ResolutionStrategy.LOCAL_WINS)

        merged = memos._store.get(memory_id)
        assert merged.content == "local content"

    def test_apply_remote_wins_overwrites(self):
        """REMOTE_WINS strategy overwrites with remote content."""
        memos = MemOS(backend="memory")
        item = memos.learn("local content", tags=["local"], importance=0.5)
        memory_id = item.id

        remote = _envelope([{
            "id": memory_id,
            "content": "remote content wins",
            "tags": ["remote"],
            "importance": 0.9,
        }])

        detector = ConflictDetector()
        report = detector.detect(memos, remote)
        report = detector.apply(memos, report, ResolutionStrategy.REMOTE_WINS)

        merged = memos._store.get(memory_id)
        assert merged.content == "remote content wins"
        assert merged.tags == ["remote"]


# ── SyncReport serialization ────────────────────────────

class TestSyncReport:
    """Test SyncReport serialization."""

    def test_to_dict(self):
        report = SyncReport(
            total_remote=10,
            new_memories=3,
            unchanged=5,
            conflicts=[
                Conflict(memory_id="abc", conflict_types=[ConflictType.CONTENT_CHANGED]),
            ],
            applied=4,
            skipped=0,
        )
        d = report.to_dict()
        assert d["total_remote"] == 10
        assert d["new_memories"] == 3
        assert d["unchanged"] == 5
        assert d["conflict_count"] == 1
        assert d["applied"] == 4
        assert len(d["conflicts"]) == 1
        assert d["conflicts"][0]["conflict_types"] == ["content_changed"]

    def test_empty_report(self):
        report = SyncReport()
        d = report.to_dict()
        assert d["total_remote"] == 0
        assert d["conflict_count"] == 0
        assert d["errors"] == []


# ── Conflict serialization ──────────────────────────────

class TestConflictSerialization:
    """Test Conflict.to_dict."""

    def test_to_dict(self):
        c = Conflict(
            memory_id="abc123",
            conflict_types=[ConflictType.CONTENT_CHANGED, ConflictType.TAGS_CHANGED],
            local_content="old",
            remote_content="new",
            local_tags=["a"],
            remote_tags=["b"],
            local_importance=0.3,
            remote_importance=0.8,
        )
        d = c.to_dict()
        assert d["memory_id"] == "abc123"
        assert "content_changed" in d["conflict_types"]
        assert "tags_changed" in d["conflict_types"]
        assert d["local_content"] == "old"
        assert d["remote_content"] == "new"


# ── Envelope validation ─────────────────────────────────

class TestEnvelopeIntegration:
    """Test that envelope checksum validation works with conflict detection."""

    def test_valid_envelope(self):
        """Valid envelope passes checksum check."""
        env = _envelope([{"id": "1", "content": "test"}])
        assert env.validate() is True

    def test_tampered_envelope(self):
        """Tampered envelope fails checksum check."""
        env = _envelope([{"id": "1", "content": "test"}])
        env.memories[0]["content"] = "tampered"
        assert env.validate() is False
