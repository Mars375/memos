from __future__ import annotations

from pathlib import Path

import pytest

from memos.brain import BrainSearch
from memos.core import MemOS
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
        response = await client.get("/api/v1/brain/entity/Alice")

    data = response.json()
    assert data["status"] == "ok"
    assert data["entity"] == "Alice"
    assert data["wiki_page"]
    assert data["kg_facts"]
    assert any(neighbor["entity"] == "OpenAI" for neighbor in data["kg_neighbors"])


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

    main([
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
    ])

    out = capsys.readouterr().out
    assert "Brain search: Alice OpenAI" in out
    assert "Memories:" in out
    assert "Wiki pages:" in out
    assert "KG facts:" in out
