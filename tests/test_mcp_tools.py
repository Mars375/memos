"""Direct tests for mcp_tools package — registry dispatch and representative tool handlers."""

from __future__ import annotations

import pytest

from memos.core import MemOS

# Direct imports from the split package
from memos.mcp_tools import TOOLS, dispatch
from memos.mcp_tools._registry import (
    _TOOL_HANDLERS,
    _TOOL_SCHEMAS,
    _error,
    _text,
    get_all_schemas,
    register_tool,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mem():
    m = MemOS()
    m.learn("Python is great for scripting", tags=["python", "dev"])
    m.learn("Use async/await for concurrency", tags=["python", "async"])
    m.learn("Docker simplifies deployment", tags=["devops"])
    return m


# ---------------------------------------------------------------------------
# Registry basics
# ---------------------------------------------------------------------------


class TestRegistry:
    """Tests for the _registry module's core functions."""

    def test_text_wraps_content(self) -> None:
        result = _text("hello world")
        assert result == {"content": [{"type": "text", "text": "hello world"}]}

    def test_error_wraps_with_is_error(self) -> None:
        result = _error("something broke")
        assert result["isError"] is True
        assert "something broke" in result["content"][0]["text"]

    def test_register_and_dispatch(self) -> None:
        """Register a custom tool and dispatch to it."""
        schema = {"name": "test_echo", "description": "echo", "inputSchema": {"type": "object", "properties": {}}}

        def handler(args: dict, memos: object) -> dict:
            return _text(f"echo: {args.get('msg', '')}")

        register_tool("test_echo", schema, handler)

        result = dispatch("test_echo", {"msg": "hi"}, None)
        assert not result.get("isError")
        assert "echo: hi" in result["content"][0]["text"]

        # Cleanup
        _TOOL_SCHEMAS.pop("test_echo", None)
        _TOOL_HANDLERS.pop("test_echo", None)

    def test_dispatch_unknown_tool(self) -> None:
        result = dispatch("nonexistent_tool_xyz", {}, None)
        assert result.get("isError") is True
        assert "Unknown tool" in result["content"][0]["text"]

    def test_dispatch_exception_caught(self) -> None:
        """Handler exceptions are caught and returned as errors."""

        def bad_handler(args: dict, memos: object) -> dict:
            raise ValueError("boom")

        register_tool("bad_tool", {"name": "bad_tool"}, bad_handler)
        result = dispatch("bad_tool", {}, None)
        assert result.get("isError") is True
        assert "boom" in result["content"][0]["text"]

        # Cleanup
        _TOOL_SCHEMAS.pop("bad_tool", None)
        _TOOL_HANDLERS.pop("bad_tool", None)

    def test_get_all_schemas(self) -> None:
        schemas = get_all_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) > 0
        # Each schema should have a name
        for s in schemas:
            assert "name" in s


# ---------------------------------------------------------------------------
# Package-level TOOLS list and dispatch
# ---------------------------------------------------------------------------


class TestPackageExports:
    """Tests for the mcp_tools package-level exports."""

    def test_tools_list_populated(self) -> None:
        assert len(TOOLS) > 0

    def test_expected_tool_names_present(self) -> None:
        names = {t["name"] for t in TOOLS}
        # Memory tools
        assert "memory_search" in names
        assert "memory_save" in names
        assert "memory_forget" in names
        assert "memory_stats" in names
        assert "memory_decay" in names
        assert "memory_reinforce" in names
        assert "memory_wake_up" in names
        assert "memory_context_for" in names
        # KG tools
        assert "kg_add_fact" in names
        assert "kg_query_entity" in names
        assert "kg_timeline" in names
        assert "kg_communities" in names
        assert "kg_god_nodes" in names
        assert "kg_surprising" in names
        # Wiki tools
        assert "wiki_regenerate_index" in names
        assert "wiki_lint" in names
        # Palace tools
        assert "diary_write" in names
        assert "diary_read" in names
        assert "palace_diary_append" in names
        assert "palace_diary_read" in names
        assert "palace_list_agents" in names
        # Sync tools
        assert "memory_sync_check" in names
        assert "memory_sync_apply" in names
        # Enriched tools
        assert "memory_recall_enriched" in names
        assert "brain_search" in names
        assert "brain_suggest" in names


# ---------------------------------------------------------------------------
# Memory tool handlers (direct dispatch)
# ---------------------------------------------------------------------------


class TestMemoryTools:
    """Tests for memory tool handlers via direct dispatch."""

    def test_memory_search(self, mem: MemOS) -> None:
        result = dispatch("memory_search", {"query": "python", "top_k": 3}, mem)
        assert not result.get("isError")
        assert "python" in result["content"][0]["text"].lower()

    def test_memory_search_no_results(self) -> None:
        m = MemOS()
        result = dispatch("memory_search", {"query": "nonexistent_topic_xyz"}, m)
        assert not result.get("isError")
        assert "No memories found" in result["content"][0]["text"]

    def test_memory_save(self, mem: MemOS) -> None:
        result = dispatch("memory_save", {"content": "test via tools", "tags": ["test"]}, mem)
        assert not result.get("isError")
        assert "Saved" in result["content"][0]["text"]

    def test_memory_save_empty_content(self, mem: MemOS) -> None:
        result = dispatch("memory_save", {"content": ""}, mem)
        assert result.get("isError")
        assert "required" in result["content"][0]["text"].lower()

    def test_memory_forget_by_id(self, mem: MemOS) -> None:
        item = mem.learn("temporary", tags=["tmp"])
        result = dispatch("memory_forget", {"id": item.id}, mem)
        assert not result.get("isError")
        assert "Forgotten" in result["content"][0]["text"]

    def test_memory_forget_by_tag(self, mem: MemOS) -> None:
        result = dispatch("memory_forget", {"tag": "devops"}, mem)
        assert not result.get("isError")
        assert "1" in result["content"][0]["text"]

    def test_memory_forget_no_args(self, mem: MemOS) -> None:
        result = dispatch("memory_forget", {}, mem)
        assert result.get("isError")

    def test_memory_stats(self, mem: MemOS) -> None:
        result = dispatch("memory_stats", {}, mem)
        assert not result.get("isError")
        assert "Total memories" in result["content"][0]["text"]
        assert "3" in result["content"][0]["text"]

    def test_memory_decay_dry_run(self, mem: MemOS) -> None:
        result = dispatch("memory_decay", {"apply": False}, mem)
        assert not result.get("isError")
        assert "DRY RUN" in result["content"][0]["text"]
        assert mem.stats().total_memories == 3

    def test_memory_reinforce_found(self) -> None:
        m = MemOS()
        item = m.learn("boost me", tags=["test"], importance=0.3)
        result = dispatch("memory_reinforce", {"memory_id": item.id, "strength": 0.2}, m)
        assert not result.get("isError")
        assert "Reinforced" in result["content"][0]["text"]

    def test_memory_reinforce_not_found(self) -> None:
        m = MemOS()
        result = dispatch("memory_reinforce", {"memory_id": "nonexistent"}, m)
        assert result.get("isError")
        assert "not found" in result["content"][0]["text"].lower()

    def test_memory_wake_up(self, mem: MemOS) -> None:
        result = dispatch("memory_wake_up", {"max_chars": 500, "l1_top": 5}, mem)
        assert not result.get("isError")
        # Should contain some content from the session identity
        assert len(result["content"][0]["text"]) > 0

    def test_memory_context_for(self, mem: MemOS) -> None:
        result = dispatch("memory_context_for", {"query": "python", "max_chars": 1000}, mem)
        assert not result.get("isError")

    def test_memory_context_for_empty_query(self, mem: MemOS) -> None:
        result = dispatch("memory_context_for", {"query": ""}, mem)
        assert result.get("isError")


# ---------------------------------------------------------------------------
# KG tool handlers (direct dispatch)
# ---------------------------------------------------------------------------


class TestKGTools:
    """Tests for knowledge graph tool handlers via direct dispatch."""

    def test_kg_add_fact(self, mem: MemOS) -> None:
        result = dispatch(
            "kg_add_fact",
            {"subject": "Alice", "predicate": "works-at", "object": "Acme Corp"},
            mem,
        )
        assert not result.get("isError")
        assert "Fact added" in result["content"][0]["text"]

    def test_kg_add_fact_missing_fields(self, mem: MemOS) -> None:
        result = dispatch("kg_add_fact", {"subject": "Alice"}, mem)
        assert result.get("isError")

    def test_kg_query_entity(self, mem: MemOS) -> None:
        # First add a fact
        dispatch("kg_add_fact", {"subject": "Alice", "predicate": "knows", "object": "Bob"}, mem)
        result = dispatch("kg_query_entity", {"entity": "Alice"}, mem)
        assert not result.get("isError")
        assert "fact" in result["content"][0]["text"].lower()

    def test_kg_query_entity_empty(self, mem: MemOS) -> None:
        result = dispatch("kg_query_entity", {"entity": "NonExistentPerson12345"}, mem)
        assert not result.get("isError")
        assert "No facts found" in result["content"][0]["text"]

    def test_kg_query_entity_missing(self, mem: MemOS) -> None:
        result = dispatch("kg_query_entity", {"entity": ""}, mem)
        assert result.get("isError")

    def test_kg_timeline(self, mem: MemOS) -> None:
        dispatch("kg_add_fact", {"subject": "X", "predicate": "rel", "object": "Y"}, mem)
        result = dispatch("kg_timeline", {"entity": "X"}, mem)
        assert not result.get("isError")

    def test_kg_god_nodes_empty(self, mem: MemOS) -> None:
        result = dispatch("kg_god_nodes", {"top_k": 5}, mem)
        assert not result.get("isError")
        assert "No entities found" in result["content"][0]["text"] or "god nodes" in result["content"][0]["text"]

    def test_kg_surprising_empty(self, mem: MemOS) -> None:
        result = dispatch("kg_surprising", {"top_k": 5}, mem)
        assert not result.get("isError")
        assert "surprising" in result["content"][0]["text"].lower() or "No" in result["content"][0]["text"]

    def test_kg_communities_empty(self, mem: MemOS) -> None:
        result = dispatch("kg_communities", {}, mem)
        assert not result.get("isError")
        assert "communities" in result["content"][0]["text"].lower() or "No" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Wiki tool handlers (direct dispatch)
# ---------------------------------------------------------------------------


class TestWikiTools:
    """Tests for wiki tool handlers via direct dispatch."""

    def test_wiki_regenerate_index(self, mem: MemOS) -> None:
        result = dispatch("wiki_regenerate_index", {}, mem)
        assert not result.get("isError")
        assert "Living Wiki Index" in result["content"][0]["text"]

    def test_wiki_lint(self, mem: MemOS) -> None:
        result = dispatch("wiki_lint", {}, mem)
        assert not result.get("isError")
        assert "Wiki Lint Report" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Palace tool handlers (direct dispatch)
# ---------------------------------------------------------------------------


class TestPalaceTools:
    """Tests for palace tool handlers via direct dispatch."""

    def test_diary_write_no_palace(self, mem: MemOS) -> None:
        """Without a palace instance, should return error."""
        result = dispatch("diary_write", {"agent": "hermes", "content": "test"}, mem)
        assert result.get("isError")
        assert "Palace" in result["content"][0]["text"]

    def test_diary_read_no_palace(self, mem: MemOS) -> None:
        result = dispatch("diary_read", {"agent": "hermes"}, mem)
        assert result.get("isError")
        assert "Palace" in result["content"][0]["text"]

    def test_palace_list_agents_no_palace(self, mem: MemOS) -> None:
        result = dispatch("palace_list_agents", {}, mem)
        assert result.get("isError")
        assert "Palace" in result["content"][0]["text"]

    def test_diary_write_missing_fields(self, mem: MemOS) -> None:
        result = dispatch("diary_write", {"agent": "", "content": ""}, mem)
        assert result.get("isError")
        assert "required" in result["content"][0]["text"].lower()


# ---------------------------------------------------------------------------
# Sync tool handlers (direct dispatch)
# ---------------------------------------------------------------------------


class TestSyncTools:
    """Tests for sync tool handlers via direct dispatch."""

    def test_sync_check_empty_envelope(self, mem: MemOS) -> None:
        result = dispatch("memory_sync_check", {"envelope": {}}, mem)
        # Empty envelope may fail validation
        assert result.get("isError") or "Sync check" in result["content"][0]["text"]

    def test_sync_check_missing_envelope(self, mem: MemOS) -> None:
        result = dispatch("memory_sync_check", {}, mem)
        assert result.get("isError")

    def test_sync_apply_missing_envelope(self, mem: MemOS) -> None:
        result = dispatch("memory_sync_apply", {}, mem)
        assert result.get("isError")

    def test_sync_apply_invalid_strategy(self, mem: MemOS) -> None:
        result = dispatch(
            "memory_sync_apply",
            {"envelope": {"source_agent": "a", "target_agent": "b", "memories": []}, "strategy": "bad_strategy"},
            mem,
        )
        assert result.get("isError")
        assert "Invalid strategy" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Enriched tool handlers (direct dispatch)
# ---------------------------------------------------------------------------


class TestEnrichedTools:
    """Tests for enriched retrieval tool handlers via direct dispatch."""

    def test_memory_recall_enriched(self, mem: MemOS) -> None:
        result = dispatch("memory_recall_enriched", {"query": "python", "top_k": 3}, mem)
        assert not result.get("isError")
        assert "Memories" in result["content"][0]["text"]

    def test_memory_recall_enriched_empty_query(self, mem: MemOS) -> None:
        result = dispatch("memory_recall_enriched", {"query": ""}, mem)
        assert result.get("isError")

    def test_brain_search(self, mem: MemOS) -> None:
        result = dispatch("brain_search", {"query": "python", "top_k": 3}, mem)
        assert not result.get("isError")
        assert "Memories" in result["content"][0]["text"]

    def test_brain_search_empty_query(self, mem: MemOS) -> None:
        result = dispatch("brain_search", {"query": ""}, mem)
        assert result.get("isError")

    def test_brain_suggest(self, mem: MemOS) -> None:
        result = dispatch("brain_suggest", {"top_k": 3}, mem)
        assert not result.get("isError")
        text = result["content"][0]["text"].lower()
        assert "suggest" in text


# ---------------------------------------------------------------------------
# Backward compatibility — mcp_server re-exports
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Legacy import path from mcp_server resolves to same dispatch function."""

    def test_dispatch_same_function(self) -> None:

        # The mcp_server._dispatch wraps the registry dispatch but the
        # underlying tool dispatch uses the same registry. Verify the
        # TOOLS list is the same object.
        from memos.mcp_server import TOOLS as server_tools

        assert server_tools is TOOLS
