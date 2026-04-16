"""Tests for KnowledgeGraph community detection (label-propagation)."""

from __future__ import annotations

import time

import pytest

from memos.knowledge_graph import KnowledgeGraph

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def kg():
    """In-memory KnowledgeGraph."""
    with KnowledgeGraph(":memory:") as g:
        yield g


def _add_chain(kg: KnowledgeGraph, entities: list[str], predicate: str = "related_to") -> None:
    """Add a linear chain of facts: e0→e1→e2→…"""
    for i in range(len(entities) - 1):
        kg.add_fact(entities[i], predicate, entities[i + 1])


# ── Core tests ────────────────────────────────────────────────


class TestDetectCommunitiesEmpty:
    """Empty graph → empty communities."""

    def test_empty_graph_returns_empty(self, kg):
        assert kg.detect_communities() == []

    def test_stats_on_empty(self, kg):
        stats = kg.stats()
        assert stats["total_facts"] == 0
        assert stats["active_facts"] == 0


class TestDetectCommunitiesThreeComponents:
    """Three disconnected components → three communities."""

    def test_three_components(self, kg):
        # Component A: alice → bob → carol
        _add_chain(kg, ["alice", "bob", "carol"])
        # Component B: dave → eve
        _add_chain(kg, ["dave", "eve"])
        # Component C: frank → grace → heidi → ivan
        _add_chain(kg, ["frank", "grace", "heidi", "ivan"])

        communities = kg.detect_communities()
        assert len(communities) == 3

        # Sort by size descending (already sorted by the method)
        sizes = [c["size"] for c in communities]
        assert sizes == sorted(sizes, reverse=True)

        # Verify structure of each community
        all_nodes: set[str] = set()
        for c in communities:
            assert isinstance(c["id"], str)
            assert isinstance(c["label"], str)
            assert isinstance(c["nodes"], list)
            assert isinstance(c["size"], int)
            assert isinstance(c["top_entity"], str)
            assert c["size"] == len(c["nodes"])
            assert c["top_entity"] in c["nodes"]
            all_nodes.update(c["nodes"])

        # All 9 entities should be covered
        assert all_nodes == {
            "alice",
            "bob",
            "carol",
            "dave",
            "eve",
            "frank",
            "grace",
            "heidi",
            "ivan",
        }

    def test_components_have_correct_sizes(self, kg):
        _add_chain(kg, ["alice", "bob", "carol"])
        _add_chain(kg, ["dave", "eve"])
        _add_chain(kg, ["frank", "grace", "heidi", "ivan"])

        communities = kg.detect_communities()
        sizes = sorted([c["size"] for c in communities], reverse=True)
        assert sizes == [4, 3, 2]


class TestLabelPropagationConvergence:
    """Label-propagation converges and produces stable results."""

    def test_converges_deterministically(self, kg):
        # Create a small graph
        kg.add_fact("a", "knows", "b")
        kg.add_fact("b", "knows", "c")
        kg.add_fact("c", "knows", "d")
        kg.add_fact("d", "knows", "e")

        result1 = kg.detect_communities()
        result2 = kg.detect_communities()
        assert result1 == result2

    def test_star_graph_single_community(self, kg):
        """A star (hub connected to many leaves) is one community."""
        for leaf in ["leaf1", "leaf2", "leaf3", "leaf4", "leaf5"]:
            kg.add_fact("hub", "connects", leaf)

        communities = kg.detect_communities()
        assert len(communities) == 1
        assert communities[0]["size"] == 6  # hub + 5 leaves
        assert communities[0]["top_entity"] == "hub"

    def test_fully_connected_single_community(self, kg):
        """A clique converges to a single community."""
        entities = ["alpha", "beta", "gamma", "delta"]
        for i, s in enumerate(entities):
            for o in entities[i + 1 :]:
                kg.add_fact(s, "linked", o)

        communities = kg.detect_communities()
        assert len(communities) == 1
        assert communities[0]["size"] == 4


class TestCommunityCache:
    """Results are cached for 60 seconds."""

    def test_cache_returns_same_object(self, kg):
        kg.add_fact("x", "rel", "y")
        r1 = kg.detect_communities()
        r2 = kg.detect_communities()
        assert r1 is r2  # same list object from cache

    def test_cache_expires(self, kg, monkeypatch):
        kg.add_fact("x", "rel", "y")
        r1 = kg.detect_communities()

        # Advance time past the TTL
        original_time = time.time()
        monkeypatch.setattr(time, "time", lambda: original_time + 61)

        # Force a new computation by adding a fact after the mock
        kg.add_fact("a", "rel", "b")
        # The cache should have been invalidated by the time jump
        r2 = kg.detect_communities()
        # r2 should reflect the new data (2 disconnected components now)
        assert r2 is not r1


class TestCommunityResultFormat:
    """Each community dict has the required keys and types."""

    def test_keys_and_types(self, kg):
        kg.add_fact("alice", "knows", "bob")
        communities = kg.detect_communities()
        assert len(communities) >= 1
        c = communities[0]
        required = {"id", "label", "nodes", "size", "top_entity"}
        assert set(c.keys()) == required
        assert isinstance(c["id"], str)
        assert isinstance(c["label"], str)
        assert isinstance(c["nodes"], list)
        assert isinstance(c["size"], int)
        assert isinstance(c["top_entity"], str)


class TestCommunityWithInvalidatedFacts:
    """Invalidated facts should not contribute to communities."""

    def test_invalidated_fact_removes_link(self, kg):
        # Create two groups: one linked pair and another linked pair
        kg.add_fact("alice", "knows", "bob")
        fid = kg.add_fact("carol", "knows", "dave")

        # Initially: 2 communities (2 disconnected pairs)
        kg._communities_cache = None
        communities = kg.detect_communities()
        assert len(communities) == 2

        # Invalidate carol-dave link
        kg.invalidate(fid)
        kg._communities_cache = None

        # Now only alice-bob remains as a single community
        communities = kg.detect_communities()
        assert len(communities) == 1
        assert set(communities[0]["nodes"]) == {"alice", "bob"}


class TestCommunityAlgorithmParameter:
    """Algorithm parameter validation."""

    def test_invalid_algorithm_raises(self, kg):
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            kg.detect_communities(algorithm="bogus")

    def test_louvain_alias_accepted(self, kg):
        """'louvain' is accepted as a backward-compat alias."""
        kg.add_fact("a", "r", "b")
        result = kg.detect_communities(algorithm="louvain")
        assert len(result) >= 1


# ── API endpoint test ────────────────────────────────────────


class TestAPIEndpoint:
    """Test the /api/v1/kg/communities endpoint via FastAPI TestClient."""

    @pytest.fixture
    def client(self):
        """Create a TestClient with a real KG."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from memos.api.routes.knowledge import create_knowledge_router

        app = FastAPI()
        kg = KnowledgeGraph(":memory:")
        router = create_knowledge_router(None, kg, None, None)
        app.include_router(router)
        return TestClient(app)

    def test_communities_endpoint_empty(self, client):
        resp = client.get("/api/v1/kg/communities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["communities"] == []
        assert data["total"] == 0

    def test_communities_endpoint_with_data(self, client):
        # Add facts directly to the KG
        # We need the same KG instance — extract from the app
        # Easier: use the route that creates a fresh in-memory KG
        # Let's use the facts endpoint to add data
        client.post(
            "/api/v1/kg/facts",
            json={"subject": "alice", "predicate": "knows", "object": "bob"},
        )
        client.post(
            "/api/v1/kg/facts",
            json={"subject": "carol", "predicate": "knows", "object": "dave"},
        )

        resp = client.get("/api/v1/kg/communities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["total"] == 2  # two disconnected components

        # Verify each community has the right structure
        for c in data["communities"]:
            assert "id" in c
            assert "label" in c
            assert "nodes" in c
            assert "size" in c
            assert "top_entity" in c

    def test_communities_endpoint_returns_json(self, client):
        resp = client.get("/api/v1/kg/communities")
        assert resp.headers["content-type"] == "application/json"
