"""Tests for wiki entity extraction stop-word filtering."""

from __future__ import annotations

import pytest

from memos.wiki_living import STOP_WORDS, extract_entities


# ---------------------------------------------------------------------------
# Stop-word rejection tests
# ---------------------------------------------------------------------------

class TestStopWordFiltering:
    """Verify that known garbage entities are filtered out."""

    @pytest.mark.parametrize(
        "noise_word",
        [
            "str", "dict", "type", "int", "float", "bool", "list", "set",
            "tuple", "None", "True", "False", "class", "def", "return",
            "import", "http", "https", "www", "com", "org", "io",
            "parameter", "returns", "raises", "example", "note",
            "mcp", "servers", "server", "client",
            "get", "set", "put", "post", "delete",
        ],
    )
    def test_programming_noise_filtered_out(self, noise_word: str) -> None:
        """Programming keywords, HTTP fragments, and API doc noise are rejected."""
        entities = extract_entities(f"Use `{noise_word}` for this operation.")
        names = {name for name, _ in entities}
        # The noise word should NOT appear as an entity
        assert noise_word not in names, f"'{noise_word}' should be filtered out"
        # Also check case-insensitive — entity keys are lowered internally
        lowered = {n.lower() for n in names}
        assert noise_word.lower() not in lowered

    @pytest.mark.parametrize(
        "noise_word",
        ["Best", "General", "Same", "Augmenting", "Answers", "Any",
         "Discovery", "Function", "Method", "Module"],
    )
    def test_generic_noise_filtered_out(self, noise_word: str) -> None:
        """Generic noise words from API docs/READMEs are rejected."""
        entities = extract_entities(f"{noise_word} is the way to go.")
        names = {name for name, _ in entities}
        assert noise_word not in names, f"'{noise_word}' should be filtered out"

    @pytest.mark.parametrize("char", ["a", "X", "1", ".", "_"])
    def test_single_character_entities_rejected(self, char: str) -> None:
        """Single-character entities are always rejected."""
        entities = extract_entities(f"Use {char} here.")
        names = {name for name, _ in entities}
        assert char not in names

    def test_lowercase_short_entities_rejected(self) -> None:
        """All-lowercase entities shorter than 4 chars are rejected."""
        entities = extract_entities("The mcp and api are used here.")
        names = {name for name, _ in entities}
        for n in names:
            # If it's lowercase and short, it should have been filtered
            if n.islower():
                assert len(n) >= 4, f"Short lowercase '{n}' should be rejected"

    def test_entity_without_letters_rejected(self) -> None:
        """Entities with no letters at all are rejected (e.g., '123', '---')."""
        entities = extract_entities("`123` is the code and `---` separator.")
        names = {name for name, _ in entities}
        assert "123" not in names
        assert "---" not in names


# ---------------------------------------------------------------------------
# Legitimate entity pass-through tests
# ---------------------------------------------------------------------------

class TestLegitimateEntitiesPass:
    """Verify that real entity names pass through the filter."""

    @pytest.mark.parametrize(
        "entity_name",
        ["Cortex", "Hermes", "Alice", "Bob"],
    )
    def test_known_names_pass_through(self, entity_name: str) -> None:
        """Known proper names and project names are not filtered."""
        # Use contexts where these names would be matched by patterns
        text = f"{entity_name} works on the project."
        entities = extract_entities(text)
        names = {name for name, _ in entities}
        assert entity_name in names, f"'{entity_name}' should pass through"

    def test_backtick_names_pass_through(self) -> None:
        """Names in backticks (e.g., project/product names) pass through."""
        entities = extract_entities("Use `MemOS` for memory management.")
        names = {name for name, _ in entities}
        assert "MemOS" in names

    def test_project_names_with_mixed_case(self) -> None:
        """Project names with mixed case pass through."""
        entities = extract_entities("Project MemOS is a memory system.")
        names = {name for name, _ in entities}
        assert "Project MemOS" in names

    def test_project_names_pass(self) -> None:
        """Multi-word project names pass through."""
        entities = extract_entities("Project Phoenix is a search tool.")
        names = {name for name, _ in entities}
        assert "Project Phoenix" in names

    def test_full_names_pass(self) -> None:
        """Full person names pass through."""
        entities = extract_entities("Alice Smith works here.")
        names = {name for name, _ in entities}
        assert "Alice Smith" in names

    def test_emails_pass(self) -> None:
        """Email addresses pass through."""
        entities = extract_entities("Contact: user@example.com for details.")
        names = {name for name, _ in entities}
        assert "user@example.com" in names

    def test_hashtag_topics_pass(self) -> None:
        """Hashtag topics pass through."""
        entities = extract_entities("Working on #machine-learning today.")
        names = {name for name, _ in entities}
        assert "machine-learning" in names


# ---------------------------------------------------------------------------
# STOP_WORDS constant tests
# ---------------------------------------------------------------------------

class TestStopWordsConstant:
    """Verify the STOP_WORDS constant is properly configured."""

    def test_stop_words_is_set(self) -> None:
        assert isinstance(STOP_WORDS, set)

    def test_programming_keywords_in_stop_words(self) -> None:
        for word in ["str", "dict", "type", "int", "float", "bool", "list", "set", "tuple"]:
            assert word in STOP_WORDS, f"'{word}' missing from STOP_WORDS"

    def test_http_fragments_in_stop_words(self) -> None:
        for word in ["http", "https", "www", "com", "org", "io"]:
            assert word in STOP_WORDS, f"'{word}' missing from STOP_WORDS"

    def test_api_doc_noise_in_stop_words(self) -> None:
        for word in ["parameter", "returns", "raises", "example", "note", "see", "also"]:
            assert word in STOP_WORDS, f"'{word}' missing from STOP_WORDS"

    def test_reported_garbage_in_stop_words(self) -> None:
        """All the specific garbage entities from the bug report are in STOP_WORDS."""
        garbage = [
            "str", "dict", "type", "http", "mcp", "servers",
            "Function", "Best", "General", "Same",
            "Augmenting", "Answers", "Any", "Discovery",
        ]
        for word in garbage:
            assert word in STOP_WORDS, f"Reported garbage '{word}' missing from STOP_WORDS"
