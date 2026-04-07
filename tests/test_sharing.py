"""Tests for multi-agent memory sharing protocol."""

import json
import time
import pytest

from memos.sharing.models import (
    MemoryEnvelope,
    SharePermission,
    ShareRequest,
    ShareScope,
    ShareStatus,
)
from memos.sharing.engine import SharingEngine
from memos.core import MemOS
from memos.models import MemoryItem


# ── ShareRequest model tests ────────────────────────────────


class TestShareRequest:
    def test_create_default(self):
        req = ShareRequest(source_agent="a", target_agent="b")
        assert req.source_agent == "a"
        assert req.target_agent == "b"
        assert req.scope == ShareScope.ITEMS
        assert req.permission == SharePermission.READ
        assert req.status == ShareStatus.PENDING
        assert req.id  # auto-generated

    def test_to_dict_roundtrip(self):
        req = ShareRequest(
            source_agent="alpha",
            target_agent="beta",
            scope=ShareScope.TAG,
            scope_key="research",
            permission=SharePermission.READ_WRITE,
            expires_at=time.time() + 3600,
        )
        d = req.to_dict()
        restored = ShareRequest.from_dict(d)
        assert restored.source_agent == "alpha"
        assert restored.target_agent == "beta"
        assert restored.scope == ShareScope.TAG
        assert restored.scope_key == "research"
        assert restored.permission == SharePermission.READ_WRITE
        assert restored.expires_at is not None

    def test_custom_id(self):
        req = ShareRequest(id="custom-id", source_agent="a", target_agent="b")
        assert req.id == "custom-id"


# ── MemoryEnvelope tests ────────────────────────────────────


class TestMemoryEnvelope:
    def test_basic_envelope(self):
        env = MemoryEnvelope(
            source_agent="a",
            target_agent="b",
            memories=[
                {"id": "1", "content": "hello", "tags": ["test"]},
                {"id": "2", "content": "world", "tags": ["demo"]},
            ],
        )
        assert len(env.memories) == 2
        assert env.source_agent == "a"

    def test_checksum_validation(self):
        env = MemoryEnvelope(
            source_agent="a",
            target_agent="b",
            memories=[{"id": "1", "content": "test"}],
        )
        env.checksum = env.compute_checksum()
        assert env.validate()

    def test_checksum_tamper_detected(self):
        env = MemoryEnvelope(
            source_agent="a",
            target_agent="b",
            memories=[{"id": "1", "content": "test"}],
        )
        env.checksum = "tampered"
        assert not env.validate()

    def test_to_dict_roundtrip(self):
        env = MemoryEnvelope(
            source_agent="a",
            target_agent="b",
            memories=[{"id": "1", "content": "test"}],
            share_id="abc",
        )
        d = env.to_dict()
        assert "checksum" in d
        restored = MemoryEnvelope.from_dict(d)
        assert restored.source_agent == "a"
        assert restored.target_agent == "b"
        assert len(restored.memories) == 1
        assert restored.validate()

    def test_from_items_with_memory_items(self):
        items = [
            MemoryItem(id="1", content="hello", tags=["test"]),
            MemoryItem(id="2", content="world", tags=["demo"]),
        ]
        env = MemoryEnvelope.from_items(
            items, source_agent="a", target_agent="b", share_id="sh1"
        )
        assert len(env.memories) == 2
        assert env.checksum
        assert env.validate()

    def test_empty_envelope(self):
        env = MemoryEnvelope(source_agent="a", target_agent="b")
        assert len(env.memories) == 0
        assert env.validate()

    def test_no_checksum_skips_validation(self):
        env = MemoryEnvelope(
            source_agent="a",
            target_agent="b",
            memories=[{"id": "1", "content": "test"}],
            checksum="",
        )
        assert env.validate()


# ── SharingEngine tests ─────────────────────────────────────


class TestSharingEngine:
    def setup_method(self):
        self.engine = SharingEngine()

    def test_offer_creates_pending(self):
        req = self.engine.offer("a", "b", scope=ShareScope.TAG, scope_key="research")
        assert req.status == ShareStatus.PENDING
        assert req.source_agent == "a"
        assert req.target_agent == "b"

    def test_accept_transitions(self):
        req = self.engine.offer("a", "b")
        accepted = self.engine.accept(req.id, "b")
        assert accepted.status == ShareStatus.ACCEPTED
        assert accepted.accepted_at is not None

    def test_only_target_can_accept(self):
        req = self.engine.offer("a", "b")
        with pytest.raises(ValueError, match="Only target agent"):
            self.engine.accept(req.id, "c")

    def test_only_target_can_reject(self):
        req = self.engine.offer("a", "b")
        with pytest.raises(ValueError, match="Only target agent"):
            self.engine.reject(req.id, "c")

    def test_reject_transitions(self):
        req = self.engine.offer("a", "b")
        rejected = self.engine.reject(req.id, "b")
        assert rejected.status == ShareStatus.REJECTED

    def test_cannot_accept_non_pending(self):
        req = self.engine.offer("a", "b")
        self.engine.accept(req.id, "b")
        with pytest.raises(ValueError, match="not pending"):
            self.engine.accept(req.id, "b")

    def test_revoke_by_source(self):
        req = self.engine.offer("a", "b")
        self.engine.accept(req.id, "b")
        revoked = self.engine.revoke(req.id, "a")
        assert revoked.status == ShareStatus.REVOKED

    def test_only_source_can_revoke(self):
        req = self.engine.offer("a", "b")
        with pytest.raises(ValueError, match="Only source agent"):
            self.engine.revoke(req.id, "b")

    def test_cannot_revoke_rejected(self):
        req = self.engine.offer("a", "b")
        self.engine.reject(req.id, "b")
        with pytest.raises(ValueError, match="Cannot revoke"):
            self.engine.revoke(req.id, "a")

    def test_get_nonexistent(self):
        assert self.engine.get("nope") is None

    def test_list_shares_filter(self):
        self.engine.offer("a", "b")
        self.engine.offer("a", "c")
        req_bc = self.engine.offer("b", "c")
        self.engine.accept(req_bc.id, "c")

        all_shares = self.engine.list_shares()
        assert len(all_shares) == 3

        agent_a = self.engine.list_shares(agent="a")
        assert len(agent_a) == 2

        accepted = self.engine.list_shares(status=ShareStatus.ACCEPTED)
        assert len(accepted) == 1

    def test_list_shared_with(self):
        self.engine.offer("a", "b")
        req = self.engine.offer("c", "b")
        self.engine.accept(req.id, "b")

        shared = self.engine.list_shared_with("b")
        assert len(shared) == 1
        assert shared[0].source_agent == "c"

    def test_list_shared_by(self):
        req = self.engine.offer("a", "b")
        self.engine.accept(req.id, "b")
        self.engine.offer("a", "c")

        shared = self.engine.list_shared_by("a")
        assert len(shared) == 1

    def test_expiry(self):
        req = self.engine.offer("a", "b", expires_at=time.time() - 1)
        self.engine.accept(req.id, "b")
        self.engine.cleanup_expired()
        assert self.engine.get(req.id) is None

    def test_stats(self):
        self.engine.offer("a", "b")
        self.engine.offer("a", "c")
        stats = self.engine.stats()
        assert stats["total_shares"] == 2
        assert stats["pending_shares"] == 2
        assert stats["total_agents"] == 3

    def test_export_envelope(self):
        req = self.engine.offer("a", "b")
        self.engine.accept(req.id, "b")
        items = [MemoryItem(id="1", content="test")]
        env = self.engine.export_envelope(req.id, items)
        assert env.source_agent == "a"
        assert env.target_agent == "b"
        assert len(env.memories) == 1
        assert env.validate()

    def test_export_non_accepted_fails(self):
        req = self.engine.offer("a", "b")
        items = [MemoryItem(id="1", content="test")]
        with pytest.raises(ValueError, match="accepted"):
            self.engine.export_envelope(req.id, items)

    def test_import_envelope(self):
        env = MemoryEnvelope(
            source_agent="a",
            target_agent="b",
            memories=[{"id": "1", "content": "hello"}],
        )
        env.checksum = env.compute_checksum()
        result = SharingEngine.import_envelope(env)
        assert len(result) == 1

    def test_import_invalid_envelope_fails(self):
        env = MemoryEnvelope(
            source_agent="a",
            target_agent="b",
            memories=[{"id": "1", "content": "hello"}],
            checksum="bad",
        )
        with pytest.raises(ValueError, match="checksum"):
            SharingEngine.import_envelope(env)

    def test_can_read_permission(self):
        req = self.engine.offer("a", "b")
        assert not self.engine.can_read("a", "b")
        self.engine.accept(req.id, "b")
        assert self.engine.can_read("a", "b")

    def test_can_write_permission(self):
        req = self.engine.offer("a", "b", permission=SharePermission.READ_WRITE)
        self.engine.accept(req.id, "b")
        assert self.engine.can_write("a", "b")
        assert self.engine.can_read("a", "b")

    def test_read_only_no_write(self):
        req = self.engine.offer("a", "b", permission=SharePermission.READ)
        self.engine.accept(req.id, "b")
        assert self.engine.can_read("a", "b")
        assert not self.engine.can_write("a", "b")

    def test_clear(self):
        self.engine.offer("a", "b")
        self.engine.offer("c", "d")
        self.engine.clear()
        assert self.engine.stats()["total_shares"] == 0

    def test_get_accepted_permissions(self):
        req = self.engine.offer("a", "b", permission=SharePermission.ADMIN)
        self.engine.accept(req.id, "b")
        perm = self.engine.get_accepted_permissions("a", "b")
        assert perm == SharePermission.ADMIN


# ── Integration tests (MemOS + Sharing) ────────────────────


class TestMemOSSharing:
    """Integration tests using a single MemOS instance with agent_id switching.

    In production, agents communicate over HTTP. For unit tests,
    we switch agent_id to simulate two agents sharing the same engine.
    """

    def setup_method(self):
        self.memos = MemOS(backend="memory")

    def _as(self, agent_id: str, namespace: str = ""):
        """Switch to agent perspective."""
        self.memos.set_agent_id(agent_id)
        self.memos.namespace = namespace

    def test_full_share_lifecycle(self):
        # Agent A learns memories
        self._as("agent-a")
        self.memos.learn("Important research finding about AI", tags=["research", "ai"])
        self.memos.learn("Meeting notes from standup", tags=["work"])
        self.memos.learn("Random thought", tags=["personal"])

        # A offers to share research tag with B
        req = self.memos.share_with(
            "agent-b",
            scope=ShareScope.TAG,
            scope_key="research",
            permission=SharePermission.READ,
        )
        assert req.status == ShareStatus.PENDING

        # B accepts
        self._as("agent-b")
        req_b = self.memos.accept_share(req.id)
        assert req_b.status == ShareStatus.ACCEPTED

        # A exports
        self._as("agent-a")
        envelope = self.memos.export_shared(req.id)
        assert len(envelope.memories) == 1
        assert envelope.memories[0]["content"] == "Important research finding about AI"

        # B imports
        self._as("agent-b")
        learned = self.memos.import_shared(envelope)
        assert len(learned) == 1
        assert learned[0].content == "Important research finding about AI"

    def test_share_specific_items(self):
        self._as("agent-a")
        item1 = self.memos.learn("Memory 1", tags=["a"])
        self.memos.learn("Memory 2", tags=["b"])

        req = self.memos.share_with(
            "agent-b",
            scope=ShareScope.ITEMS,
            scope_key=item1.id,
        )

        self._as("agent-b")
        self.memos.accept_share(req.id)

        self._as("agent-a")
        envelope = self.memos.export_shared(req.id)
        assert len(envelope.memories) == 1

    def test_share_reject_flow(self):
        self._as("agent-a")
        req = self.memos.share_with("agent-b", scope=ShareScope.NAMESPACE)

        self._as("agent-b")
        self.memos.reject_share(req.id)

        shares = self.memos.list_shares(status=ShareStatus.REJECTED)
        assert len(shares) == 1

    def test_share_revoke_flow(self):
        self._as("agent-a")
        req = self.memos.share_with("agent-b")

        self._as("agent-b")
        self.memos.accept_share(req.id)

        self._as("agent-a")
        self.memos.revoke_share(req.id)

        assert not self.memos.sharing().can_read("agent-a", "agent-b")

    def test_sharing_stats(self):
        self._as("agent-a")
        self.memos.share_with("agent-b")
        self.memos.share_with("agent-c")
        stats = self.memos.sharing_stats()
        assert stats["total_shares"] == 2
        assert stats["pending_shares"] == 2

    def test_envelope_portability(self):
        self._as("agent-a")
        self.memos.learn("Test content", tags=["test"])
        req = self.memos.share_with("agent-b", scope=ShareScope.TAG, scope_key="test")

        self._as("agent-b")
        self.memos.accept_share(req.id)

        self._as("agent-a")
        envelope = self.memos.export_shared(req.id)

        # Serialize → deserialize → import
        json_str = json.dumps(envelope.to_dict())
        restored = MemoryEnvelope.from_dict(json.loads(json_str))
        assert restored.validate()

        self._as("agent-b")
        learned = self.memos.import_shared(restored)
        assert len(learned) == 1

    def test_list_shares_endpoint(self):
        self._as("agent-a")
        self.memos.share_with("agent-b")
        self.memos.share_with("agent-c")
        all_shares = self.memos.list_shares()
        assert len(all_shares) == 2

        filtered = self.memos.list_shares(agent="agent-b")
        assert any(s.target_agent == "agent-b" for s in filtered)

    def test_namespace_scope_share(self):
        self._as("agent-a")
        self.memos.grant_namespace_access("agent-a", "research", "owner")
        self.memos.namespace = "research"
        self.memos.learn("Research finding", tags=["ai"])

        req = self.memos.share_with(
            "agent-b",
            scope=ShareScope.NAMESPACE,
            scope_key="research",
        )

        self._as("agent-b")
        self.memos.accept_share(req.id)

        self._as("agent-a")
        self.memos.namespace = "research"
        envelope = self.memos.export_shared(req.id)
        assert len(envelope.memories) == 1


# ── Edge case tests ─────────────────────────────────────────


class TestSharingEdgeCases:
    def test_accept_expired_share(self):
        engine = SharingEngine()
        req = engine.offer("a", "b", expires_at=time.time() - 10)
        engine.accept(req.id, "b")
        engine.cleanup_expired()
        assert engine.get(req.id) is None

    def test_double_accept_fails(self):
        engine = SharingEngine()
        req = engine.offer("a", "b")
        engine.accept(req.id, "b")
        with pytest.raises(ValueError):
            engine.accept(req.id, "b")

    def test_revoke_pending(self):
        engine = SharingEngine()
        req = engine.offer("a", "b")
        revoked = engine.revoke(req.id, "a")
        assert revoked.status == ShareStatus.REVOKED

    def test_export_empty_scope(self):
        memos = MemOS(backend="memory")
        memos.set_agent_id("a")
        req = memos.share_with("b", scope=ShareScope.TAG, scope_key="nonexistent")
        memos.set_agent_id("b")
        memos.accept_share(req.id)
        memos.set_agent_id("a")
        envelope = memos.export_shared(req.id)
        assert len(envelope.memories) == 0

    def test_import_envelope_empty_memories(self):
        env = MemoryEnvelope(source_agent="a", target_agent="b", memories=[])
        env.checksum = env.compute_checksum()
        with pytest.raises(ValueError, match="no memories"):
            SharingEngine.import_envelope(env)

    def test_share_id_unique(self):
        engine = SharingEngine()
        req1 = engine.offer("a", "b")
        time.sleep(0.01)
        req2 = engine.offer("a", "b")
        assert req1.id != req2.id

    def test_admin_can_read_and_write(self):
        engine = SharingEngine()
        req = engine.offer("a", "b", permission=SharePermission.ADMIN)
        engine.accept(req.id, "b")
        assert engine.can_read("a", "b")
        assert engine.can_write("a", "b")

    def test_reject_non_pending_fails(self):
        engine = SharingEngine()
        req = engine.offer("a", "b")
        engine.reject(req.id, "b")
        with pytest.raises(ValueError, match="not pending"):
            engine.reject(req.id, "b")
