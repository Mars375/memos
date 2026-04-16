from __future__ import annotations

from pathlib import Path

import pytest

from memos.brain import BrainSearch
from memos.core import MemOS
from memos.kg_bridge import KGBridge
from memos.knowledge_graph import KnowledgeGraph
from memos.mcp_server import _dispatch
from memos.wiki_living import LivingWikiEngine


@pytest.fixture()
def brain_env(tmp_path: Path):
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn("Alice works at OpenAI and leads MemOS retrieval design.", tags=["people", "memos"])
    memos.learn("Bob collaborates with Alice on graph search.", tags=["people", "graph"])

    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()
    wiki.update(force=True)

    kg = KnowledgeGraph(db_path=str(kg_path))
    kg.add_fact("Alice", "works_at", "OpenAI", confidence_label="EXTRACTED")
    kg.add_fact("OpenAI", "builds", "MemOS", confidence_label="INFERRED")
    memos._kg = kg

    yield memos, kg, wiki_root, kg_path
    kg.close()


def test_brain_search_unifies_sources(brain_env):
    memos, kg, wiki_root, _kg_path = brain_env
    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

    result = searcher.search("Alice OpenAI", top_k=5)

    assert result.entities
    assert any(item.entity == "Alice" for item in result.wiki_pages)
    assert any(fact.subject == "Alice" for fact in result.kg_facts)
    assert any("Alice works at OpenAI" in item.content for item in result.memories)
    assert "Fused context:" in result.context
    assert "[kg" in result.context
    assert "[memory" in result.context


def test_brain_entity_detail_bridges_wiki_memories_and_graph(brain_env):
    memos, kg, wiki_root, _kg_path = brain_env
    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

    detail = searcher.entity_detail("Alice")

    assert detail.entity == "Alice"
    assert "# Alice" in detail.wiki_page
    assert any(memory["id"] for memory in detail.memories)
    assert any(fact["subject"] == "Alice" or fact["object"] == "Alice" for fact in detail.kg_facts)
    assert any(neighbor.entity == "OpenAI" for neighbor in detail.kg_neighbors)


def test_brain_entity_subgraph_returns_neighbors(brain_env):
    memos, kg, wiki_root, _kg_path = brain_env
    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

    subgraph = searcher.entity_subgraph("Alice", depth=2)

    assert subgraph.center == "Alice"
    assert any(node["id"] == "Alice" for node in subgraph.nodes)
    assert any(edge["source"] == "Alice" or edge["target"] == "Alice" for edge in subgraph.edges)


@pytest.mark.asyncio
async def test_brain_search_api(brain_env):
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    memos, _kg, wiki_root, kg_path = brain_env
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/brain/search",
            json={"query": "Alice OpenAI", "top_k": 5, "wiki_dir": str(wiki_root)},
        )

    data = response.json()
    assert data["status"] == "ok"
    assert data["entities"]
    assert len(data["memories"]) >= 1
    assert len(data["wiki_pages"]) >= 1
    assert len(data["kg_facts"]) >= 1
    assert "Fused context:" in data["context"]


@pytest.mark.asyncio
async def test_brain_entity_detail_api(brain_env):
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    memos, _kg, wiki_root, kg_path = brain_env
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/brain/entity/Alice",
            params={"wiki_dir": str(wiki_root)},
        )

    data = response.json()
    assert data["status"] == "ok"
    assert data["entity"] == "Alice"
    assert data["wiki_page"]
    assert data["kg_facts"]
    assert any(neighbor["entity"] == "OpenAI" for neighbor in data["kg_neighbors"])


def test_brain_search_rebinds_stale_bridge_to_explicit_kg(tmp_path: Path):
    persist_path = tmp_path / "store.json"
    wiki_root = tmp_path / "wiki"
    stale_kg_path = tmp_path / "stale-kg.db"
    fresh_kg_path = tmp_path / "fresh-kg.db"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn("Alice works at OpenAI.", tags=["people"])
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()
    wiki.update(force=True)

    stale_kg = KnowledgeGraph(db_path=str(stale_kg_path))
    stale_kg.add_fact("Alice", "works_at", "OldCorp", confidence_label="AMBIGUOUS")
    memos._kg_bridge = KGBridge(memos, stale_kg)

    fresh_kg = KnowledgeGraph(db_path=str(fresh_kg_path))
    fresh_kg.add_fact("Alice", "works_at", "OpenAI", confidence_label="EXTRACTED")

    searcher = BrainSearch(memos, kg=fresh_kg, wiki_dir=str(wiki_root))
    detail = searcher.entity_detail("Alice")

    assert any(fact["object"] == "OpenAI" for fact in detail.kg_facts)
    assert all(fact["object"] != "OldCorp" for fact in detail.kg_facts)

    stale_kg.close()
    fresh_kg.close()


@pytest.mark.asyncio
async def test_brain_entity_subgraph_api(brain_env):
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    memos, _kg, wiki_root, kg_path = brain_env
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/brain/entity/Alice/subgraph?depth=2")

    data = response.json()
    assert data["status"] == "ok"
    assert data["entity"] == "Alice"
    assert any(node["id"] == "Alice" for node in data["nodes"])
    assert any(edge["source"] == "Alice" or edge["target"] == "Alice" for edge in data["edges"])


def test_brain_search_mcp_dispatch(brain_env):
    memos, kg, wiki_root, _kg_path = brain_env
    memos._kg = kg
    response = _dispatch(
        memos,
        "brain_search",
        {"query": "Alice OpenAI", "top_k": 5, "wiki_dir": str(wiki_root)},
    )

    assert not response.get("isError")
    text = response["content"][0]["text"]
    assert "Memories (" in text
    assert "Wiki (" in text
    assert "KG facts (" in text
    assert "Context:" in text


def test_brain_search_cli(tmp_path: Path, capsys):
    from memos.cli import main

    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn("Alice works at OpenAI and documents MemOS.", tags=["people", "memos"])
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()
    wiki.update(force=True)
    kg = KnowledgeGraph(db_path=str(kg_path))
    kg.add_fact("Alice", "works_at", "OpenAI")
    kg.close()

    main(
        [
            "brain-search",
            "Alice OpenAI",
            "--backend",
            "json",
            "--persist-path",
            str(persist_path),
            "--wiki-dir",
            str(wiki_root),
            "--db",
            str(kg_path),
            "--top",
            "5",
        ]
    )

    out = capsys.readouterr().out
    assert "Brain search: Alice OpenAI" in out
    assert "Memories:" in out
    assert "Wiki pages:" in out
    assert "KG facts:" in out


# ── Suggest Questions ────────────────────────────────────────────


def test_suggest_questions_hub_exploration(brain_env):
    memos, kg, wiki_root, _kg_path = brain_env
    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

    suggestions = searcher.suggest_questions(top_k=5)

    assert len(suggestions) >= 1
    hub_questions = [sq for sq in suggestions if sq.category == "hub_exploration"]
    assert len(hub_questions) >= 1
    assert any("What is connected to" in sq.question for sq in hub_questions)
    assert any("Alice" in sq.question or "OpenAI" in sq.question for sq in hub_questions)


def test_suggest_questions_orphan_entities(tmp_path: Path):
    """Entities that appear in only one fact should be flagged as orphans."""
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn("Rare project Zephyr is interesting.", tags=["project"])

    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()
    wiki.update(force=True)

    kg = KnowledgeGraph(db_path=str(kg_path))
    kg.add_fact("Zephyr", "is_a", "project", confidence_label="EXTRACTED")
    memos._kg = kg

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    suggestions = searcher.suggest_questions(top_k=10)

    orphan_qs = [sq for sq in suggestions if sq.category == "orphan_exploration"]
    assert len(orphan_qs) >= 1
    assert any("Zephyr" in sq.question for sq in orphan_qs)


def test_suggest_questions_respects_top_k(brain_env):
    memos, kg, wiki_root, _kg_path = brain_env
    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

    suggestions = searcher.suggest_questions(top_k=2)
    assert len(suggestions) <= 2


def test_suggest_questions_sorted_by_score(brain_env):
    memos, kg, wiki_root, _kg_path = brain_env
    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

    suggestions = searcher.suggest_questions(top_k=10)
    scores = [sq.score for sq in suggestions]
    assert scores == sorted(scores, reverse=True)


def test_suggest_questions_empty_kg(tmp_path: Path):
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()

    kg = KnowledgeGraph(db_path=str(kg_path))
    memos._kg = kg

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    suggestions = searcher.suggest_questions(top_k=5)

    assert suggestions == []


@pytest.mark.asyncio
async def test_brain_suggest_api(brain_env):
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    memos, _kg, wiki_root, kg_path = brain_env
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/brain/suggest", params={"top_k": 5})

    data = response.json()
    assert data["status"] == "ok"
    assert "suggestions" in data
    assert data["total"] >= 1
    for sq in data["suggestions"]:
        assert "question" in sq
        assert "category" in sq
        assert "score" in sq
        assert "entities" in sq


def test_brain_suggest_mcp_dispatch(brain_env):
    memos, kg, wiki_root, _kg_path = brain_env
    memos._kg = kg
    response = _dispatch(memos, "brain_suggest", {"top_k": 5})

    assert not response.get("isError")
    text = response["content"][0]["text"]
    assert "Suggested questions" in text
    assert "hub_exploration" in text


# ── Surprising Connections ──────────────────────────────────────


def test_surprising_connections_empty_graph(tmp_path: Path):
    """An empty knowledge graph should return no connections."""
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()

    kg = KnowledgeGraph(db_path=str(kg_path))
    memos._kg = kg

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    result = searcher.surprising_connections(top_n=5)

    assert result == []
    kg.close()


def test_surprising_connections_single_community(tmp_path: Path):
    """If all entities are in the same community there are no cross-domain links."""
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()

    kg = KnowledgeGraph(db_path=str(kg_path))
    # A→B→C forms a single connected component / one community
    kg.add_fact("A", "related_to", "B", confidence=0.9)
    kg.add_fact("B", "related_to", "C", confidence=0.8)
    memos._kg = kg

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    result = searcher.surprising_connections(top_n=5)

    assert result == []
    kg.close()


def test_surprising_connections_cross_domain(tmp_path: Path):
    """Facts linking entities in different communities should be found and scored."""
    from unittest.mock import patch

    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()

    kg = KnowledgeGraph(db_path=str(kg_path))
    # Community 1 (tech): Alice —works_at→ OpenAI, Alice —uses→ Python
    kg.add_fact("Alice", "works_at", "OpenAI", confidence=0.95)
    kg.add_fact("Alice", "uses", "Python", confidence=0.9)
    # Community 2 (biology): Bob —studies→ Cells, Bob —works_at→ LabCorp
    kg.add_fact("Bob", "studies", "Cells", confidence=0.85)
    kg.add_fact("Bob", "works_at", "LabCorp", confidence=0.8)
    # Cross-domain link: Alice —collaborates_with→ Bob
    kg.add_fact("Alice", "collaborates_with", "Bob", confidence=0.7)
    memos._kg = kg

    # Mock communities so Alice/OpenAI/Python are in one and Bob/Cells/LabCorp in another
    fake_communities = [
        {"id": "0", "label": "tech", "nodes": ["Alice", "OpenAI", "Python"], "size": 3, "top_entity": "Alice"},
        {"id": "1", "label": "bio", "nodes": ["Bob", "Cells", "LabCorp"], "size": 3, "top_entity": "Bob"},
    ]

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    with patch.object(kg, "detect_communities", return_value=fake_communities):
        result = searcher.surprising_connections(top_n=5)

    # Should find the cross-domain fact
    assert len(result) >= 1

    # Find the cross-domain fact about Alice and Bob
    cross = [r for r in result if r["subject"] == "Alice" and r["object"] == "Bob"]
    assert len(cross) == 1

    fact = cross[0]
    assert fact["predicate"] == "collaborates_with"
    assert fact["confidence"] == 0.7
    assert fact["score"] > 0

    # Verify scoring formula: 2.0 * confidence * (1 / degree_of_predicate)
    # "collaborates_with" appears once → edge_rarity = 1.0
    # score = 2.0 * 0.7 * 1.0 = 1.4
    assert fact["score"] == pytest.approx(1.4, abs=1e-4)

    kg.close()


def test_surprising_connections_reason_is_descriptive(tmp_path: Path):
    """The reason string should be human-readable and mention communities."""
    from unittest.mock import patch

    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()

    kg = KnowledgeGraph(db_path=str(kg_path))
    # Two separate communities
    kg.add_fact("Alice", "works_at", "OpenAI", confidence=0.9)
    kg.add_fact("Bob", "studies", "Cells", confidence=0.9)
    kg.add_fact("Alice", "mentors", "Bob", confidence=0.8)
    memos._kg = kg

    fake_communities = [
        {"id": "0", "label": "tech", "nodes": ["Alice", "OpenAI"], "size": 2, "top_entity": "Alice"},
        {"id": "1", "label": "bio", "nodes": ["Bob", "Cells"], "size": 2, "top_entity": "Bob"},
    ]

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    with patch.object(kg, "detect_communities", return_value=fake_communities):
        result = searcher.surprising_connections(top_n=5)

    assert len(result) >= 1
    reason = result[0]["reason"]
    assert "Cross-domain link:" in reason
    assert "Alice" in reason
    assert "Bob" in reason
    assert "mentors" in reason
    assert "community" in reason.lower()

    kg.close()


@pytest.mark.asyncio
async def test_surprising_connections_api(tmp_path: Path):
    """Test the GET /api/v1/brain/connections endpoint."""
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()

    kg = KnowledgeGraph(db_path=str(kg_path))
    kg.add_fact("Alice", "works_at", "OpenAI", confidence=0.9)
    kg.add_fact("Bob", "studies", "Cells", confidence=0.9)
    kg.add_fact("Alice", "mentors", "Bob", confidence=0.8)
    kg.close()

    fake_communities = [
        {"id": "0", "label": "tech", "nodes": ["Alice", "OpenAI"], "size": 2, "top_entity": "Alice"},
        {"id": "1", "label": "bio", "nodes": ["Bob", "Cells"], "size": 2, "top_entity": "Bob"},
    ]

    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))

    # Patch detect_communities on the KG module level so the endpoint picks it up
    import memos.knowledge_graph as _kg_mod

    with patch.object(_kg_mod.KnowledgeGraph, "detect_communities", return_value=fake_communities):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/brain/connections", params={"top": 5})

    data = response.json()
    assert data["status"] == "ok"
    assert "connections" in data
    assert "total" in data


# ── Enhanced Suggest Questions (Task 5.2) ────────────────────────


def test_suggest_god_node_relationship_questions(brain_env):
    """Top 3 god nodes should generate pairwise relationship questions."""
    memos, kg, wiki_root, _kg_path = brain_env
    # Add more facts so there are at least 3 god nodes
    kg.add_fact("Alice", "uses", "Python", confidence_label="EXTRACTED")
    kg.add_fact("OpenAI", "located_in", "SanFrancisco", confidence_label="EXTRACTED")

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    suggestions = searcher.suggest_questions(top_k=20)

    god_rel = [sq for sq in suggestions if sq.category == "god_node_relationship"]
    assert len(god_rel) >= 1
    for sq in god_rel:
        assert "What is the relationship between" in sq.question
        assert " and " in sq.question


def test_suggest_small_community_questions(tmp_path: Path):
    """Communities with 1-2 members should generate exploration questions."""
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn("Zephyr is a small research project.", tags=["project"])

    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()
    wiki.update(force=True)

    kg = KnowledgeGraph(db_path=str(kg_path))
    # Two isolated facts → each entity forms its own 1-2 node community
    kg.add_fact("Zephyr", "is_a", "project", confidence_label="EXTRACTED")
    kg.add_fact("Orion", "is_a", "tool", confidence_label="EXTRACTED")
    memos._kg = kg

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    suggestions = searcher.suggest_questions(top_k=20)

    small_comm = [sq for sq in suggestions if sq.category == "small_community"]
    assert len(small_comm) >= 1
    for sq in small_comm:
        assert "What else is connected to" in sq.question

    kg.close()


def test_suggest_ambiguous_fact_questions(tmp_path: Path):
    """Facts with AMBIGUOUS confidence should generate verification questions."""
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn("Maybe Pluto is a planet.", tags=["space"])

    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()
    wiki.update(force=True)

    kg = KnowledgeGraph(db_path=str(kg_path))
    kg.add_fact("Pluto", "is_a", "planet", confidence_label="AMBIGUOUS")
    kg.add_fact("Pluto", "orbits", "Sun", confidence_label="EXTRACTED")
    memos._kg = kg

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    suggestions = searcher.suggest_questions(top_k=20)

    ambig = [sq for sq in suggestions if sq.category == "ambiguous_verification"]
    assert len(ambig) >= 1
    assert any("Is it true that" in sq.question for sq in ambig)
    assert any("Pluto" in sq.question for sq in ambig)

    kg.close()


def test_suggest_wiki_sparse_entity_questions(tmp_path: Path):
    """Entities with wiki pages but few KG facts should generate questions."""
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn("RareEntity is mentioned in documents.", tags=["entity"])

    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()
    wiki.update(force=True)

    kg = KnowledgeGraph(db_path=str(kg_path))
    # Only one fact about RareEntity → sparse
    kg.add_fact("RareEntity", "mentioned_in", "documents", confidence_label="EXTRACTED")
    memos._kg = kg

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    suggestions = searcher.suggest_questions(top_k=20)

    sparse_qs = [sq for sq in suggestions if sq.category == "wiki_sparse"]
    assert len(sparse_qs) >= 1
    assert any("What do we know about" in sq.question for sq in sparse_qs)

    kg.close()


def test_suggest_questions_empty_kg_returns_empty(tmp_path: Path):
    """An empty KG should return empty suggestions."""
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()

    kg = KnowledgeGraph(db_path=str(kg_path))
    memos._kg = kg

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    suggestions = searcher.suggest_questions(top_k=5)

    assert suggestions == []
    kg.close()


def test_suggest_questions_n_parameter_limits_results(brain_env):
    """The n/top_k parameter should limit the number of returned questions."""
    memos, kg, wiki_root, _kg_path = brain_env
    kg.add_fact("Alice", "uses", "Python", confidence_label="EXTRACTED")
    kg.add_fact("OpenAI", "located_in", "SanFrancisco", confidence_label="EXTRACTED")

    searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
    suggestions = searcher.suggest_questions(top_k=2)
    assert len(suggestions) <= 2

    suggestions = searcher.suggest_questions(top_k=1)
    assert len(suggestions) <= 1


@pytest.mark.asyncio
async def test_brain_suggestions_api(brain_env):
    """Test the GET /api/v1/brain/suggestions endpoint."""
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    memos, _kg, wiki_root, kg_path = brain_env
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/brain/suggestions", params={"n": 5})

    data = response.json()
    assert data["status"] == "ok"
    assert "questions" in data
    assert "details" in data
    assert data["total"] >= 1
    # questions is a list of strings
    assert isinstance(data["questions"], list)
    for q in data["questions"]:
        assert isinstance(q, str)
    # details has structured data
    for d in data["details"]:
        assert "question" in d
        assert "category" in d
        assert "score" in d
        assert "entities" in d


@pytest.mark.asyncio
async def test_brain_suggestions_api_n_param(brain_env):
    """The n parameter should limit results in the API."""
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    memos, _kg, wiki_root, kg_path = brain_env
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/brain/suggestions", params={"n": 2})

    data = response.json()
    assert data["status"] == "ok"
    assert len(data["questions"]) <= 2
