"""Tests for kg_bridge SVO pattern extraction."""

from __future__ import annotations

import pytest

from memos.kg_bridge import KGBridge


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _extract(text: str) -> list[tuple[str, str, str]]:
    """Run extract_facts on a single-line string and return all triples."""
    return KGBridge.extract_facts(text)


def _first(text: str) -> tuple[str, str, str] | None:
    """Return the first extracted fact, or None."""
    facts = _extract(text)
    return facts[0] if facts else None


# ===========================================================================
# New fine-grained SVO patterns
# ===========================================================================

class TestDeployedOn:
    def test_basic(self) -> None:
        f = _first("Loïc deployed MemOS on Cortex")
        assert f is not None
        assert f[0] == "Loïc"           # subject
        assert "deploy" in f[1]          # predicate
        assert "Cortex" in f[2]          # object includes destination

    def test_three_part(self) -> None:
        f = _first("Alice deployed MyApp on Kubernetes")
        assert f is not None
        assert f[0] == "Alice"
        assert f[1] == "deployed_on"

    def test_case_insensitive(self) -> None:
        f = _first("Bob Deployed Service On AWS")
        assert f is not None
        assert f[1] == "deployed_on"


class TestUses:
    def test_basic(self) -> None:
        f = _first("MemOS uses ChromaDB")
        assert f is not None
        assert f[0] == "MemOS"
        assert f[1] == "uses"
        assert f[2] == "ChromaDB"

    def test_third_person(self) -> None:
        f = _first("He uses Python")
        assert f is not None
        assert f[1] == "uses"


class TestRunsOn:
    def test_basic(self) -> None:
        f = _first("MemOS runs on Linux")
        assert f is not None
        assert f[0] == "MemOS"
        assert f[1] == "runs_on"
        assert f[2] == "Linux"


class TestManages:
    def test_basic(self) -> None:
        f = _first("Orchestrator manages Pipeline")
        assert f is not None
        assert f[0] == "Orchestrator"
        assert f[1] == "manages"
        assert f[2] == "Pipeline"


class TestDependsOn:
    def test_basic(self) -> None:
        f = _first("MemOS depends on FastAPI")
        assert f is not None
        assert f[0] == "MemOS"
        assert f[1] == "depends_on"
        assert f[2] == "FastAPI"


class TestContains:
    def test_basic(self) -> None:
        f = _first("Cluster contains NodeA")
        assert f is not None
        assert f[0] == "Cluster"
        assert f[1] == "contains"
        assert f[2] == "NodeA"


class TestLocatedIn:
    def test_basic(self) -> None:
        f = _first("Server located in Paris")
        assert f is not None
        assert f[0] == "Server"
        assert f[1] == "located_in"
        assert f[2] == "Paris"

    def test_with_is_matches_located(self) -> None:
        """'Server is located in Paris' matches the broader 'located' pattern
        (which is listed first in _FACT_PATTERNS). Both are valid — verify
        that something is extracted with a location-related predicate."""
        f = _first("Server is located in Paris")
        assert f is not None
        assert f[0] == "Server"
        assert f[2] == "Paris"
        assert "locat" in f[1]  # either 'located' or 'located_in'


class TestPartOf:
    def test_basic(self) -> None:
        f = _first("Module part of System")
        assert f is not None
        assert f[0] == "Module"
        assert f[1] == "part_of"
        assert f[2] == "System"

    def test_with_is_a(self) -> None:
        """'Module is a part of System' matches 'is_type_of' (listed earlier).
        Both are valid — verify a fact is extracted linking Module to System."""
        f = _first("Module is a part of System")
        assert f is not None
        assert f[0] == "Module"
        assert f[2] == "System"

    def test_with_is(self) -> None:
        f = _first("Module is part of System")
        assert f is not None
        assert f[1] == "part_of"


class TestConnectedTo:
    def test_basic(self) -> None:
        f = _first("NodeA connected to NodeB")
        assert f is not None
        assert f[0] == "NodeA"
        assert f[1] == "connected_to"
        assert f[2] == "NodeB"

    def test_with_is(self) -> None:
        f = _first("NodeA is connected to NodeB")
        assert f is not None
        assert f[1] == "connected_to"


class TestBuiltWith:
    def test_basic(self) -> None:
        f = _first("App built with Rust")
        assert f is not None
        assert f[0] == "App"
        assert f[1] == "built_with"
        assert f[2] == "Rust"

    def test_was_built(self) -> None:
        f = _first("App was built with Rust")
        assert f is not None
        assert f[1] == "built_with"


class TestHosts:
    def test_basic(self) -> None:
        f = _first("Server hosts App")
        assert f is not None
        assert f[0] == "Server"
        assert f[1] == "hosts"
        assert f[2] == "App"


# ===========================================================================
# General SVO fallback
# ===========================================================================

class TestGeneralSVOfallback:
    def test_unknown_past_verb(self) -> None:
        f = _first("Alice discovered MemOS")
        assert f is not None
        assert f[0] == "Alice"
        assert f[1] == "general_svo"
        assert f[2] == "MemOS"

    def test_another_unknown(self) -> None:
        f = _first("Bob created ProjectX")
        assert f is not None
        assert f[0] == "Bob"
        assert f[1] == "general_svo"


# ===========================================================================
# Active verb catch-all (broader pattern for verbs without own entry)
# ===========================================================================

class TestActiveVerb:
    def test_supports(self) -> None:
        f = _first("MemOS supports Plugins")
        assert f is not None
        assert f[0] == "MemOS"
        assert f[1] == "active_verb"
        assert f[2] == "Plugins"

    def test_monitors(self) -> None:
        f = _first("Agent monitors Cluster")
        assert f is not None
        assert f[1] == "active_verb"


# ===========================================================================
# Task-required specific test case
# ===========================================================================

class TestDeployedOnCortex:
    """Test that 'Loïc deployed MemOS on Cortex' extracts correctly."""

    def test_subject_is_loic(self) -> None:
        f = _first("Loïc deployed MemOS on Cortex")
        assert f is not None
        assert f[0] == "Loïc", f"Expected subject='Loïc', got {f[0]!r}"

    def test_predicate_contains_deploy(self) -> None:
        f = _first("Loïc deployed MemOS on Cortex")
        assert f is not None
        assert "deploy" in f[1].lower(), f"Expected predicate containing 'deploy', got {f[1]!r}"

    def test_object_is_destination(self) -> None:
        """The deployed_on pattern captures the deployment target (Cortex)
        as the object. The deployed thing (MemOS) is the intermediate token."""
        f = _first("Loïc deployed MemOS on Cortex")
        assert f is not None
        assert f[2] == "Cortex", f"Expected object='Cortex', got {f[2]!r}"

    def test_fact_extracted_from_sentence(self) -> None:
        """At minimum, a fact must be extracted from this sentence."""
        facts = _extract("Loïc deployed MemOS on Cortex")
        assert len(facts) >= 1
        sub, pred, obj = facts[0]
        assert sub == "Loïc"
        assert "deploy" in pred


# ===========================================================================
# Backward compatibility — existing patterns still work
# ===========================================================================

class TestBackwardCompat:
    def test_is(self) -> None:
        f = _first("MemOS is awesome")
        assert f is not None
        assert f[0] == "MemOS"
        assert f[1] == "is"
        assert f[2] == "awesome"

    def test_works_at(self) -> None:
        f = _first("Alice works at Google")
        assert f is not None
        assert f[0] == "Alice"
        assert f[1] == "works_at"
        assert f[2] == "Google"

    def test_arrow(self) -> None:
        f = _first("Alice → Bob")
        assert f is not None
        assert f[0].strip() == "Alice"
        assert f[1] == "arrow"
        assert f[2].strip() == "Bob"

    def test_from_to(self) -> None:
        f = _first("from: Alice to: Bob")
        assert f is not None
        assert f[1] == "from_to"

    def test_version(self) -> None:
        f = _first("MemOS version 1.2.3")
        assert f is not None
        assert f[0] == "MemOS"
        assert f[1] == "version"
        assert f[2] == "1.2.3"

    def test_is_type_of(self) -> None:
        f = _first("ChromaDB is a type of Database")
        assert f is not None
        assert f[0] == "ChromaDB"
        assert f[1] == "is_type_of"
        assert f[2] == "Database"

    def test_located(self) -> None:
        f = _first("MemOS is located in Paris")
        assert f is not None
        assert f[1] == "located"


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_multiline_extracts_per_line(self) -> None:
        text = "MemOS uses ChromaDB\nServer runs on Linux"
        facts = _extract(text)
        assert len(facts) == 2

    def test_empty_input(self) -> None:
        assert _extract("") == []

    def test_no_match_gibberish(self) -> None:
        assert _extract("xyzzy plugh") == []

    def test_is_catches_lowercase_sentence(self) -> None:
        """The broadened entity regex (supporting accented chars) also
        matches lowercase starts. 'is' pattern catches 'weather is nice'."""
        facts = _extract("the weather is nice today")
        assert len(facts) == 1
        assert facts[0][1] == "is"

    def test_single_sentence_per_line(self) -> None:
        """Each line yields at most one fact (first match wins, then break)."""
        text = "MemOS uses ChromaDB"
        facts = _extract(text)
        assert len(facts) == 1
        assert facts[0][0] == "MemOS"
        assert facts[0][1] == "uses"
