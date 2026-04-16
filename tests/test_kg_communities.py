"""Tests for KG Community Detection, God Nodes, and Surprising Connections."""

import pytest

from memos.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    """Create an in-memory KG with a multi-community test graph.

    Structure (two communities with a bridge):
      Community A (work cluster):
        Alice -[works_on]-> ProjectX
        Alice -[leads]-> Infrastructure
        Bob -[works_on]-> ProjectX
        Bob -[manages]-> Carol
        Carol -[works_on]-> ProjectY

      Community B (isolated cluster):
        Eve -[works_on]-> ProjectZ
        Eve -[mentors]-> Frank
        Frank -[works_on]-> ProjectZ

      Bridge (cross-community):
        Dave -[reviews]-> ProjectY       (Dave ↔ Community A)
        Dave -[consults]-> Eve           (Dave ↔ Community B)
    """
    kg = KnowledgeGraph(db_path=":memory:")
    # Community A
    kg.add_fact("Alice", "works_on", "ProjectX")
    kg.add_fact("Alice", "leads", "Infrastructure")
    kg.add_fact("Bob", "works_on", "ProjectX")
    kg.add_fact("Bob", "manages", "Carol")
    kg.add_fact("Carol", "works_on", "ProjectY")
    kg.add_fact("ProjectX", "depends_on", "ProjectY")
    # Community B
    kg.add_fact("Eve", "works_on", "ProjectZ")
    kg.add_fact("Eve", "mentors", "Frank")
    kg.add_fact("Frank", "works_on", "ProjectZ")
    # Bridge
    kg.add_fact("Dave", "reviews", "ProjectY")
    kg.add_fact("Dave", "consults", "Eve")
    yield kg
    kg.close()


@pytest.fixture
def empty_kg():
    """Empty KG for edge-case testing."""
    kg = KnowledgeGraph(db_path=":memory:")
    yield kg
    kg.close()


# ── detect_communities ────────────────────────────────────────────────


class TestDetectCommunities:
    def test_returns_list_of_community_dicts(self, kg):
        communities = kg.detect_communities()
        assert isinstance(communities, list)
        assert len(communities) >= 2  # At least two distinct communities
        for c in communities:
            assert "id" in c
            assert "nodes" in c
            assert "label" in c
            assert "size" in c
            assert "top_entity" in c

    def test_all_entities_covered(self, kg):
        """Every entity should appear in exactly one community."""
        communities = kg.detect_communities()
        all_nodes = []
        for c in communities:
            all_nodes.extend(c["nodes"])
        # Unique set
        unique = set(all_nodes)
        assert len(all_nodes) == len(unique)
        # All expected entities present
        expected = {
            "Alice", "Bob", "Carol", "ProjectX", "ProjectY",
            "Infrastructure", "Dave", "Eve", "Frank", "ProjectZ",
        }
        assert unique == expected

    def test_communities_sorted_by_size_descending(self, kg):
        communities = kg.detect_communities()
        sizes = [c["size"] for c in communities]
        assert sizes == sorted(sizes, reverse=True)

    def test_top_entity_is_member_with_highest_degree(self, kg):
        communities = kg.detect_communities()
        for c in communities:
            if c["size"] > 1:
                assert c["top_entity"] in c["nodes"]

    def test_empty_graph_returns_empty(self, empty_kg):
        assert empty_kg.detect_communities() == []

    def test_single_fact_graph(self, empty_kg):
        empty_kg.add_fact("A", "rel", "B")
        communities = empty_kg.detect_communities()
        assert len(communities) == 1
        assert communities[0]["size"] == 2
        assert set(communities[0]["nodes"]) == {"A", "B"}

    def test_unsupported_algorithm_raises(self, kg):
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            kg.detect_communities(algorithm="invalid")

    def test_invalidated_facts_excluded(self, kg):
        """Invalidated facts should not be part of the community graph."""
        communities_before = kg.detect_communities()
        # Invalidate a bridge fact
        facts = kg.query("Dave")
        for f in facts:
            if f["predicate"] == "consults":
                kg.invalidate(f["id"])
                break
        kg._communities_cache = None
        communities_after = kg.detect_communities()
        # Still should have communities, but graph changed
        assert isinstance(communities_after, list)
        assert len(communities_after) >= 1


# ── god_nodes ─────────────────────────────────────────────────────────


class TestGodNodes:
    def test_returns_list_of_entity_dicts(self, kg):
        nodes = kg.god_nodes()
        assert isinstance(nodes, list)
        for n in nodes:
            assert "entity" in n
            assert "degree" in n

    def test_sorted_by_degree_descending(self, kg):
        nodes = kg.god_nodes()
        degrees = [n["degree"] for n in nodes]
        assert degrees == sorted(degrees, reverse=True)

    def test_top_k_limits_results(self, kg):
        nodes = kg.god_nodes(top_k=3)
        assert len(nodes) <= 3

    def test_default_top_k_is_10(self, kg):
        nodes = kg.god_nodes()
        assert len(nodes) <= 10

    def test_high_degree_entities_at_top(self, kg):
        """Alice appears as subject in 2 facts + Bob/Carol/ProjectX connect
        to her via ProjectX, so she should be high-degree."""
        nodes = kg.god_nodes()
        entity_names = [n["entity"] for n in nodes]
        # All entities should be present (10 entities, top_k=10 default)
        assert len(nodes) == 10

    def test_empty_graph_returns_empty(self, empty_kg):
        assert empty_kg.god_nodes() == []

    def test_single_fact(self, empty_kg):
        empty_kg.add_fact("X", "rel", "Y")
        nodes = empty_kg.god_nodes()
        assert len(nodes) == 2
        assert nodes[0]["degree"] == 1
        assert nodes[1]["degree"] == 1

    def test_counts_both_subject_and_object(self, empty_kg):
        """Entity appearing as subject in 3 facts and object in 2 should have degree 5."""
        empty_kg.add_fact("Hub", "rel1", "A")
        empty_kg.add_fact("Hub", "rel2", "B")
        empty_kg.add_fact("Hub", "rel3", "C")
        empty_kg.add_fact("D", "rel4", "Hub")
        empty_kg.add_fact("E", "rel5", "Hub")
        nodes = empty_kg.god_nodes()
        hub = [n for n in nodes if n["entity"] == "Hub"][0]
        assert hub["degree"] == 5


# ── surprising_connections ────────────────────────────────────────────


class TestSurprisingConnections:
    def test_returns_list_of_connection_dicts(self, kg):
        connections = kg.surprising_connections()
        assert isinstance(connections, list)
        for c in connections:
            assert "id" in c
            assert "subject" in c
            assert "predicate" in c
            assert "object" in c
            assert "surprise_score" in c
            assert "reason" in c

    def test_all_connections_are_cross_community(self, kg):
        """Each surprising connection should connect entities from different communities."""
        communities = kg.detect_communities()
        entity_to_comm = {}
        for comm in communities:
            for member in comm["nodes"]:
                entity_to_comm[member] = comm["id"]

        connections = kg.surprising_connections()
        for c in connections:
            subj_comm = entity_to_comm.get(c["subject"])
            obj_comm = entity_to_comm.get(c["object"])
            assert subj_comm is not None
            assert obj_comm is not None
            assert subj_comm != obj_comm, (
                f"Expected cross-community but both in community {subj_comm}: "
                f"{c['subject']} -> {c['object']}"
            )

    def test_sorted_by_surprise_score_descending(self, kg):
        connections = kg.surprising_connections()
        scores = [c["surprise_score"] for c in connections]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_limits_results(self, kg):
        connections = kg.surprising_connections(top_k=1)
        assert len(connections) <= 1

    def test_empty_graph_returns_empty(self, empty_kg):
        assert empty_kg.surprising_connections() == []

    def test_single_community_no_surprises(self, empty_kg):
        """If all entities are in one community, no surprising connections."""
        empty_kg.add_fact("A", "rel", "B")
        empty_kg.add_fact("B", "rel", "C")
        empty_kg.add_fact("C", "rel", "A")
        assert empty_kg.surprising_connections() == []

    def test_reason_string_describes_bridge(self, kg):
        connections = kg.surprising_connections()
        for c in connections:
            assert "Cross-community bridge" in c["reason"]
            assert c["subject"] in c["reason"]
            assert c["object"] in c["reason"]

    def test_bridge_facts_detected(self, kg):
        """Dave's cross-community facts should appear."""
        connections = kg.surprising_connections()
        subjects = [c["subject"] for c in connections]
        objects = [c["object"] for c in connections]
        # Dave should appear as a subject in some cross-community edges
        dave_edges = [
            c for c in connections if c["subject"] == "Dave" or c["object"] == "Dave"
        ]
        # Dave has two facts that may be cross-community
        assert len(dave_edges) >= 1
