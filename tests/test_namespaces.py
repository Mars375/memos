"""Tests for multi-agent namespace isolation."""

from memos import MemOS


class TestNamespaceIsolation:
    """Verify agents with different namespaces can't see each other's memories."""

    def setup_method(self):
        self.global_mem = MemOS(backend="memory")
        self.agent_a = MemOS(backend="memory")
        self.agent_a.namespace = "agent-a"
        self.agent_b = MemOS(backend="memory")
        self.agent_b.namespace = "agent-b"

    def test_learn_isolated(self):
        self.agent_a.learn("Alice likes cats", tags=["preference"])
        self.agent_b.learn("Bob likes dogs", tags=["preference"])

        assert len(self.agent_a.recall("likes")) == 1
        assert self.agent_a.recall("likes")[0].item.content == "Alice likes cats"
        assert len(self.agent_b.recall("likes")) == 1
        assert self.agent_b.recall("likes")[0].item.content == "Bob likes dogs"

    def test_global_separate(self):
        self.global_mem.learn("Global memory")
        self.agent_a.learn("Agent A memory")

        assert len(self.agent_a.recall("memory")) == 1
        assert self.agent_a.recall("memory")[0].item.content == "Agent A memory"

    def test_stats_scoped(self):
        self.agent_a.learn("A1", tags=["x"])
        self.agent_a.learn("A2", tags=["x"])
        self.agent_b.learn("B1")

        stats_a = self.agent_a.stats()
        stats_b = self.agent_b.stats()
        assert stats_a.total_memories == 2
        assert stats_b.total_memories == 1

    def test_forget_scoped(self):
        item = self.agent_a.learn("secret A")
        self.agent_b.learn("secret B")

        assert self.agent_a.forget(item.id)
        assert self.agent_a.stats().total_memories == 0
        assert self.agent_b.stats().total_memories == 1

    def test_prune_scoped(self):
        self.agent_a.learn("keep me", importance=0.9)
        self.agent_b.learn("decay me", importance=0.1)

        pruned_a = self.agent_a.prune(threshold=0.05)
        assert len(pruned_a) == 0
        assert self.agent_b.stats().total_memories == 1

    def test_search_scoped(self):
        self.agent_a.learn("alpha data", tags=["alpha"])
        self.agent_b.learn("beta data", tags=["beta"])

        assert len(self.agent_a.search("data")) == 1
        assert self.agent_a.search("data")[0].content == "alpha data"

    def test_list_namespaces(self):
        from memos.storage.memory_backend import InMemoryBackend
        shared = InMemoryBackend()
        a = MemOS(backend="memory")
        a._store = shared
        a._retrieval._store = shared
        a.namespace = "agent-a"
        b = MemOS(backend="memory")
        b._store = shared
        b._retrieval._store = shared
        b.namespace = "agent-b"
        a.learn("A")
        b.learn("B")
        ns = a.list_namespaces()
        assert "agent-a" in ns
        assert "agent-b" in ns

    def test_cross_namespace_invisible(self):
        """Agent A cannot recall Agent B's memories by content match."""
        self.agent_a.learn("hidden from B")
        assert len(self.agent_b.recall("hidden")) == 0

    def test_empty_namespace_is_global(self):
        mem = MemOS(backend="memory")
        mem.namespace = ""
        mem.learn("global item")
        assert len(mem.recall("global")) == 1

    def test_namespace_setter(self):
        mem = MemOS(backend="memory")
        assert mem.namespace == ""
        mem.namespace = "test-ns"
        assert mem.namespace == "test-ns"
        mem.namespace = ""
        assert mem.namespace == ""
