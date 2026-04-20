"""Direct tests for wiki_entities module — entity extraction and stop-word filtering."""

from __future__ import annotations

import pytest

# Direct import from the split module
from memos.wiki_entities import _STOPWORDS, STOP_WORDS, extract_entities

# ---------------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------------


class TestAliases:
    """Verify _STOPWORDS alias for STOP_WORDS."""

    def test_stopwords_alias(self) -> None:
        assert _STOPWORDS is STOP_WORDS


# ---------------------------------------------------------------------------
# Core extraction behaviour (direct import)
# ---------------------------------------------------------------------------


class TestExtractEntitiesDirect:
    """Tests exercising extract_entities directly from the split module."""

    def test_project_names(self) -> None:
        entities = extract_entities("Project Phoenix is awesome")
        names = {n for n, _ in entities}
        assert "Project Phoenix" in names

    def test_full_person_names(self) -> None:
        entities = extract_entities("Alice Smith works here")
        names = {n for n, _ in entities}
        assert "Alice Smith" in names

    def test_single_proper_names(self) -> None:
        entities = extract_entities("Cortex is a module")
        names = {n for n, _ in entities}
        assert "Cortex" in names

    def test_backtick_names(self) -> None:
        entities = extract_entities("Use `MemOS` for memory")
        names = {n for n, _ in entities}
        assert "MemOS" in names

    def test_hashtag_topics(self) -> None:
        entities = extract_entities("Working on #machine-learning today")
        names = {n for n, _ in entities}
        assert "machine-learning" in names

    def test_emails(self) -> None:
        entities = extract_entities("Contact user@example.com for info")
        names = {n for n, _ in entities}
        assert "user@example.com" in names

    def test_returns_tuples_with_types(self) -> None:
        entities = extract_entities("Alice works on Project Alpha")
        for name, etype in entities:
            assert isinstance(name, str)
            assert isinstance(etype, str)
            assert len(name) >= 2

    def test_deduplication(self) -> None:
        text = "Alice works with Alice on Project Alice"
        entities = extract_entities(text)
        # "Alice" should only appear once (deduped by lowered key)
        alice_entries = [(n, t) for n, t in entities if n == "Alice"]
        assert len(alice_entries) == 1

    def test_empty_input(self) -> None:
        assert extract_entities("") == []

    def test_concept_pattern(self) -> None:
        """'X is Y' pattern should be detected as concept."""
        entities = extract_entities("Reinforcement means reward signal")
        names = {n for n, _ in entities}
        assert "Reinforcement" in names


# ---------------------------------------------------------------------------
# Stop-word filtering (direct import)
# ---------------------------------------------------------------------------


class TestStopWordFilteringDirect:
    """Verify known noise is filtered when importing directly from wiki_entities."""

    @pytest.mark.parametrize(
        "noise",
        ["str", "dict", "type", "int", "float", "bool", "list", "http", "https", "mcp", "server", "get", "set"],
    )
    def test_programming_and_http_noise_filtered(self, noise: str) -> None:
        entities = extract_entities(f"Use `{noise}` here.")
        names = {n for n, _ in entities}
        assert noise not in names

    @pytest.mark.parametrize("noise", ["Best", "General", "Same", "Function", "Method", "Module"])
    def test_generic_noise_filtered(self, noise: str) -> None:
        entities = extract_entities(f"{noise} is the answer.")
        names = {n for n, _ in entities}
        assert noise not in names

    def test_single_char_rejected(self) -> None:
        entities = extract_entities("Use X here")
        names = {n for n, _ in entities}
        assert "X" not in names

    def test_lowercase_short_rejected(self) -> None:
        """All-lowercase entities shorter than 4 chars are rejected."""
        entities = extract_entities("the mcp and api are here")
        names = {n for n, _ in entities}
        for n in names:
            if n.islower():
                assert len(n) >= 4

    def test_no_letter_entities_rejected(self) -> None:
        entities = extract_entities("`123` and `---` are codes")
        names = {n for n, _ in entities}
        assert "123" not in names
        assert "---" not in names


# ---------------------------------------------------------------------------
# STOP_WORDS set content
# ---------------------------------------------------------------------------


class TestStopWordsSet:
    """Verify STOP_WORDS set composition."""

    def test_is_set(self) -> None:
        assert isinstance(STOP_WORDS, set)

    def test_contains_key_programming_words(self) -> None:
        for w in ["str", "dict", "type", "int", "float", "bool"]:
            assert w in STOP_WORDS

    def test_contains_http_fragments(self) -> None:
        for w in ["http", "https", "www", "com", "org", "io"]:
            assert w in STOP_WORDS

    def test_contains_api_doc_noise(self) -> None:
        for w in ["parameter", "returns", "raises", "example", "note"]:
            assert w in STOP_WORDS


# ---------------------------------------------------------------------------
# Backward compatibility — import from wiki_living shim
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Legacy import path from wiki_living resolves to same objects."""

    def test_extract_entities_same_function(self) -> None:
        from memos.wiki_living import extract_entities as shim_extract

        assert shim_extract is extract_entities

    def test_stop_words_same_object(self) -> None:
        from memos.wiki_living import STOP_WORDS as shim_sw

        assert shim_sw is STOP_WORDS
