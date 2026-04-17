"""Tests for MCP pre/post hooks — P4."""

from __future__ import annotations

from unittest.mock import MagicMock

from memos.mcp_hooks import (
    MCPHookRegistry,
    _extract_and_store_facts,
    create_default_registry,
    hook_auto_capture_kg,
)

# ---------------------------------------------------------------------------
# MCPHookRegistry unit tests
# ---------------------------------------------------------------------------


class TestMCPHookRegistry:
    def test_register_and_run_post(self):
        registry = MCPHookRegistry()
        called = []

        def my_hook(tool, args, result, memos):
            called.append(tool)
            return {**result, "hooked": True}

        registry.register_post("memory_save", my_hook)
        result = registry.run_post("memory_save", {}, {"content": []}, None)
        assert called == ["memory_save"]
        assert result["hooked"] is True

    def test_register_and_run_pre_short_circuit(self):
        registry = MCPHookRegistry()

        def blocker(tool, args, memos):
            return {"blocked": True}

        registry.register_pre("memory_search", blocker)
        early = registry.run_pre("memory_search", {}, None)
        assert early == {"blocked": True}

    def test_pre_returns_none_when_no_hook(self):
        registry = MCPHookRegistry()
        result = registry.run_pre("memory_save", {}, None)
        assert result is None

    def test_post_returns_result_unchanged_when_no_hook(self):
        registry = MCPHookRegistry()
        original = {"content": [{"type": "text", "text": "hello"}]}
        result = registry.run_post("memory_save", {}, original, None)
        assert result is original

    def test_hook_exception_is_swallowed(self):
        registry = MCPHookRegistry()

        def bad_hook(tool, args, result, memos):
            raise RuntimeError("boom")

        registry.register_post("memory_save", bad_hook)
        original = {"content": [{"type": "text", "text": "hello"}]}
        # Should not raise
        result = registry.run_post("memory_save", {}, original, None)
        assert result is original

    def test_multiple_post_hooks_chained(self):
        registry = MCPHookRegistry()

        def hook1(tool, args, result, memos):
            return {**result, "step": 1}

        def hook2(tool, args, result, memos):
            return {**result, "step": result.get("step", 0) + 1}

        registry.register_post("memory_save", hook1)
        registry.register_post("memory_save", hook2)
        result = registry.run_post("memory_save", {}, {}, None)
        assert result["step"] == 2

    def test_unregister_removes_hooks(self):
        registry = MCPHookRegistry()
        registry.register_post("memory_save", lambda *a: {"hooked": True})
        registry.unregister("memory_save")
        result = registry.run_post("memory_save", {}, {}, None)
        assert "hooked" not in result

    def test_registered_tools(self):
        registry = MCPHookRegistry()
        registry.register_pre("memory_search", lambda *a: None)
        registry.register_post("memory_save", lambda *a: None)
        assert "memory_search" in registry.registered_tools
        assert "memory_save" in registry.registered_tools


# ---------------------------------------------------------------------------
# KG extraction helper
# ---------------------------------------------------------------------------


class TestExtractFacts:
    def test_works_at_pattern(self):
        from memos.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(":memory:")
        content = "Alice works at CompanyX and loves her job."
        ids = _extract_and_store_facts(content, kg)
        assert len(ids) >= 1
        facts = kg.query("Alice")
        predicates = {f["predicate"] for f in facts}
        assert "works-at" in predicates
        kg.close()

    def test_depends_on_pattern(self):
        from memos.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(":memory:")
        content = "ServiceA depends on ServiceB for authentication."
        _extract_and_store_facts(content, kg)
        facts = kg.query("ServiceA")
        predicates = {f["predicate"] for f in facts}
        assert "depends-on" in predicates
        kg.close()

    def test_no_self_reference(self):
        from memos.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(":memory:")
        content = "Alice leads Alice."  # invalid self-reference
        _extract_and_store_facts(content, kg)
        facts = kg.query("Alice")
        self_refs = [f for f in facts if f["subject"] == f["object"]]
        assert len(self_refs) == 0
        kg.close()

    def test_confidence_label_extracted(self):
        from memos.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(":memory:")
        content = "Bob manages Carol effectively."
        _extract_and_store_facts(content, kg)
        facts = kg.query("Bob")
        assert all(f["confidence_label"] == "EXTRACTED" for f in facts)
        kg.close()


# ---------------------------------------------------------------------------
# hook_auto_capture_kg
# ---------------------------------------------------------------------------


class TestAutoCapture:
    def test_stores_facts_from_memory_save(self):
        from memos.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(":memory:")
        memos = MagicMock()
        memos.kg = kg
        result = {"content": [{"type": "text", "text": "Saved"}]}
        hook_auto_capture_kg("memory_save", {"content": "Alice leads TeamA"}, result, memos)
        facts = kg.query("Alice")
        assert any(f["predicate"] == "leads" for f in facts)
        kg.close()

    def test_empty_content_no_error(self):
        memos = MagicMock()
        memos.kg = MagicMock()
        result = {"content": []}
        hook_auto_capture_kg("memory_save", {"content": ""}, result, memos)
        # No exception, result unchanged
        assert result == {"content": []}

    def test_returns_original_result_unchanged(self):
        memos = MagicMock()
        memos.kg = MagicMock()
        memos.kg.add_fact.return_value = "abc"
        original = {"content": [{"type": "text", "text": "ok"}]}
        returned = hook_auto_capture_kg("memory_save", {"content": "Alice leads TeamA"}, original, memos)
        assert returned is original


# ---------------------------------------------------------------------------
# create_default_registry
# ---------------------------------------------------------------------------


class TestDefaultRegistry:
    def test_empty_registry_no_hooks(self):
        registry = create_default_registry()
        assert registry.registered_tools == set()

    def test_auto_kg_registers_post_hook(self):
        registry = create_default_registry(auto_kg=True)
        assert "memory_save" in registry.registered_tools

    def test_auto_context_registers_post_hook(self):
        registry = create_default_registry(auto_context=True)
        assert "memory_search" in registry.registered_tools


# ---------------------------------------------------------------------------
# Integration: _dispatch with hooks
# ---------------------------------------------------------------------------


class TestDispatchWithHooks:
    def test_pre_hook_short_circuits(self):
        from memos.mcp_server import _dispatch

        registry = MCPHookRegistry()
        registry.register_pre("memory_save", lambda tool, args, memos: {"short": "circuit"})
        result = _dispatch(None, "memory_save", {}, hooks=registry)
        assert result == {"short": "circuit"}

    def test_post_hook_augments_result(self):
        from memos.core import MemOS
        from memos.mcp_server import _dispatch

        memos = MemOS(backend="memory")

        registry = MCPHookRegistry()

        def augment(tool, args, result, memos):
            result["augmented"] = True
            return result

        registry.register_post("memory_save", augment)
        result = _dispatch(memos, "memory_save", {"content": "test hook content"}, hooks=registry)
        assert result.get("augmented") is True

    def test_no_hooks_normal_dispatch(self):
        from memos.core import MemOS
        from memos.mcp_server import _dispatch

        memos = MemOS(backend="memory")
        result = _dispatch(memos, "memory_save", {"content": "no hooks"})
        assert result is not None
        assert "isError" not in result or not result.get("isError")
