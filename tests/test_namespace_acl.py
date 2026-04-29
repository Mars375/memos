"""Tests for namespace access control (RBAC)."""

import time

import pytest

from memos import MemOS
from memos._namespace_facade import acl_sidecar_path
from memos.namespaces.acl import NamespaceACL, NamespacePolicy, Role


class TestRole:
    """Test Role enum."""

    def test_role_values(self):
        assert Role.OWNER.value == "owner"
        assert Role.WRITER.value == "writer"
        assert Role.READER.value == "reader"
        assert Role.DENIED.value == "denied"

    def test_role_from_string(self):
        assert Role("owner") == Role.OWNER
        assert Role("writer") == Role.WRITER
        assert Role("reader") == Role.READER
        assert Role("denied") == Role.DENIED


class TestNamespacePolicy:
    """Test policy data model."""

    def test_to_dict(self):
        policy = NamespacePolicy(
            agent_id="agent-1",
            namespace="production",
            role=Role.WRITER,
            granted_by="admin",
            granted_at=1000.0,
        )
        d = policy.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["namespace"] == "production"
        assert d["role"] == "writer"

    def test_from_dict(self):
        data = {
            "agent_id": "agent-2",
            "namespace": "staging",
            "role": "reader",
            "granted_by": "",
            "granted_at": 0.0,
        }
        policy = NamespacePolicy.from_dict(data)
        assert policy.agent_id == "agent-2"
        assert policy.role == Role.READER

    def test_roundtrip(self):
        original = NamespacePolicy(
            agent_id="a",
            namespace="ns",
            role=Role.OWNER,
            granted_at=time.time(),
        )
        restored = NamespacePolicy.from_dict(original.to_dict())
        assert restored.agent_id == original.agent_id
        assert restored.role == original.role


class TestNamespaceACL:
    """Test ACL manager."""

    def setup_method(self):
        self.acl = NamespaceACL()

    def test_acl_sidecar_path_preserves_store_path_semantics(self):
        assert acl_sidecar_path(".memos/store.json") == ".memos/store.acl.json"
        assert acl_sidecar_path("~/.memos/store.json") == "~/.memos/store.acl.json"
        assert acl_sidecar_path("store") == "store.acl.json"

    def test_grant_and_check(self):
        self.acl.grant("agent-a", "production", Role.WRITER)
        self.acl.check("agent-a", "production", "write")
        self.acl.check("agent-a", "production", "read")
        self.acl.check("agent-a", "production", "delete")

    def test_grant_reader_no_write(self):
        self.acl.grant("agent-b", "production", Role.READER)
        self.acl.check("agent-b", "production", "read")

        with pytest.raises(PermissionError):
            self.acl.check("agent-b", "production", "write")

    def test_grant_denied_blocks_all(self):
        self.acl.grant("agent-c", "production", Role.WRITER)
        self.acl.deny("agent-c", "production")

        with pytest.raises(PermissionError):
            self.acl.check("agent-c", "production", "read")

        with pytest.raises(PermissionError):
            self.acl.check("agent-c", "production", "write")

    def test_no_access_raises(self):
        with pytest.raises(PermissionError):
            self.acl.check("unknown", "production", "read")

    def test_revoke(self):
        self.acl.grant("agent-d", "production", Role.WRITER)
        removed = self.acl.revoke("agent-d", "production")
        assert removed is not None
        assert removed.role == Role.WRITER

        with pytest.raises(PermissionError):
            self.acl.check("agent-d", "production", "read")

    def test_revoke_nonexistent(self):
        result = self.acl.revoke("nobody", "nowhere")
        assert result is None

    def test_get_role(self):
        self.acl.grant("agent-e", "ns1", Role.OWNER)
        assert self.acl.get_role("agent-e", "ns1") == Role.OWNER

    def test_get_role_nonexistent(self):
        assert self.acl.get_role("unknown", "ns1") is None

    def test_has_permission(self):
        self.acl.grant("agent-f", "ns1", Role.WRITER)
        assert self.acl.has_permission("agent-f", "ns1", "write")
        assert self.acl.has_permission("agent-f", "ns1", "read")
        assert not self.acl.has_permission("agent-f", "ns1", "manage")

    def test_owner_has_all_permissions(self):
        self.acl.grant("admin", "ns1", Role.OWNER)
        assert self.acl.has_permission("admin", "ns1", "read")
        assert self.acl.has_permission("admin", "ns1", "write")
        assert self.acl.has_permission("admin", "ns1", "delete")
        assert self.acl.has_permission("admin", "ns1", "manage")
        assert self.acl.has_permission("admin", "ns1", "destroy")

    def test_namespaces_for(self):
        self.acl.grant("agent-g", "ns1", Role.WRITER)
        self.acl.grant("agent-g", "ns2", Role.READER)
        self.acl.grant("agent-g", "ns3", Role.DENIED)

        ns = self.acl.namespaces_for("agent-g")
        assert "ns1" in ns
        assert "ns2" in ns
        assert "ns3" not in ns  # DENIED excluded

    def test_agents_in(self):
        self.acl.grant("a1", "production", Role.OWNER)
        self.acl.grant("a2", "production", Role.WRITER)
        self.acl.grant("a3", "production", Role.READER)
        self.acl.grant("a4", "production", Role.DENIED)

        agents = self.acl.agents_in("production")
        assert len(agents) == 3  # DENIED excluded
        ids = [a[0] for a in agents]
        assert "a1" in ids
        assert "a2" in ids
        assert "a3" in ids
        assert "a4" not in ids

    def test_list_policies(self):
        self.acl.grant("a1", "ns1", Role.WRITER)
        self.acl.grant("a2", "ns2", Role.READER)

        all_policies = self.acl.list_policies()
        assert len(all_policies) == 2

        ns1_policies = self.acl.list_policies(namespace="ns1")
        assert len(ns1_policies) == 1
        assert ns1_policies[0].agent_id == "a1"

    def test_dump_and_load_policies(self):
        self.acl.grant("a1", "ns1", Role.WRITER, granted_by="admin")
        self.acl.grant("a2", "ns2", Role.READER)

        restored = NamespaceACL()
        count = restored.load_policies(self.acl.dump_policies())

        assert count == 2
        assert restored.get_role("a1", "ns1") == Role.WRITER
        assert restored.get_policy("a1", "ns1").granted_by == "admin"
        assert restored.get_role("a2", "ns2") == Role.READER

    def test_dump_policies_excludes_expired(self):
        self.acl.grant("expired", "ns", Role.WRITER, expires_at=time.time() - 1)
        self.acl.grant("active", "ns", Role.READER)

        policies = self.acl.dump_policies()

        assert len(policies) == 1
        assert policies[0]["agent_id"] == "active"

    def test_stats(self):
        self.acl.grant("a1", "ns1", Role.OWNER)
        self.acl.grant("a2", "ns1", Role.WRITER)
        self.acl.grant("a3", "ns2", Role.READER)

        stats = self.acl.stats()
        assert stats["total_policies"] == 3
        assert stats["total_agents"] == 3
        assert stats["total_namespaces"] == 2
        assert stats["role_distribution"]["owner"] == 1
        assert stats["role_distribution"]["writer"] == 1

    def test_grant_updates_existing(self):
        self.acl.grant("agent", "ns", Role.READER)
        assert self.acl.get_role("agent", "ns") == Role.READER

        self.acl.grant("agent", "ns", Role.WRITER)
        assert self.acl.get_role("agent", "ns") == Role.WRITER

    def test_clear(self):
        self.acl.grant("a", "ns", Role.WRITER)
        self.acl.clear()
        assert self.acl.stats()["total_policies"] == 0

    def test_expiration(self):
        # Grant with past expiration
        self.acl.grant("agent", "ns", Role.WRITER, expires_at=time.time() - 100)
        # Should return None (expired)
        assert self.acl.get_role("agent", "ns") is None
        assert not self.acl.has_permission("agent", "ns", "read")

    def test_cleanup_expired(self):
        self.acl.grant("a1", "ns", Role.WRITER, expires_at=time.time() - 100)
        self.acl.grant("a2", "ns", Role.WRITER)  # No expiration
        self.acl.grant("a3", "ns", Role.WRITER, expires_at=time.time() + 3600)

        removed = self.acl.cleanup_expired()
        assert removed == 1
        assert self.acl.stats()["total_policies"] == 2

    def test_get_policy(self):
        self.acl.grant("agent", "ns", Role.WRITER, granted_by="admin")
        policy = self.acl.get_policy("agent", "ns")
        assert policy is not None
        assert policy.granted_by == "admin"

    def test_thread_safety(self):
        import threading

        errors = []

        def writer(i):
            try:
                self.acl.grant(f"agent-{i}", "ns", Role.WRITER)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert self.acl.stats()["total_policies"] == 20


class TestMemOSACLIntegration:
    """Test MemOS with namespace ACL enforcement."""

    def test_agent_with_write_access(self):
        mem = MemOS(backend="memory")
        mem.set_agent_id("agent-a")
        mem.namespace = "production"

        # Grant writer access
        mem.acl.grant("agent-a", "production", Role.WRITER)
        item = mem.learn("test memory")
        assert item is not None

    def test_acl_blocks_unauthorized_write(self):
        mem = MemOS(backend="memory")
        mem.set_agent_id("intruder")
        mem.namespace = "production"

        # Grant reader access to the namespace
        mem.acl.grant("intruder", "production", Role.READER)

        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.learn("should fail")

    def test_acl_blocks_unauthorized_read(self):
        mem = MemOS(backend="memory")
        mem.set_agent_id("spy")
        mem.namespace = "production"

        # Grant writer but then explicitly deny
        mem.acl.grant("spy", "production", Role.WRITER)
        mem.acl.deny("spy", "production")

        with pytest.raises(PermissionError):
            mem.recall("anything")

    def test_acl_allows_authorized_operations(self):
        mem = MemOS(backend="memory")
        mem.set_agent_id("worker")
        mem.namespace = "production"

        mem.acl.grant("worker", "production", Role.WRITER)

        # write
        item = mem.learn("authorized memory", tags=["test"])
        assert item is not None

        # read
        results = mem.recall("authorized")
        assert len(results) >= 1

        # delete
        assert mem.forget(item.id)

    def test_acl_grant_via_api(self):
        mem = MemOS(backend="memory")
        policy = mem.grant_namespace_access(
            agent_id="new-agent",
            namespace="staging",
            role="writer",
            granted_by="admin",
        )
        assert policy["agent_id"] == "new-agent"
        assert policy["role"] == "writer"

    def test_acl_revoke_via_api(self):
        mem = MemOS(backend="memory")
        mem.grant_namespace_access("agent-x", "ns1", "writer")
        assert mem.revoke_namespace_access("agent-x", "ns1")
        assert not mem.revoke_namespace_access("agent-x", "ns1")

    def test_agent_id_is_initialized(self):
        mem = MemOS(backend="memory")

        assert mem.agent_id == ""

        mem.set_agent_id("agent-a")
        assert mem.agent_id == "agent-a"

        mem.set_agent_id("")
        assert mem.agent_id == ""

    def test_acl_policies_persist_with_json_backend(self, tmp_path):
        store_path = tmp_path / "store.json"
        mem = MemOS(backend="json", persist_path=str(store_path))
        mem.acl.grant("agent-a", "production", Role.WRITER, granted_by="admin")

        reopened = MemOS(backend="json", persist_path=str(store_path))

        assert reopened.acl.get_role("agent-a", "production") == Role.WRITER
        policy = reopened.acl.get_policy("agent-a", "production")
        assert policy is not None
        assert policy.granted_by == "admin"
        assert (tmp_path / "store.acl.json").exists()

    def test_acl_clear_persists_with_json_backend(self, tmp_path):
        store_path = tmp_path / "store.json"
        mem = MemOS(backend="json", persist_path=str(store_path))
        mem.acl.grant("agent-a", "production", Role.WRITER)
        mem.acl.clear()

        reopened = MemOS(backend="json", persist_path=str(store_path))

        assert reopened.list_namespace_policies() == []

    def test_acl_revoke_persists_with_json_backend(self, tmp_path):
        store_path = tmp_path / "store.json"
        mem = MemOS(backend="json", persist_path=str(store_path))
        mem.grant_namespace_access("agent-a", "production", "writer")
        mem.revoke_namespace_access("agent-a", "production")

        reopened = MemOS(backend="json", persist_path=str(store_path))

        assert reopened.acl.get_role("agent-a", "production") is None

    def test_denied_acl_policy_persists_with_json_backend(self, tmp_path):
        store_path = tmp_path / "store.json"
        mem = MemOS(backend="json", persist_path=str(store_path))
        mem.grant_namespace_access("agent-a", "production", "denied")

        reopened = MemOS(backend="json", persist_path=str(store_path))

        assert reopened.acl.get_role("agent-a", "production") == Role.DENIED

    def test_list_namespace_policies(self):
        mem = MemOS(backend="memory")
        mem.grant_namespace_access("a1", "ns1", "owner")
        mem.grant_namespace_access("a2", "ns1", "writer")
        mem.grant_namespace_access("a3", "ns2", "reader")

        all_policies = mem.list_namespace_policies()
        assert len(all_policies) == 3

        ns1_policies = mem.list_namespace_policies(namespace="ns1")
        assert len(ns1_policies) == 2

    def test_namespace_acl_stats(self):
        mem = MemOS(backend="memory")
        mem.grant_namespace_access("a1", "ns1", "owner")
        mem.grant_namespace_access("a2", "ns1", "writer")

        stats = mem.namespace_acl_stats()
        assert stats["total_policies"] == 2
        assert stats["total_agents"] == 2

    def test_empty_namespace_bypasses_acl(self):
        """Empty namespace (global) bypasses ACL checks."""
        mem = MemOS(backend="memory")
        mem.set_agent_id("agent")

        # No namespace set — should work fine
        item = mem.learn("global memory")
        assert item is not None
        assert len(mem.recall("global")) >= 1

    def test_no_agent_id_bypasses_acl(self):
        """No agent_id set — ACL checks are skipped."""
        mem = MemOS(backend="memory")
        mem.namespace = "production"

        # No set_agent_id called — should work fine
        item = mem.learn("works without agent id")
        assert item is not None

    def test_batch_learn_respects_acl(self):
        mem = MemOS(backend="memory")
        mem.set_agent_id("reader-agent")
        mem.namespace = "production"
        mem.acl.grant("reader-agent", "production", Role.READER)

        with pytest.raises(PermissionError, match="lacks 'write'"):
            mem.batch_learn([{"content": "test"}])

    def test_search_respects_acl(self):
        mem = MemOS(backend="memory")
        mem.set_agent_id("denied-agent")
        mem.namespace = "production"
        mem.acl.grant("denied-agent", "production", Role.DENIED)

        with pytest.raises(PermissionError):
            mem.search("anything")

    def test_forget_respects_acl(self):
        mem = MemOS(backend="memory")
        mem.set_agent_id("reader-agent")
        mem.namespace = "production"
        mem.acl.grant("reader-agent", "production", Role.READER)

        with pytest.raises(PermissionError, match="lacks 'delete'"):
            mem.forget("some-id")
