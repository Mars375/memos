"""Tests for KnowledgeGraph.god_nodes — top-degree hub entities."""

from __future__ import annotations

import pytest

from memos.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    """In-memory knowledge graph for testing."""
    g = KnowledgeGraph(db_path=":memory:")
    yield g
    g.close()


# ── Test 1: Empty graph → empty list ────────────────────────────

class TestEmptyGraph:
    def test_god_nodes_empty(self, kg: KnowledgeGraph):
        assert kg.god_nodes() == []

    def test_god_nodes_empty_with_top_k(self, kg: KnowledgeGraph):
        assert kg.god_nodes(top_k=5) == []


# ── Test 2: Correct degree calculation ──────────────────────────

class TestDegreeCalculation:
    def test_single_fact(self, kg: KnowledgeGraph):
        kg.add_fact("Alice", "knows", "Bob")
        nodes = kg.god_nodes()
        assert len(nodes) == 2
        # Alice: degree 1 (1 subject), Bob: degree 1 (1 object)
        by_name = {n["entity"]: n for n in nodes}
        assert by_name["Alice"]["degree"] == 1
        assert by_name["Alice"]["facts_as_subject"] == 1
        assert by_name["Alice"]["facts_as_object"] == 0
        assert by_name["Bob"]["degree"] == 1
        assert by_name["Bob"]["facts_as_subject"] == 0
        assert by_name["Bob"]["facts_as_object"] == 1

    def test_hub_entity_highest_degree(self, kg: KnowledgeGraph):
        """Entity appearing in many facts should be the top god node."""
        kg.add_fact("Alice", "knows", "Bob")
        kg.add_fact("Alice", "works_at", "Acme")
        kg.add_fact("Alice", "lives_in", "NYC")
        kg.add_fact("Charlie", "knows", "Alice")
        nodes = kg.god_nodes()
        assert nodes[0]["entity"] == "Alice"
        # Alice: 3 as subject + 1 as object = degree 4
        assert nodes[0]["degree"] == 4
        assert nodes[0]["facts_as_subject"] == 3
        assert nodes[0]["facts_as_object"] == 1

    def test_degree_includes_both_directions(self, kg: KnowledgeGraph):
        """Entity as both subject and object in different facts."""
        kg.add_fact("A", "rel1", "B")
        kg.add_fact("B", "rel2", "C")
        nodes = kg.god_nodes()
        by_name = {n["entity"]: n for n in nodes}
        # B: 1 as object + 1 as subject = 2
        assert by_name["B"]["degree"] == 2
        assert by_name["B"]["facts_as_subject"] == 1
        assert by_name["B"]["facts_as_object"] == 1

    def test_invalidated_facts_excluded(self, kg: KnowledgeGraph):
        """Invalidated facts should not count toward degree."""
        fid = kg.add_fact("X", "old_rel", "Y")
        kg.add_fact("X", "new_rel", "Z")
        kg.invalidate(fid)
        nodes = kg.god_nodes()
        by_name = {n["entity"]: n for n in nodes}
        # X: only 1 active fact (new_rel)
        assert by_name["X"]["degree"] == 1
        # Y should not appear at all (its only fact was invalidated)
        assert "Y" not in by_name


# ── Test 3: top_k parameter ────────────────────────────────────

class TestTopK:
    def test_top_k_limits_results(self, kg: KnowledgeGraph):
        for i in range(20):
            kg.add_fact(f"entity_{i:02d}", "related_to", f"entity_{(i + 1) % 20:02d}")
        nodes = kg.god_nodes(top_k=5)
        assert len(nodes) == 5

    def test_top_k_default_is_10(self, kg: KnowledgeGraph):
        for i in range(15):
            kg.add_fact(f"e_{i}", "rel", f"e_{(i + 1) % 15}")
        nodes = kg.god_nodes()
        assert len(nodes) == 10

    def test_top_k_greater_than_entities(self, kg: KnowledgeGraph):
        kg.add_fact("A", "rel", "B")
        nodes = kg.god_nodes(top_k=100)
        # Only 2 entities exist
        assert len(nodes) == 2

    def test_sorted_by_degree_descending(self, kg: KnowledgeGraph):
        kg.add_fact("A", "r1", "B")
        kg.add_fact("A", "r2", "C")
        kg.add_fact("A", "r3", "D")
        kg.add_fact("E", "r4", "B")
        nodes = kg.god_nodes()
        degrees = [n["degree"] for n in nodes]
        assert degrees == sorted(degrees, reverse=True)


# ── Test 4: top_predicates ─────────────────────────────────────

class TestTopPredicates:
    def test_top_predicates_most_common(self, kg: KnowledgeGraph):
        kg.add_fact("A", "knows", "B")
        kg.add_fact("A", "knows", "C")
        kg.add_fact("A", "works_at", "D")
        kg.add_fact("A", "lives_in", "E")
        kg.add_fact("A", "lives_in", "F")
        nodes = kg.god_nodes()
        a_node = next(n for n in nodes if n["entity"] == "A")
        # knows: 2 (A as subject), lives_in: 2 (A as subject), works_at: 1
        # top 3 by count: knows(2), lives_in(2), works_at(1)
        assert len(a_node["top_predicates"]) == 3
        # knows and lives_in both have count 2; works_at has 1
        # Both knows and lives_in should be in top 3
        assert "knows" in a_node["top_predicates"]
        assert "lives_in" in a_node["top_predicates"]
        assert "works_at" in a_node["top_predicates"]

    def test_top_predicates_limited_to_3(self, kg: KnowledgeGraph):
        kg.add_fact("A", "r1", "B")
        kg.add_fact("A", "r2", "C")
        kg.add_fact("A", "r3", "D")
        kg.add_fact("A", "r4", "E")
        kg.add_fact("A", "r5", "F")
        nodes = kg.god_nodes()
        a_node = next(n for n in nodes if n["entity"] == "A")
        assert len(a_node["top_predicates"]) <= 3

    def test_top_predicates_includes_object_role(self, kg: KnowledgeGraph):
        """Predicates from facts where entity is the object also count."""
        kg.add_fact("X", "manages", "A")
        kg.add_fact("Y", "manages", "A")
        kg.add_fact("Z", "reports_to", "A")
        nodes = kg.god_nodes()
        a_node = next(n for n in nodes if n["entity"] == "A")
        # A is object in 3 facts: manages(2), reports_to(1)
        assert "manages" in a_node["top_predicates"]
        assert "reports_to" in a_node["top_predicates"]

    def test_top_predicates_empty_when_no_facts(self, kg: KnowledgeGraph):
        nodes = kg.god_nodes()
        assert nodes == []


# ── Test 5: Return structure completeness ───────────────────────

class TestReturnStructure:
    def test_all_keys_present(self, kg: KnowledgeGraph):
        kg.add_fact("Alice", "knows", "Bob")
        nodes = kg.god_nodes()
        for node in nodes:
            assert "entity" in node
            assert "degree" in node
            assert "facts_as_subject" in node
            assert "facts_as_object" in node
            assert "top_predicates" in node
            assert isinstance(node["entity"], str)
            assert isinstance(node["degree"], int)
            assert isinstance(node["facts_as_subject"], int)
            assert isinstance(node["facts_as_object"], int)
            assert isinstance(node["top_predicates"], list)

    def test_degree_equals_subject_plus_object(self, kg: KnowledgeGraph):
        kg.add_fact("A", "r1", "B")
        kg.add_fact("C", "r2", "A")
        kg.add_fact("A", "r3", "D")
        nodes = kg.god_nodes()
        a_node = next(n for n in nodes if n["entity"] == "A")
        assert a_node["degree"] == a_node["facts_as_subject"] + a_node["facts_as_object"]
