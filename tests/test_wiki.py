"""Tests for wiki compile mode (P3)."""
from __future__ import annotations

import tempfile

import pytest

from memos.core import MemOS
from memos.wiki import WikiEngine


@pytest.fixture
def mem():
    m = MemOS()
    m.learn("Python is great for scripting", tags=["python", "dev"])
    m.learn("Use async/await for concurrency", tags=["python", "async"])
    m.learn("Docker simplifies deployment", tags=["devops"])
    m.learn("Use type hints everywhere", tags=["python", "dev"])
    return m


@pytest.fixture
def wiki(mem, tmp_path):
    return WikiEngine(mem, wiki_dir=str(tmp_path / "wiki"))


def test_compile_all_tags(wiki, tmp_path):
    pages = wiki.compile()
    assert len(pages) > 0
    tags = {p.tag for p in pages}
    assert "python" in tags
    assert "devops" in tags


def test_compile_creates_files(wiki, tmp_path):
    pages = wiki.compile()
    for page in pages:
        assert page.path.exists()
        assert page.memory_count > 0
        assert page.size_bytes > 0


def test_compile_markdown_structure(wiki):
    pages = wiki.compile()
    python_page = next(p for p in pages if p.tag == "python")
    content = python_page.path.read_text()
    assert "# python" in content
    assert "★" in content  # importance bar
    assert python_page.memory_count == 3  # 3 memories with "python" tag


def test_compile_filter_tags(wiki):
    pages = wiki.compile(tags=["devops"])
    assert len(pages) == 1
    assert pages[0].tag == "devops"
    assert pages[0].memory_count == 1


def test_list_pages(wiki):
    wiki.compile()
    pages = wiki.list_pages()
    assert len(pages) > 0
    assert all(p.memory_count > 0 for p in pages)
    assert all(p.size_bytes > 0 for p in pages)


def test_read_existing_tag(wiki):
    wiki.compile()
    content = wiki.read("python")
    assert content is not None
    assert "# python" in content
    assert "async" in content.lower() or "scripting" in content.lower()


def test_read_missing_tag(wiki):
    wiki.compile()
    result = wiki.read("nonexistent_tag_xyz")
    assert result is None


def test_read_case_insensitive(wiki):
    wiki.compile()
    content = wiki.read("PYTHON")
    assert content is not None


def test_compile_sorts_by_importance(mem, tmp_path):
    mem2 = MemOS()
    mem2.learn("High importance memory", tags=["test"], importance=0.9)
    mem2.learn("Low importance memory", tags=["test"], importance=0.1)
    wiki2 = WikiEngine(mem2, wiki_dir=str(tmp_path / "wiki2"))
    pages = wiki2.compile()
    test_page = next(p for p in pages if p.tag == "test")
    content = test_page.path.read_text()
    # High importance should appear before low
    hi_pos = content.index("High importance")
    lo_pos = content.index("Low importance")
    assert hi_pos < lo_pos


def test_wiki_engine_default_dir(mem):
    """WikiEngine should not crash even without explicit wiki_dir."""
    import os
    # Use a custom home to avoid polluting ~/.memos
    with tempfile.TemporaryDirectory() as tmpdir:
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = tmpdir
        try:
            wiki = WikiEngine(mem)
            assert wiki._wiki_dir.exists()
        finally:
            if old_home:
                os.environ["HOME"] = old_home
