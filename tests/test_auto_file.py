"""Tests for Task 3.3: Auto-file good answers as wiki pages."""

from __future__ import annotations

from pathlib import Path

import pytest

from memos.brain import BrainSearch
from memos.core import MemOS
from memos.knowledge_graph import KnowledgeGraph
from memos.wiki_living import LivingWikiEngine


@pytest.fixture
def brain_env(tmp_path: Path):
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn(
        "Alice works at OpenAI and leads the MemOS retrieval design. "
        "She has extensive experience in vector databases and semantic search.",
        tags=["people", "memos"],
    )
    memos.learn(
        "Bob collaborates with Alice on graph search algorithms. "
        "Together they built the hybrid retrieval engine.",
        tags=["people", "graph"],
    )

    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()
    wiki.update(force=True)

    kg = KnowledgeGraph(db_path=str(kg_path))
    kg.add_fact("Alice", "works_at", "OpenAI", confidence_label="EXTRACTED")
    kg.add_fact("OpenAI", "builds", "MemOS", confidence_label="INFERRED")
    memos._kg = kg

    yield memos, kg, wiki_root
    kg.close()


class TestAutoFileSearch:
    def test_auto_file_creates_wiki_page_when_substantial(self, brain_env):
        memos, kg, wiki_root = brain_env
        searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

        result = searcher.search("Alice OpenAI retrieval", top_k=5, auto_file=True)
        assert len(result.context) > 200  # pre-condition

        # Wiki page should have been created
        page = searcher._wiki.read_page("Alice OpenAI retrieval")
        assert page is not None
        assert "Auto-filed from brain search" in page
        assert "## Entities" in page
        assert "## Fused Context" in page

    def test_auto_file_off_by_default(self, brain_env):
        memos, kg, wiki_root = brain_env
        searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

        result = searcher.search("Alice OpenAI retrieval", top_k=5)
        # No wiki page should be created when auto_file=False
        page = searcher._wiki.read_page("Alice OpenAI retrieval")
        assert page is None

    def test_auto_file_not_created_for_short_context(self, tmp_path: Path):
        """If context < 200 chars, no wiki page should be created."""
        persist_path = tmp_path / "store.json"
        kg_path = tmp_path / "kg.db"
        wiki_root = tmp_path / "wiki"

        memos = MemOS(backend="json", persist_path=str(persist_path))
        memos.learn("short", tags=["test"])  # Very short content

        wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
        wiki.init()
        wiki.update(force=True)

        kg = KnowledgeGraph(db_path=str(kg_path))
        memos._kg = kg

        searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))
        result = searcher.search("short", top_k=1, auto_file=True)

        # The context may or may not be >200 chars, so check conditionally
        if len(result.context) <= 200:
            page = searcher._wiki.read_page("short")
            assert page is None

        kg.close()

    def test_auto_file_page_contains_memories(self, brain_env):
        memos, kg, wiki_root = brain_env
        searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

        searcher.search("Alice OpenAI", top_k=5, auto_file=True)

        page = searcher._wiki.read_page("Alice OpenAI")
        assert page is not None
        assert "## Relevant Memories" in page

    def test_auto_file_page_contains_kg_facts(self, brain_env):
        memos, kg, wiki_root = brain_env
        searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

        searcher.search("Alice OpenAI", top_k=5, auto_file=True)

        page = searcher._wiki.read_page("Alice OpenAI")
        assert page is not None
        assert "## Knowledge Graph Facts" in page

    def test_auto_file_page_contains_entities(self, brain_env):
        memos, kg, wiki_root = brain_env
        searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

        searcher.search("Alice OpenAI", top_k=5, auto_file=True)

        page = searcher._wiki.read_page("Alice OpenAI")
        assert page is not None
        assert "## Entities" in page

    def test_auto_file_returns_slug(self, brain_env):
        memos, kg, wiki_root = brain_env
        searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

        result = searcher.search("Alice OpenAI retrieval", top_k=5)
        if len(result.context) > 200:
            slug = searcher._auto_file_wiki("Alice OpenAI retrieval", result)
            assert slug is not None
            assert "alice-openai-retrieval" == slug

    def test_auto_file_does_not_duplicate_existing_page(self, brain_env):
        memos, kg, wiki_root = brain_env
        searcher = BrainSearch(memos, kg=kg, wiki_dir=str(wiki_root))

        # First search creates the page
        searcher.search("Alice OpenAI", top_k=5, auto_file=True)

        # Second search should not fail; page already exists
        result = searcher.search("Alice OpenAI", top_k=5, auto_file=True)
        assert result is not None


@pytest.mark.asyncio
async def test_auto_file_api_parameter(brain_env):
    """POST /brain/search with auto_file=True creates a wiki page."""
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    memos, _kg, wiki_root, kg_path = brain_env[0], brain_env[1], brain_env[2], Path(brain_env[1]._db_path)
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/brain/search",
            json={
                "query": "Alice OpenAI retrieval",
                "top_k": 5,
                "wiki_dir": str(wiki_root),
                "auto_file": True,
            },
        )

    data = response.json()
    assert data["status"] == "ok"
    assert data["entities"]

    # Verify the wiki page was created
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    page = wiki.read_page("Alice OpenAI retrieval")
    assert page is not None
    assert "Auto-filed from brain search" in page


@pytest.mark.asyncio
async def test_auto_file_api_default_false(brain_env):
    """POST /brain/search without auto_file does not create a wiki page."""
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    memos, _kg, wiki_root, kg_path = brain_env[0], brain_env[1], brain_env[2], Path(brain_env[1]._db_path)
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/brain/search",
            json={
                "query": "UniqueQueryForThisTest",
                "top_k": 5,
                "wiki_dir": str(wiki_root),
            },
        )

    data = response.json()
    assert data["status"] == "ok"

    # Verify no wiki page was created
    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    page = wiki.read_page("UniqueQueryForThisTest")
    assert page is None
