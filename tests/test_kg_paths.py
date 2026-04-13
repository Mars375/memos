"""Tests for KG Path Queries — multi-hop graph traversal."""

import pytest

from memos.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    """Create an in-memory KG with a small test graph."""
    kg = KnowledgeGraph(db_path=":memory:")
    # Graph structure:
    #   Alice -[works_on]-> ProjectX
    #   Alice -[leads]-> Infrastructure
    #   Bob -[works_on]-> ProjectX
    #   Bob -[manages]-> Carol
    #   Carol -[works_on]-> ProjectY
    #   ProjectX -[depends_on]-> ProjectY
    #   Dave -[reviews]-> ProjectY
    #   Eve -[works_on]-> ProjectZ   (isolated cluster)
    kg.add_fact("Alice", "works_on", "ProjectX")
    kg.add_fact("Alice", "leads", "Infrastructure")
    kg.add_fact("Bob", "works_on", "ProjectX")
    kg.add_fact("Bob", "manages", "Carol")
    kg.add_fact("Carol", "works_on", "ProjectY")
    kg.add_fact("ProjectX", "depends_on", "ProjectY")
    kg.add_fact("Dave", "reviews", "ProjectY")
    kg.add_fact("Eve", "works_on", "ProjectZ")
    yield kg
    kg.close()


class TestNeighbors:
    """Tests for KnowledgeGraph.neighbors()."""

    def test_neighbors_depth1(self, kg):
        result = kg.neighbors("Alice", depth=1)
        assert result["center"] == "Alice"
        assert result["depth"] == 1
        assert "Alice" in result["nodes"]
        # Alice connects to ProjectX, Infrastructure
        assert "ProjectX" in result["nodes"]
        assert "Infrastructure" in result["nodes"]
        assert len(result["edges"]) >= 2

    def test_neighbors_depth2(self, kg):
        result = kg.neighbors("Alice", depth=2)
        assert result["depth"] == 2
        # Hop 2 from Alice: ProjectX -> Bob, ProjectY; Infrastructure -> (none new)
        assert "Bob" in result["nodes"]
        assert "ProjectY" in result["nodes"]
        # Should have layers
        assert 1 in result["layers"]
        assert 2 in result["layers"]

    def test_neighbors_layers(self, kg):
        result = kg.neighbors("Alice", depth=2)
        hop1 = result["layers"][1]
        hop2 = result["layers"][2]
        # Hop 1: entities directly connected to Alice
        assert "ProjectX" in hop1 or "Infrastructure" in hop1
        # Hop 2: entities 2 hops away
        assert len(hop2) > 0

    def test_neighbors_direction_subject(self, kg):
        # Only triples where Alice is the subject
        result = kg.neighbors("Alice", depth=1, direction="subject")
        for edge in result["edges"]:
            assert edge["subject"] == "Alice"

    def test_neighbors_direction_object(self, kg):
        # Only triples where Alice is the object
        result = kg.neighbors("Alice", depth=1, direction="object")
        # Alice is not an object in any triple, so no edges
        assert len(result["edges"]) == 0

    def test_neighbors_isolated_entity(self, kg):
        # Eve only connects to ProjectZ, nothing else connects to Eve/ProjectZ
        result = kg.neighbors("Eve", depth=3)
        assert "Eve" in result["nodes"]
        assert "ProjectZ" in result["nodes"]
        # Should be just the 2 nodes
        assert len(result["nodes"]) == 2

    def test_neighbors_nonexistent_entity(self, kg):
        result = kg.neighbors("Nobody", depth=2)
        assert result["nodes"] == ["Nobody"]
        assert len(result["edges"]) == 0

    def test_neighbors_invalid_depth(self, kg):
        with pytest.raises(ValueError, match="depth must be >= 1"):
            kg.neighbors("Alice", depth=0)


class TestFindPaths:
    """Tests for KnowledgeGraph.find_paths()."""

    def test_direct_path(self, kg):
        # Alice -> ProjectX is a direct edge
        paths = kg.find_paths("Alice", "ProjectX")
        assert len(paths) >= 1
        # Shortest path should be 1 hop
        assert len(paths[0]) == 1
        assert paths[0][0]["subject"] == "Alice"
        assert paths[0][0]["object"] == "ProjectX"

    def test_two_hop_path(self, kg):
        # Alice -> ProjectX -> Bob (via works_on both sides)
        paths = kg.find_paths("Alice", "Bob", max_hops=2)
        assert len(paths) >= 1
        # There should be at least one 2-hop path
        found_two_hop = any(len(p) == 2 for p in paths)
        assert found_two_hop, f"Expected a 2-hop path, got: {paths}"

    def test_three_hop_path(self, kg):
        # Alice -> ProjectX -> Bob -> Carol
        paths = kg.find_paths("Alice", "Carol", max_hops=3)
        assert len(paths) >= 1

    def test_no_path_isolated(self, kg):
        # Eve/ProjectZ are isolated from Alice's cluster
        paths = kg.find_paths("Alice", "Eve", max_hops=5)
        assert len(paths) == 0

    def test_same_entity(self, kg):
        paths = kg.find_paths("Alice", "Alice")
        assert len(paths) == 0

    def test_max_paths_limit(self, kg):
        paths = kg.find_paths("Alice", "ProjectY", max_hops=4, max_paths=2)
        assert len(paths) <= 2

    def test_invalid_max_hops(self, kg):
        with pytest.raises(ValueError, match="max_hops must be >= 1"):
            kg.find_paths("Alice", "Bob", max_hops=0)

    def test_path_chain_valid(self, kg):
        """Each consecutive triple in a path must share an entity."""
        paths = kg.find_paths("Alice", "Carol", max_hops=4)
        for path in paths:
            for i in range(len(path) - 1):
                current_triple = path[i]
                next_triple = path[i + 1]
                # They must share at least one entity
                current_entities = {current_triple["subject"], current_triple["object"]}
                next_entities = {next_triple["subject"], next_triple["object"]}
                assert current_entities & next_entities, f"Path chain broken: {current_triple} -> {next_triple}"


class TestShortestPath:
    """Tests for KnowledgeGraph.shortest_path()."""

    def test_shortest_path_exists(self, kg):
        path = kg.shortest_path("Alice", "ProjectX")
        assert path is not None
        assert len(path) == 1

    def test_shortest_path_multi_hop(self, kg):
        path = kg.shortest_path("Alice", "Carol", max_hops=5)
        assert path is not None
        assert len(path) <= 5

    def test_shortest_path_none(self, kg):
        path = kg.shortest_path("Alice", "Eve", max_hops=5)
        assert path is None

    def test_shortest_path_is_shortest(self, kg):
        """shortest_path should return no more hops than find_paths minimum."""
        path = kg.shortest_path("Alice", "ProjectY", max_hops=5)
        all_paths = kg.find_paths("Alice", "ProjectY", max_hops=5, max_paths=20)
        if path:
            min_hops = min(len(p) for p in all_paths)
            assert len(path) == min_hops


class TestCLI:
    """Test CLI commands for path queries."""

    def test_kg_path_cli(self, kg, monkeypatch, capsys):
        import argparse

        from memos.cli import cmd_kg_path

        ns = argparse.Namespace(
            entity_a="Alice",
            entity_b="Bob",
            max_hops=3,
            max_paths=10,
            kg_db=None,
        )
        # Override _get_kg to use our test instance
        import memos.cli as cli_mod

        original_get_kg = cli_mod._get_kg
        cli_mod._get_kg = lambda ns: kg
        try:
            cmd_kg_path(ns)
            captured = capsys.readouterr()
            assert "path" in captured.out.lower() or "Path" in captured.out
        finally:
            cli_mod._get_kg = original_get_kg

    def test_kg_neighbors_cli(self, kg, monkeypatch, capsys):
        import argparse

        from memos.cli import cmd_kg_neighbors

        ns = argparse.Namespace(
            entity="Alice",
            depth=2,
            direction="both",
            kg_db=None,
        )
        from unittest.mock import patch

        with patch("memos.cli.commands_knowledge._get_kg", return_value=kg):
            cmd_kg_neighbors(ns)
        captured = capsys.readouterr()
        assert "Neighborhood" in captured.out
        assert "ProjectX" in captured.out

    def test_kg_path_cli_no_path(self, kg, capsys):
        import argparse

        from memos.cli import cmd_kg_path

        ns = argparse.Namespace(
            entity_a="Alice",
            entity_b="Eve",
            max_hops=3,
            max_paths=10,
            kg_db=None,
        )
        import memos.cli as cli_mod

        original_get_kg = cli_mod._get_kg
        cli_mod._get_kg = lambda ns: kg
        try:
            cmd_kg_path(ns)
            captured = capsys.readouterr()
            assert "No path" in captured.out
        finally:
            cli_mod._get_kg = original_get_kg
