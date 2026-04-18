"""Regression tests: facade methods enforce _check_acl gates.

These tests prove that every public method on the non-maintenance facades
(IO, Versioning, Feedback, Sharing) raises PermissionError when the agent
lacks the required ACL permission on a namespaced store.
"""

import pytest

from memos import MemOS
from memos.namespaces.acl import Role


def _namespaced_mem(agent_id: str, role: Role) -> MemOS:
    mem = MemOS(backend="memory")
    mem.set_agent_id(agent_id)
    mem.namespace = "test-ns"
    mem.acl.grant(agent_id, "test-ns", role)
    return mem


def _mem_with_item(agent_id: str) -> tuple[MemOS, str]:
    mem = _namespaced_mem(agent_id, Role.WRITER)
    item = mem.learn("seed content", tags=["seed"])
    return mem, item.id


# ── IOFacade ───────────────────────────────────────────────


class TestIOFacadeACL:
    def test_export_json_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.export_json()

    def test_export_json_allows_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        result = mem.export_json()
        assert "memories" in result

    def test_import_json_blocks_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.import_json({"memories": []})

    def test_import_json_allows_writer(self):
        mem = _namespaced_mem("writer-agent", Role.WRITER)
        result = mem.import_json({"memories": []})
        assert result["imported"] == 0

    def test_export_parquet_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.export_parquet("/tmp/nope.parquet")

    def test_import_parquet_blocks_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.import_parquet("/tmp/nope.parquet")

    def test_migrate_to_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.migrate_to("memory")

    def test_migrate_to_allows_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        result = mem.migrate_to("memory", dry_run=True)
        assert result is not None


# ── VersioningFacade ──────────────────────────────────────


class TestVersioningFacadeACL:
    def test_history_blocks_denied(self):
        mem, item_id = _mem_with_item("writer-agent")
        mem.acl.deny("writer-agent", "test-ns")
        with pytest.raises(PermissionError):
            mem.history(item_id)

    def test_get_version_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.get_version("some-id", 1)

    def test_diff_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.diff("some-id", 1, 2)

    def test_diff_latest_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.diff_latest("some-id")

    def test_recall_at_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.recall_at("query", 0.0)

    def test_snapshot_at_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.snapshot_at(0.0)

    def test_rollback_blocks_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.rollback("some-id", 1)

    def test_versioning_stats_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.versioning_stats()

    def test_versioning_gc_blocks_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        with pytest.raises(PermissionError, match="lacks 'delete'"):
            mem.versioning_gc()

    def test_history_allows_reader(self):
        mem, item_id = _mem_with_item("writer-agent")
        mem.acl.grant("writer-agent", "test-ns", Role.READER)
        history = mem.history(item_id)
        assert isinstance(history, list)

    def test_versioning_stats_allows_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        stats = mem.versioning_stats()
        assert isinstance(stats, dict)


# ── FeedbackFacade ────────────────────────────────────────


class TestFeedbackFacadeACL:
    def test_record_feedback_blocks_reader(self):
        mem, item_id = _mem_with_item("writer-agent")
        mem.acl.grant("writer-agent", "test-ns", Role.READER)
        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.record_feedback(item_id, "relevant")

    def test_get_feedback_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.get_feedback()

    def test_feedback_stats_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.feedback_stats()

    def test_record_feedback_allows_writer(self):
        mem = _namespaced_mem("writer-agent", Role.WRITER)
        item = mem.learn("feedback target")
        entry = mem.record_feedback(item.id, "relevant")
        assert entry.feedback == "relevant"

    def test_get_feedback_allows_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        result = mem.get_feedback()
        assert isinstance(result, list)


# ── SharingFacade ─────────────────────────────────────────


class TestSharingFacadeACL:
    def test_share_with_blocks_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.share_with("other-agent")

    def test_accept_share_blocks_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.accept_share("share-123")

    def test_reject_share_blocks_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.reject_share("share-123")

    def test_revoke_share_blocks_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.revoke_share("share-123")

    def test_export_shared_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.export_shared("share-123")

    def test_import_shared_blocks_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.import_shared(object())

    def test_list_shares_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.list_shares()

    def test_sharing_stats_blocks_denied(self):
        mem = _namespaced_mem("denied-agent", Role.DENIED)
        with pytest.raises(PermissionError):
            mem.sharing_stats()

    def test_list_shares_allows_reader(self):
        mem = _namespaced_mem("reader-agent", Role.READER)
        result = mem.list_shares()
        assert isinstance(result, list)
