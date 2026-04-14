"""Tests for markdown migration tool (P4)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow importing from tools/
TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from migrate_markdown import _tags_from_filename, collect_files, migrate, parse_markdown_file  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_md(tmp_path) -> Path:
    f = tmp_path / "notes.md"
    f.write_text("""# My Notes

## Python Tips
Use list comprehensions for clean code.
Prefer f-strings over .format().

## Docker Tips
Use multi-stage builds to minimize image size.
Always pin base image versions.
""")
    return f


@pytest.fixture
def frontmatter_md(tmp_path) -> Path:
    f = tmp_path / "prefs.md"
    f.write_text("""---
tags: preferences, workflow
---
# User Preferences

## Response Style
Prefer concise answers. Use bullet points.

## Code Style
Always include type hints. Follow PEP 8.
""")
    return f


@pytest.fixture
def flat_md(tmp_path) -> Path:
    f = tmp_path / "flat.md"
    f.write_text("This is a simple memory without any headers. It contains useful information.")
    return f


@pytest.fixture
def daily_md(tmp_path) -> Path:
    f = tmp_path / "2026-04-07-python-tips.md"
    f.write_text("""# Daily Log 2026-04-07

## Learned
Python walrus operator := is useful in while loops.

## Decisions
Chose FastAPI over Flask for better async support.
""")
    return f


@pytest.fixture
def empty_md(tmp_path) -> Path:
    f = tmp_path / "empty.md"
    f.write_text("# Title\n\n")
    return f


# ---------------------------------------------------------------------------
# parse_markdown_file
# ---------------------------------------------------------------------------


def test_parse_sections(simple_md):
    memories = parse_markdown_file(simple_md)
    assert len(memories) >= 2
    contents = " ".join(m.content for m in memories)
    assert "list comprehensions" in contents
    assert "multi-stage" in contents


def test_parse_frontmatter_tags(frontmatter_md):
    memories = parse_markdown_file(frontmatter_md)
    assert len(memories) >= 2
    for m in memories:
        assert "preferences" in m.tags or "workflow" in m.tags


def test_parse_flat_file(flat_md):
    memories = parse_markdown_file(flat_md)
    assert len(memories) == 1
    assert "useful information" in memories[0].content


def test_parse_daily_filename_tags(daily_md):
    memories = parse_markdown_file(daily_md)
    assert len(memories) >= 1
    all_tags = [t for m in memories for t in m.tags]
    assert "daily" in all_tags


def test_parse_extra_tags(simple_md):
    memories = parse_markdown_file(simple_md, extra_tags=["imported", "test"])
    for m in memories:
        assert "imported" in m.tags
        assert "test" in m.tags


def test_parse_empty_file(empty_md):
    memories = parse_markdown_file(empty_md)
    assert len(memories) == 0


def test_source_file_recorded(simple_md):
    memories = parse_markdown_file(simple_md)
    for m in memories:
        assert str(simple_md) == m.source_file


def test_content_capped_at_2000(tmp_path):
    long_md = tmp_path / "long.md"
    long_md.write_text("# Title\n\n## Section\n\n" + "x" * 5000)
    memories = parse_markdown_file(long_md)
    for m in memories:
        assert len(m.content) <= 2000


# ---------------------------------------------------------------------------
# collect_files
# ---------------------------------------------------------------------------


def test_collect_files_dir(tmp_path):
    (tmp_path / "a.md").write_text("# A")
    (tmp_path / "b.md").write_text("# B")
    (tmp_path / "c.txt").write_text("ignore")
    files = collect_files([tmp_path])
    assert len(files) == 2
    assert all(f.suffix == ".md" for f in files)


def test_collect_files_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "top.md").write_text("# Top")
    (sub / "nested.md").write_text("# Nested")
    files = collect_files([tmp_path], recursive=True)
    assert len(files) == 2


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------


def test_migrate_imports(simple_md, memos_empty):
    imported, errors = migrate([simple_md], memos_empty)

    s = memos_empty.stats()


def test_migrate_dry_run(simple_md, memos_empty):
    imported, errors = migrate([simple_md], memos_empty, dry_run=True)

    s = memos_empty.stats()


def test_migrate_extra_tags(simple_md, memos_empty):
    migrate([simple_md], memos_empty, extra_tags=["migrated"])
    results = memos_empty.recall("Python", top=10)


def test_migrate_multiple_files(simple_md, frontmatter_md, memos_empty):
    imported, errors = migrate([simple_md, frontmatter_md], memos_empty)


def test_migrate_missing_file(tmp_path, memos_empty):
    bad = tmp_path / "does_not_exist.md"
    # Should not crash — collect_files just skips non-existent files
    files = collect_files([bad])
    assert len(files) == 0


# ---------------------------------------------------------------------------
# filename tag derivation
# ---------------------------------------------------------------------------


def test_tags_from_daily_filename():
    tags = _tags_from_filename(Path("2026-04-07.md"))
    assert "daily" in tags


def test_tags_from_dated_slug_filename():
    tags = _tags_from_filename(Path("2026-04-07-python-tips.md"))
    assert "daily" in tags
    assert any("python" in t for t in tags)


def test_tags_from_plain_filename():
    tags = _tags_from_filename(Path("preferences.md"))
    assert "preferences" in tags
