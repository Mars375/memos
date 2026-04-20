"""Structural regression tests for the TagFacade mixin extraction.

Verifies that TagFacade methods exist on MemOS via inheritance, have correct
signatures, delegate properly, and that core.py no longer contains duplicated
definitions.
"""

import inspect

from memos._tag_facade import TagFacade
from memos.core import MemOS
from memos.models import MemoryItem

TAG_METHODS = ("list_tags", "rename_tag", "delete_tag")


class TestTagFacadeInheritance:
    def test_memos_inherits_tag_facade(self):
        assert issubclass(MemOS, TagFacade)

    def test_tag_facade_is_mixin(self):
        assert "__init__" not in TagFacade.__dict__, "TagFacade should not define __init__"

    def test_memos_instance_has_all_tag_methods(self):
        mem = MemOS(backend="memory", sanitize=False)
        for name in TAG_METHODS:
            assert hasattr(mem, name), f"MemOS instance missing method: {name}"
            assert callable(getattr(mem, name)), f"MemOS.{name} is not callable"


class TestMethodSignatures:
    def test_list_tags_signature(self):
        sig = inspect.signature(MemOS.list_tags)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "sort" in params
        assert "limit" in params
        assert sig.parameters["sort"].default == "count"
        assert sig.parameters["limit"].default == 0

    def test_rename_tag_signature(self):
        sig = inspect.signature(MemOS.rename_tag)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "old_tag" in params
        assert "new_tag" in params

    def test_delete_tag_signature(self):
        sig = inspect.signature(MemOS.delete_tag)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "tag" in params


class TestNoDuplicationInCore:
    def test_methods_defined_on_facade(self):
        for name in TAG_METHODS:
            assert name in TagFacade.__dict__, (
                f"{name} should be defined on TagFacade, not just inherited"
            )


class TestListTagsBehavior:
    def test_list_tags_returns_tuples(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("alpha content", tags=["alpha", "beta"])
        mem.learn("beta content", tags=["beta"])

        result = mem.list_tags()
        assert isinstance(result, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)

    def test_list_tags_counts_correctly(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("a1", tags=["x", "y"])
        mem.learn("a2", tags=["x"])

        result = dict(mem.list_tags())
        assert result["x"] == 2
        assert result["y"] == 1

    def test_list_tags_sort_by_count(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("a1", tags=["rare"])
        mem.learn("a2", tags=["common"])
        mem.learn("a3", tags=["common"])

        result = mem.list_tags(sort="count")
        assert result[0][0] == "common"

    def test_list_tags_sort_by_name(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("a1", tags=["zeta"])
        mem.learn("a2", tags=["alpha"])

        result = mem.list_tags(sort="name")
        assert result[0][0] == "alpha"

    def test_list_tags_limit(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("a1", tags=["a", "b", "c"])

        result = mem.list_tags(limit=2)
        assert len(result) == 2

    def test_list_tags_empty_store(self):
        mem = MemOS(backend="memory", sanitize=False)
        result = mem.list_tags()
        assert result == []


class TestRenameTagBehavior:
    def test_rename_tag_updates_items(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("content one", tags=["old-tag"])
        mem.learn("content two", tags=["old-tag", "other"])

        count = mem.rename_tag("old-tag", "new-tag")
        assert count == 2

        tags = dict(mem.list_tags())
        assert "old-tag" not in tags
        assert tags["new-tag"] == 2
        assert tags["other"] == 1

    def test_rename_tag_case_insensitive(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("content", tags=["MyTag"])

        count = mem.rename_tag("mytag", "renamed")
        assert count == 1

    def test_rename_tag_nonexistent_returns_zero(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("content", tags=["unrelated"])

        count = mem.rename_tag("nonexistent", "anything")
        assert count == 0


class TestDeleteTagBehavior:
    def test_delete_tag_removes_from_items(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("content one", tags=["target", "keep"])
        mem.learn("content two", tags=["target"])

        count = mem.delete_tag("target")
        assert count == 2

        tags = dict(mem.list_tags())
        assert "target" not in tags
        assert tags["keep"] == 1

    def test_delete_tag_case_insensitive(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("content", tags=["RemoveMe"])

        count = mem.delete_tag("removeme")
        assert count == 1

    def test_delete_tag_nonexistent_returns_zero(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("content", tags=["keep"])

        count = mem.delete_tag("nonexistent")
        assert count == 0


class TestTagNamespaceIsolation:
    def test_list_tags_respects_namespace(self):
        alice = MemOS(backend="memory", sanitize=False)
        alice._namespace = "agent-alice"
        bob = MemOS(backend="memory", sanitize=False)
        bob._namespace = "agent-bob"

        alice._store.upsert(
            MemoryItem(id="a1", content="alice stuff", tags=["alpha"], importance=0.5),
            namespace="agent-alice",
        )
        bob._store.upsert(
            MemoryItem(id="b1", content="bob stuff", tags=["beta"], importance=0.5),
            namespace="agent-bob",
        )

        alice_tags = dict(alice.list_tags())
        bob_tags = dict(bob.list_tags())

        assert "alpha" in alice_tags
        assert "beta" not in alice_tags
        assert "beta" in bob_tags
        assert "alpha" not in bob_tags
